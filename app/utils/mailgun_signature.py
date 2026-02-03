"""
Mailgun webhook signature verification utility.

Mailgun signs webhook requests using HMAC-SHA256. This module provides
functions to verify the authenticity of incoming Mailgun webhooks.

Reference: https://documentation.mailgun.com/docs/mailgun/user-manual/events/webhooks/#securing-webhooks
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional


# Maximum age of a webhook signature before it's considered stale (5 minutes)
SIGNATURE_MAX_AGE_SECONDS = 300


def verify_mailgun_signature(
    signing_key: str,
    timestamp: str,
    token: str,
    signature: str,
    max_age_seconds: int = SIGNATURE_MAX_AGE_SECONDS,
) -> bool:
    """
    Verify a Mailgun webhook signature.

    Mailgun webhooks include three fields for signature verification:
    - timestamp: Unix epoch seconds when the webhook was generated
    - token: A randomly generated 50-character string
    - signature: HMAC-SHA256 hex digest of timestamp + token

    Args:
        signing_key: Your Mailgun HTTP webhook signing key (from dashboard).
        timestamp: The 'timestamp' field from the webhook payload.
        token: The 'token' field from the webhook payload.
        signature: The 'signature' field from the webhook payload.
        max_age_seconds: Maximum allowed age of the timestamp (default 5 min).

    Returns:
        True if the signature is valid and not stale, False otherwise.
    """
    if not signing_key or not timestamp or not token or not signature:
        return False

    # Verify timestamp is not stale (prevents replay attacks)
    try:
        webhook_time = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - webhook_time) > max_age_seconds:
            return False
    except (ValueError, TypeError):
        return False

    # Compute expected signature: HMAC-SHA256(signing_key, timestamp + token)
    expected_signature = hmac.new(
        key=signing_key.encode("utf-8"),
        msg=f"{timestamp}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)


def is_signature_verification_enabled(signing_key: Optional[str]) -> bool:
    """
    Check if Mailgun signature verification is enabled.

    Args:
        signing_key: The configured Mailgun signing key.

    Returns:
        True if a signing key is configured, False otherwise.
    """
    return bool(signing_key and signing_key.strip())
