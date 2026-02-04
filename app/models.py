from typing import Optional
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Mailgun Models (form-encoded payload)
# -----------------------------------------------------------------------------

class MailgunInbound(BaseModel):
    """
    Mailgun inbound email payload (form-encoded).
    
    Mailgun posts as application/x-www-form-urlencoded or multipart/form-data.
    Field names use hyphens (aliased here for Python compatibility).
    Used by the /webhooks/mailgun endpoint.
    
    Reference: https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/storing-and-retrieving-messages
    """
    recipient: str
    sender: str = ""
    subject: str = ""
    body_html: Optional[str] = Field(default=None, alias="body-html")
    body_plain: Optional[str] = Field(default=None, alias="body-plain")
    message_headers: Optional[str] = Field(default=None, alias="message-headers")
    # Signature verification fields
    timestamp: str = ""
    token: str = ""
    signature: str = ""

    class Config:
        populate_by_name = True  # Allow both alias and field name


# -----------------------------------------------------------------------------
# Cloudflare Models (JSON payload)
# -----------------------------------------------------------------------------

class CloudflareInbound(BaseModel):
    """
    Cloudflare inbound email payload (JSON).
    
    Cloudflare Workers post JSON when forwarding inbound emails.
    Used by the /webhooks/cloudflare endpoint.
    
    The raw_content field contains the full RFC 5322 email (headers + body)
    which needs to be parsed to extract HTML and Message-Id.
    """
    from_field: str = Field(..., alias="from")
    to: str
    subject: str
    timestamp: str
    raw_content: str

    class Config:
        populate_by_name = True  # Allow both alias and field name
