"""
Tests for GitHub webhook HMAC-SHA256 signature validation.

These tests verify that:
1. Valid signatures are accepted
2. Invalid signatures are rejected (401)
3. Missing signature headers are rejected (422)
4. Wrong format signatures are rejected (401)

This is a security-critical component — if validation is broken, an attacker
could trigger fake reviews or waste our Groq API quota by sending fabricated
webhook payloads.

How the test works:
- We use FastAPI's TestClient which simulates HTTP requests without a real server
- We compute the correct HMAC signature ourselves using the test secret
- We verify the endpoint accepts valid signatures and rejects invalid ones
"""

import hashlib
import hmac
import json

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.github.webhook import validate_webhook_signature


# Create a minimal FastAPI app just for testing the webhook dependency
# This isolates the test from the rest of the application
test_app = FastAPI()

# We need to override the settings for testing — we don't want to use
# the real webhook secret from .env
TEST_SECRET = "test_webhook_secret_for_unit_tests"


@test_app.post("/test-webhook")
async def webhook_endpoint(body: bytes = Depends(validate_webhook_signature)):
    """A dummy endpoint that uses the webhook validation dependency."""
    return {"status": "ok", "body_length": len(body)}


def _compute_signature(payload: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 signature the same way GitHub does."""
    signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


@pytest.fixture
def client(monkeypatch):
    """
    Create a test client with a known webhook secret.

    monkeypatch temporarily overrides settings.github_webhook_secret
    so our tests use a predictable secret instead of the real one.
    """
    monkeypatch.setattr(
        "app.github.webhook.settings.github_webhook_secret",
        TEST_SECRET,
    )
    return TestClient(test_app)


class TestWebhookValidation:
    def test_valid_signature_accepted(self, client):
        """A correctly signed payload should return 200."""
        payload = json.dumps({"action": "opened"}).encode()
        signature = _compute_signature(payload, TEST_SECRET)

        response = client.post(
            "/test-webhook",
            content=payload,
            headers={"X-Hub-Signature-256": signature},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_invalid_signature_rejected(self, client):
        """A payload signed with the wrong secret should return 401."""
        payload = json.dumps({"action": "opened"}).encode()
        wrong_signature = _compute_signature(payload, "wrong_secret")

        response = client.post(
            "/test-webhook",
            content=payload,
            headers={"X-Hub-Signature-256": wrong_signature},
        )
        assert response.status_code == 401

    def test_tampered_payload_rejected(self, client):
        """A valid signature for a DIFFERENT payload should return 401."""
        original_payload = json.dumps({"action": "opened"}).encode()
        signature = _compute_signature(original_payload, TEST_SECRET)

        # Send a different payload but with the original's signature
        tampered_payload = json.dumps({"action": "hacked"}).encode()

        response = client.post(
            "/test-webhook",
            content=tampered_payload,
            headers={"X-Hub-Signature-256": signature},
        )
        assert response.status_code == 401

    def test_missing_signature_rejected(self, client):
        """A request without the signature header should be rejected."""
        payload = json.dumps({"action": "opened"}).encode()

        response = client.post("/test-webhook", content=payload)
        # FastAPI returns 422 (Unprocessable Entity) for missing required headers
        assert response.status_code == 422

    def test_malformed_signature_rejected(self, client):
        """A signature without the 'sha256=' prefix should be rejected."""
        payload = json.dumps({"action": "opened"}).encode()

        response = client.post(
            "/test-webhook",
            content=payload,
            headers={"X-Hub-Signature-256": "not_a_valid_signature"},
        )
        assert response.status_code == 401
