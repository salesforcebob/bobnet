"""
Integration tests for the Cloudflare webhook endpoint.

These tests verify that the /webhooks/cloudflare endpoint correctly:
- Accepts JSON payloads
- Verifies X-Custom-Auth header
- Parses raw email content to extract HTML and Message-Id
- Publishes jobs to RabbitMQ
"""
import hashlib
import uuid
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.web import app


def _create_raw_email(
    message_id: str | None = None,
    subject: str = "Test Subject",
    from_addr: str = "sender@example.com",
    to_addr: str = "test+user1@example.com",
    html_body: str | None = "<html><body>Test HTML</body></html>",
    plain_body: str | None = "Test plain text",
    multipart: bool = True,
) -> str:
    """
    Create a raw RFC 5322 email string for testing.
    
    Args:
        message_id: Message-Id header value (generated if None).
        subject: Subject header value.
        from_addr: From header value.
        to_addr: To header value.
        html_body: HTML body content (None to omit).
        plain_body: Plain text body content (None to omit).
        multipart: Whether to create multipart/alternative structure.
        
    Returns:
        Raw email string (headers + body).
    """
    if message_id is None:
        message_id = f"<test-{uuid.uuid4()}@example.com>"
    
    headers = [
        f"Message-Id: {message_id}",
        f"Subject: {subject}",
        f"From: {from_addr}",
        f"To: {to_addr}",
        "Date: Mon, 1 Jan 2024 12:00:00 +0000",
        "MIME-Version: 1.0",
    ]
    
    if multipart and (html_body or plain_body):
        headers.append("Content-Type: multipart/alternative; boundary=\"boundary123\"")
        email_str = "\r\n".join(headers) + "\r\n\r\n"
        
        if plain_body:
            email_str += "--boundary123\r\n"
            email_str += "Content-Type: text/plain; charset=utf-8\r\n"
            email_str += "Content-Transfer-Encoding: 7bit\r\n\r\n"
            email_str += plain_body + "\r\n"
        
        if html_body:
            email_str += "--boundary123\r\n"
            email_str += "Content-Type: text/html; charset=utf-8\r\n"
            email_str += "Content-Transfer-Encoding: 7bit\r\n\r\n"
            email_str += html_body + "\r\n"
        
        email_str += "--boundary123--\r\n"
    elif html_body:
        headers.append("Content-Type: text/html; charset=utf-8")
        email_str = "\r\n".join(headers) + "\r\n\r\n"
        email_str += html_body + "\r\n"
    elif plain_body:
        headers.append("Content-Type: text/plain; charset=utf-8")
        email_str = "\r\n".join(headers) + "\r\n\r\n"
        email_str += plain_body + "\r\n"
    else:
        email_str = "\r\n".join(headers) + "\r\n\r\n"
    
    return email_str


def _create_cloudflare_payload(
    to_addr: str = "test+user1@example.com",
    from_addr: str = "sender@example.com",
    subject: str = "Test Subject",
    raw_content: str | None = None,
    message_id: str | None = None,
    html_body: str | None = "<html><body>Test HTML</body></html>",
) -> dict:
    """
    Create a Cloudflare-style JSON payload for testing.
    
    Args:
        to_addr: The email recipient.
        from_addr: The email sender.
        subject: The email subject.
        raw_content: Raw email content (generated if None).
        message_id: Message-Id for raw email generation.
        html_body: HTML body for raw email generation.
        
    Returns:
        Dictionary suitable for JSON POST.
    """
    if raw_content is None:
        raw_content = _create_raw_email(
            message_id=message_id,
            subject=subject,
            from_addr=from_addr,
            to_addr=to_addr,
            html_body=html_body,
        )
    
    return {
        "from": from_addr,
        "to": to_addr,
        "subject": subject,
        "timestamp": "2024-01-01T12:00:00Z",
        "raw_content": raw_content,
    }


class TestCloudflareWebhookBasic:
    """Basic functionality tests."""

    @patch("app.web.publish_job")
    def test_webhook_accepts_valid_payload(self, mock_publish, monkeypatch):
        """Valid Cloudflare payload should be accepted and published."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        payload = _create_cloudflare_payload()
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

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

    def test_webhook_requires_auth_header(self, monkeypatch):
        """Request without X-Custom-Auth header should fail with 401."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        payload = _create_cloudflare_payload()
        
        resp = client.post("/webhooks/cloudflare", json=payload)
        assert resp.status_code == 401
        assert "invalid authentication" in resp.json()["detail"]

    def test_webhook_rejects_invalid_auth_header(self, monkeypatch):
        """Request with wrong X-Custom-Auth header should fail with 401."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        payload = _create_cloudflare_payload()
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "wrong-token"},
        )
        assert resp.status_code == 401
        assert "invalid authentication" in resp.json()["detail"]

    @patch("app.web.publish_job")
    def test_webhook_uses_default_auth_token(self, mock_publish, monkeypatch):
        """Webhook should use default auth token when env var not set."""
        monkeypatch.delenv("CLOUDFLARE_AUTH_TOKEN", raising=False)
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        payload = _create_cloudflare_payload()
        
        # Default token is "b0b-th3-build3r"
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "b0b-th3-build3r"},
        )
        assert resp.status_code == 200

    def test_webhook_requires_json_payload(self, monkeypatch):
        """Request with invalid JSON should fail with 422."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        client = TestClient(app)
        
        resp = client.post(
            "/webhooks/cloudflare",
            data="not json",
            headers={"X-Custom-Auth": "test-token", "Content-Type": "application/json"},
        )
        assert resp.status_code == 422


