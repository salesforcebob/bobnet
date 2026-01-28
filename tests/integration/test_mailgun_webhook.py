"""
Integration tests for the Mailgun webhook endpoint.

These tests verify that the /webhooks/mailgun endpoint correctly:
- Accepts form-encoded payloads
- Verifies signatures when configured
- Publishes jobs to RabbitMQ
"""
import hashlib
import hmac
import time
import uuid
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.web import app


def _generate_signature(signing_key: str, timestamp: str, token: str) -> str:
    """Helper to generate a valid Mailgun signature for testing."""
    return hmac.new(
        key=signing_key.encode("utf-8"),
        msg=f"{timestamp}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def _create_mailgun_payload(
    recipient: str = "test+user1@example.com",
    sender: str = "sender@example.com",
    subject: str = "Test Subject",
    body_html: str = "<html><body>Test</body></html>",
    message_id: str | None = None,
    include_signature: bool = False,
    signing_key: str | None = None,
) -> dict:
    """
    Create a Mailgun-style form payload for testing.

    Args:
        recipient: The email recipient.
        sender: The email sender.
        subject: The email subject.
        body_html: The HTML body content.
        message_id: Optional Message-Id to include in headers.
        include_signature: Whether to include signature fields.
        signing_key: Key to use for generating signature.

    Returns:
        Dictionary suitable for form-encoded POST.
    """
    payload = {
        "recipient": recipient,
        "sender": sender,
        "subject": subject,
        "body-html": body_html,
        "body-plain": "Test plain text",
    }

    # Add message headers with Message-Id if provided
    if message_id:
        payload["message-headers"] = f'[["Message-Id", "{message_id}"], ["Subject", "{subject}"]]'
    else:
        # Generate unique message ID for test isolation
        payload["message-headers"] = f'[["Message-Id", "<test-{uuid.uuid4()}@example.com>"]]'

    # Add signature fields if requested
    if include_signature and signing_key:
        timestamp = str(int(time.time()))
        token = f"test-token-{uuid.uuid4().hex[:20]}"
        signature = _generate_signature(signing_key, timestamp, token)
        payload["timestamp"] = timestamp
        payload["token"] = token
        payload["signature"] = signature
    else:
        # Include empty signature fields (required form fields)
        payload["timestamp"] = ""
        payload["token"] = ""
        payload["signature"] = ""

    return payload


class TestMailgunWebhookBasic:
    """Basic functionality tests (without signature verification)."""

    @patch("app.web.publish_job")
    def test_webhook_accepts_valid_payload(self, mock_publish, monkeypatch):
        """Valid Mailgun payload should be accepted and published."""
        # Disable signature verification for this test
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "")
        monkeypatch.setenv("MAILGUN_DOMAIN", "")

        # Need to reload settings after env change
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        payload = _create_mailgun_payload()

        resp = client.post("/webhooks/mailgun", data=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "enqueued"
        assert "message_id" in data
        
        # Verify publish_job was called with correct payload structure
        mock_publish.assert_called_once()
        job_payload = mock_publish.call_args[0][0]
        assert "message_id" in job_payload
        assert "to" in job_payload
        assert "html" in job_payload

    def test_webhook_requires_recipient(self, monkeypatch):
        """Request without recipient should fail with 422."""
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        # Payload missing required 'recipient' field
        payload = {
            "sender": "test@example.com",
            "body-html": "<html></html>",
        }

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 422  # Validation error

    @patch("app.web.publish_job")
    def test_webhook_extracts_message_id_from_headers(self, mock_publish, monkeypatch):
        """Message-Id should be extracted from Mailgun headers."""
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "")
        monkeypatch.setenv("MAILGUN_DOMAIN", "")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        expected_message_id = "<unique-test-id@example.com>"
        payload = _create_mailgun_payload(message_id=expected_message_id)

        resp = client.post("/webhooks/mailgun", data=payload)

        assert resp.status_code == 200
        
        # Verify the extracted message_id was passed to publish_job
        job_payload = mock_publish.call_args[0][0]
        assert job_payload["message_id"] == expected_message_id


class TestMailgunWebhookSignatureVerification:
    """Tests for signature verification."""

    @patch("app.web.publish_job")
    def test_valid_signature_accepted(self, mock_publish, monkeypatch):
        """Request with valid signature should be accepted."""
        signing_key = "test-signing-key-for-verification"
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", signing_key)
        monkeypatch.setenv("MAILGUN_DOMAIN", "")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        payload = _create_mailgun_payload(
            include_signature=True,
            signing_key=signing_key,
        )

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "enqueued"

    def test_invalid_signature_rejected(self, monkeypatch):
        """Request with invalid signature should be rejected with 401."""
        signing_key = "test-signing-key-for-verification"
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", signing_key)
        monkeypatch.setenv("MAILGUN_DOMAIN", "")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        # Generate payload with wrong signing key
        payload = _create_mailgun_payload(
            include_signature=True,
            signing_key="wrong-key",
        )

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 401
        assert "invalid signature" in resp.json()["detail"]

    def test_missing_signature_rejected_when_key_configured(self, monkeypatch):
        """Request without signature should be rejected when key is configured."""
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "my-signing-key")
        monkeypatch.setenv("MAILGUN_DOMAIN", "")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        # Payload without signature fields
        payload = _create_mailgun_payload(include_signature=False)

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 401


class TestMailgunWebhookDomainValidation:
    """Tests for recipient domain validation."""

    @patch("app.web.publish_job")
    def test_valid_domain_accepted(self, mock_publish, monkeypatch):
        """Recipient matching configured domain should be accepted."""
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "")
        monkeypatch.setenv("MAILGUN_DOMAIN", "inbound.example.com")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        payload = _create_mailgun_payload(recipient="user+tag@inbound.example.com")

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 200

    def test_invalid_domain_rejected(self, monkeypatch):
        """Recipient not matching configured domain should be rejected."""
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "")
        monkeypatch.setenv("MAILGUN_DOMAIN", "inbound.example.com")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        payload = _create_mailgun_payload(recipient="user@wrong-domain.com")

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 400
        assert "invalid recipient domain" in resp.json()["detail"]

    @patch("app.web.publish_job")
    def test_no_domain_validation_when_not_configured(self, mock_publish, monkeypatch):
        """Any domain should be accepted when MAILGUN_DOMAIN is not set."""
        monkeypatch.setenv("MAILGUN_SIGNING_KEY", "")
        monkeypatch.setenv("MAILGUN_DOMAIN", "")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        payload = _create_mailgun_payload(recipient="anyone@any-domain.com")

        resp = client.post("/webhooks/mailgun", data=payload)
        assert resp.status_code == 200
