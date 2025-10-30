import os
import uuid
from fastapi.testclient import TestClient
from app.web import app


def test_webhook_enqueues_job(monkeypatch):
    # Requires Redis running / REDIS_URL set to a valid instance
    client = TestClient(app)

    payload = {
        "headers": {"message_id": f"<test-{uuid.uuid4()}@example.com>", "subject": "Hello"},
        "envelope": {"to": "c96be77c591e99f5c6bf+it@cloudmailin.net"},
        "html": "<html><img src=\"https://example.com/p.png\"></html>",
    }

    resp = client.post("/webhooks/cloudmailin", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] in ("enqueued", "duplicate")
    assert "message_id" in data
