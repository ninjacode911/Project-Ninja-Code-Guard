"""
GitHub Webhook Signature Validation
====================================

When GitHub sends a webhook event to our server, it includes a cryptographic
signature in the `X-Hub-Signature-256` header. This signature proves the request
genuinely came from GitHub, not from an attacker.

The signature is computed as: HMAC-SHA256(webhook_secret, request_body)

We recompute the same HMAC on our side and compare. If they match, the request
is authentic. We use `hmac.compare_digest()` for constant-time comparison to
prevent timing attacks — where an attacker measures response time differences
to guess the signature byte by byte.

Reference: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
"""

import hashlib
import hmac

from fastapi import Header, HTTPException, Request

from app.config import settings


async def validate_webhook_signature(
    request: Request,
    x_hub_signature_256: str = Header(..., alias="X-Hub-Signature-256"),
) -> bytes:
    """
    FastAPI dependency that validates the GitHub webhook HMAC-SHA256 signature.

    How this works as a FastAPI dependency:
    - FastAPI's dependency injection system calls this function before your endpoint runs
    - It automatically extracts the X-Hub-Signature-256 header from the request
    - If validation fails, it raises HTTPException and the endpoint never executes
    - If it passes, it returns the raw request body for further processing

    Args:
        request: The incoming FastAPI request object (injected automatically)
        x_hub_signature_256: The signature header from GitHub (extracted by FastAPI)

    Returns:
        The raw request body bytes (so the endpoint can parse it as JSON)

    Raises:
        HTTPException 401: If the signature is missing or invalid
    """
    # Read the raw request body — we need the exact bytes GitHub used to compute the HMAC.
    # Important: we read raw bytes, NOT parsed JSON, because even a single whitespace
    # difference would produce a completely different HMAC hash.
    body = await request.body()

    # Reject if webhook secret is not configured — empty secret = no security
    if not settings.github_webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing webhook signature header")

    # GitHub sends the signature as "sha256=<hex_digest>"
    # We need to strip the "sha256=" prefix to get just the hex digest
    if not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid signature format")

    received_signature = x_hub_signature_256[7:]  # Strip "sha256=" prefix

    # Compute the expected HMAC using our stored webhook secret
    # hmac.new() takes: key (bytes), message (bytes), hash algorithm
    expected_signature = hmac.new(
        key=settings.github_webhook_secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison — this is critical for security.
    # A naive `==` comparison short-circuits on the first different byte,
    # which leaks timing information. compare_digest() always takes the
    # same amount of time regardless of where the mismatch is.
    if not hmac.compare_digest(expected_signature, received_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    return body