class TestCloudflareWebhookEmailParsing:
    """Tests for email parsing functionality."""

    @patch("app.web.publish_job")
    def test_extracts_message_id_from_headers(self, mock_publish, monkeypatch):
        """Message-Id should be extracted from email headers."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        expected_message_id = "<unique-test-id@example.com>"
        raw_content = _create_raw_email(message_id=expected_message_id)
        payload = _create_cloudflare_payload(raw_content=raw_content)
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

        assert resp.status_code == 200
        
        # Verify the extracted message_id was passed to publish_job
        job_payload = mock_publish.call_args[0][0]
        assert job_payload["message_id"] == expected_message_id.strip("<>")

    @patch("app.web.publish_job")
    def test_generates_message_id_fallback(self, mock_publish, monkeypatch):
        """Message-Id should be generated if missing from headers."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        # Create raw email without Message-Id header
        raw_content = _create_raw_email(message_id=None)
        # Remove Message-Id line
        raw_content = "\n".join(
            line for line in raw_content.split("\n")
            if not line.startswith("Message-Id:")
        )
        payload = _create_cloudflare_payload(
            raw_content=raw_content,
            subject="Test Subject",
            to_addr="test@example.com",
        )
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

        assert resp.status_code == 200
        
        # Verify fallback message_id was generated
        job_payload = mock_publish.call_args[0][0]
        expected_hash = hashlib.sha256("Test Subject-test@example.com".encode("utf-8")).hexdigest()
        assert job_payload["message_id"] == expected_hash

    @patch("app.web.publish_job")
    def test_extracts_html_from_multipart(self, mock_publish, monkeypatch):
        """HTML should be extracted from multipart/alternative email."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        html_content = "<html><body>Test HTML Content</body></html>"
        raw_content = _create_raw_email(html_body=html_content, multipart=True)
        payload = _create_cloudflare_payload(raw_content=raw_content)
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

        assert resp.status_code == 200
        
        # Verify HTML was extracted and passed to publish_job
        job_payload = mock_publish.call_args[0][0]
        assert job_payload["html"] == html_content

    @patch("app.web.publish_job")
    def test_extracts_html_from_direct_html(self, mock_publish, monkeypatch):
        """HTML should be extracted from direct text/html email."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        html_content = "<html><body>Direct HTML</body></html>"
        raw_content = _create_raw_email(html_body=html_content, multipart=False, plain_body=None)
        payload = _create_cloudflare_payload(raw_content=raw_content)
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

        assert resp.status_code == 200
        
        # Verify HTML was extracted
        job_payload = mock_publish.call_args[0][0]
        assert job_payload["html"] == html_content

    @patch("app.web.publish_job")
    def test_handles_plain_text_only(self, mock_publish, monkeypatch):
        """Plain text emails should result in None HTML."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        raw_content = _create_raw_email(html_body=None, plain_body="Plain text only", multipart=True)
        payload = _create_cloudflare_payload(raw_content=raw_content)
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

        assert resp.status_code == 200
        
        # Verify HTML is None for plain text emails
        job_payload = mock_publish.call_args[0][0]
        assert job_payload["html"] is None

    @patch("app.web.publish_job")
    def test_handles_malformed_email(self, mock_publish, monkeypatch):
        """Malformed email should still be processed (with fallback values)."""
        monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "test-token")
        from app.config import Settings
        monkeypatch.setattr("app.web.settings", Settings())

        mock_publish.return_value = "test-message-id"
        
        client = TestClient(app)
        # Invalid email format
        payload = _create_cloudflare_payload(
            raw_content="not a valid email",
            subject="Test",
            to_addr="test@example.com",
        )
        
        resp = client.post(
            "/webhooks/cloudflare",
            json=payload,
            headers={"X-Custom-Auth": "test-token"},
        )

        assert resp.status_code == 200
        
        # Should still publish with fallback message_id
        job_payload = mock_publish.call_args[0][0]
        assert "message_id" in job_payload
        assert job_payload["to"] == "test@example.com"
