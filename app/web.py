from __future__ import annotations
import hashlib
import logging
from fastapi import FastAPI, Header, HTTPException, Response, status
from .config import settings
from .logging import configure_json_logging
from .models import IncomingMail
from .queue import get_queue, get_redis
from .utils.idempotency import mark_if_first


configure_json_logging()
logger = logging.getLogger(__name__)
app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhooks/cloudmailin")
async def cloudmailin_webhook(mail: IncomingMail, response: Response, x_webhook_secret: str | None = Header(default=None)):
    if settings.webhook_secret and x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    # Basic validation of recipient matches configured forward address local part
    if settings.forward_address:
        expected_local = settings.forward_address.split("@")[0]
        if expected_local not in mail.envelope.to:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid recipient")

    message_id = None
    if mail.headers and isinstance(mail.headers, dict):
        message_id = mail.headers.get("message_id") or mail.headers.get("Message-Id")

    if not message_id:
        # Fallback to hash of subject+to to ensure idempotency across retries
        subject = mail.headers.get("subject") if mail.headers else ""
        message_id = hashlib.sha256(f"{subject}-{mail.envelope.to}".encode("utf-8")).hexdigest()

    idem_key = f"cloudmailin:msg:{message_id}"
    first = mark_if_first(get_redis(), idem_key, settings.idempotency_ttl_seconds)
    if not first:
        # Already processed recently; acknowledge to avoid retries
        logger.info("duplicate_message_skipped", extra={"message_id": message_id})
        response.status_code = status.HTTP_202_ACCEPTED
        return {"status": "duplicate", "message_id": message_id}

    job = get_queue().enqueue("app.worker.process_mail", {
        "message_id": message_id,
        "to": mail.envelope.to,
        "html": mail.html,
    })

    logger.info("enqueued_message", extra={"message_id": message_id, "job_id": job.id})
    response.status_code = status.HTTP_202_ACCEPTED
    return {"status": "enqueued", "message_id": message_id, "job_id": job.id}
