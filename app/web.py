from __future__ import annotations
import hashlib
import json
import logging
from fastapi import FastAPI, Form, HTTPException, Response, status
from .config import settings
from .logging import configure_json_logging
from .queue import publish_job
from .utils.mailgun_signature import verify_mailgun_signature, is_signature_verification_enabled


configure_json_logging()
logger = logging.getLogger(__name__)
app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


# -----------------------------------------------------------------------------
# Mailgun Webhook Endpoint
# -----------------------------------------------------------------------------

def _extract_message_id_from_mailgun_headers(message_headers: str | None) -> str | None:
    """
    Extract Message-Id from Mailgun's message-headers JSON string.

    Mailgun provides headers as a JSON array of [name, value] pairs, e.g.:
    [["Message-Id", "<abc123@example.com>"], ["Subject", "Hello"], ...]

    Args:
        message_headers: JSON string of header pairs from Mailgun.

    Returns:
        The Message-Id value if found, None otherwise.
    """
    if not message_headers:
        return None
    try:
        headers = json.loads(message_headers)
        for header in headers:
            if isinstance(header, list) and len(header) >= 2:
                name, value = header[0], header[1]
                if name.lower() == "message-id":
                    return value
    except (json.JSONDecodeError, TypeError):
        pass
    return None


@app.post("/webhooks/mailgun")
async def mailgun_webhook(
    response: Response,
    # Mailgun sends form-encoded data, not JSON
    recipient: str = Form(...),
    sender: str = Form(default=""),
    subject: str = Form(default=""),
    body_html: str | None = Form(default=None, alias="body-html"),
    body_plain: str | None = Form(default=None, alias="body-plain"),
    message_headers: str | None = Form(default=None, alias="message-headers"),
    timestamp: str = Form(default=""),
    token: str = Form(default=""),
    signature: str = Form(default=""),
    # Additional fields Mailgun may send
    stripped_text: str | None = Form(default=None, alias="stripped-text"),
    stripped_html: str | None = Form(default=None, alias="stripped-html"),
    from_field: str = Form(default="", alias="from"),
):
    """
    Webhook endpoint for Mailgun inbound email routing.

    Mailgun posts form-encoded data (not JSON) when forwarding inbound emails
    via Routes. This endpoint normalizes the payload and publishes it to
    RabbitMQ for processing by the worker.

    Security: If MAILGUN_SIGNING_KEY is configured, webhook signatures are
    verified using HMAC-SHA256. If not configured, all requests are accepted.
    """
    # Log the full incoming payload for debugging
    logger.info("mailgun_webhook_received", extra={
        "recipient": recipient,
        "sender": sender,
        "from": from_field,
        "subject": subject,
        "has_body_html": body_html is not None,
        "body_html_length": len(body_html) if body_html else 0,
        "body_html_preview": (body_html[:500] + "...") if body_html and len(body_html) > 500 else body_html,
        "has_body_plain": body_plain is not None,
        "body_plain_length": len(body_plain) if body_plain else 0,
        "has_stripped_html": stripped_html is not None,
        "stripped_html_length": len(stripped_html) if stripped_html else 0,
        "has_stripped_text": stripped_text is not None,
        "has_message_headers": message_headers is not None,
        "message_headers_preview": (message_headers[:300] + "...") if message_headers and len(message_headers) > 300 else message_headers,
        "has_signature": bool(signature),
        "has_timestamp": bool(timestamp),
    })

    # Verify signature if signing key is configured
    if is_signature_verification_enabled(settings.mailgun_signing_key):
        if not verify_mailgun_signature(
            signing_key=settings.mailgun_signing_key,
            timestamp=timestamp,
            token=token,
            signature=signature,
        ):
            logger.warning("mailgun_signature_invalid", extra={"recipient": recipient})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid signature",
            )

    # Optional: Validate recipient matches configured domain
    if settings.mailgun_domain:
        if not recipient.endswith(f"@{settings.mailgun_domain}"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid recipient domain",
            )

    # Extract Message-Id from headers for job tracking
    message_id = _extract_message_id_from_mailgun_headers(message_headers)
    if not message_id:
        # Fallback to hash of subject+recipient
        message_id = hashlib.sha256(f"{subject}-{recipient}".encode("utf-8")).hexdigest()

    # Build job payload - use body_html, fallback to stripped_html if body_html is empty
    html_content = body_html
    html_source = "body-html"
    if not html_content and stripped_html:
        html_content = stripped_html
        html_source = "stripped-html"
    
    job_payload = {
        "message_id": message_id,
        "to": recipient,
        "html": html_content,
    }
    
    # Log what we're publishing for debugging
    logger.info("mailgun_job_payload", extra={
        "message_id": message_id,
        "to": recipient,
        "html_source": html_source,
        "html_length": len(html_content) if html_content else 0,
        "html_is_none": html_content is None,
        "html_is_empty_string": html_content == "",
    })

    # Publish job to RabbitMQ
    publish_job(job_payload)

    logger.info("enqueued_message", extra={"message_id": message_id, "provider": "mailgun"})
    response.status_code = status.HTTP_200_OK
    return {"status": "enqueued", "message_id": message_id}
