from typing import Any, Dict, Optional
from pydantic import BaseModel


class Envelope(BaseModel):
    to: str


class IncomingMail(BaseModel):
    envelope: Envelope
    headers: Optional[Dict[str, Any]] = None
    html: Optional[str] = None
    plain: Optional[str] = None
