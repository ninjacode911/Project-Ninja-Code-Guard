"""
GitHub App Authentication
==========================

GitHub Apps authenticate via a two-step process:

1. **JWT Generation**: We create a JSON Web Token (JWT) signed with our private key
   (.pem file). This JWT proves we are the registered GitHub App. It's valid for
   max 10 minutes — intentionally short-lived for security.

2. **Installation Access Token**: We exchange the JWT for an installation access token
   via GitHub's API. This token is scoped to a specific installation (a specific set
   of repos where the app is installed) and lasts 1 hour.

Why two steps? A GitHub App can be installed on hundreds of orgs/repos. The JWT says
"I am CodeProbe app" — the installation token says "I have permission to access
@ninjacode911's repos specifically." This separation of identity vs. authorization
is a production-grade security pattern (similar to OAuth2 client credentials).

We cache the installation token in memory and refresh it when it expires, so we
don't make unnecessary API calls.

Reference: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app
"""

import asyncio
import time
from pathlib import Path

import httpx
import jwt  # PyJWT library — used to create JSON Web Tokens

from app.config import settings

# In-memory cache for installation tokens
_token_cache: dict[int, dict] = {}

# Asyncio lock to prevent race conditions on token cache
_token_lock = asyncio.Lock()

# Cached private key (read from disk once, reused)
_private_key: str | None = None

# GitHub API base URL
GITHUB_API = "https://api.github.com"


def _generate_jwt() -> str:
    """
    Generate a JWT (JSON Web Token) signed with our GitHub App's private key.

    A JWT has three parts (separated by dots):
    1. Header: algorithm (RS256) and token type
    2. Payload: who we are (iss = app ID), when issued, when it expires
    3. Signature: the header+payload signed with our RSA private key

    GitHub verifies the signature using our app's public key (which GitHub stores
    when we register the app). This is asymmetric cryptography — we sign with the
    private key, GitHub verifies with the public key.

    RS256 = RSA + SHA-256 — the industry standard for JWT signing.
    """
    now = int(time.time())

    # Cache the private key in memory after first read
    global _private_key
    if _private_key is None:
        if settings.github_app_private_key:
            # Cloud deployment: key content passed directly via env var
            # HF Spaces may strip newlines — restore them if needed
            key = settings.github_app_private_key
            if "\\n" in key:
                key = key.replace("\\n", "\n")
            _private_key = key
        else:
            # Local development: read from .pem file
            project_root = Path(__file__).resolve().parent.parent.parent
            private_key_path = project_root / settings.github_app_private_key_path
            _private_key = private_key_path.read_text()

    payload = {
        # iat = "issued at" — when this token was created
        "iat": now - 60,  # 60 seconds in the past to account for clock drift
        # exp = "expires at" — GitHub rejects JWTs older than 10 minutes
        "exp": now + (9 * 60),  # 9 minutes (safely under the 10-min limit)
        # iss = "issuer" — our GitHub App ID, proving which app we are
        "iss": settings.github_app_id,
    }

    # Sign the JWT with our private RSA key using RS256 algorithm
    return jwt.encode(payload, _private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """
    Get an installation access token for a specific GitHub App installation.

    This token is what we actually use to call GitHub APIs (fetch PRs, post comments).
    It's scoped to the specific repos where the app is installed.

    We cache tokens in memory and reuse them until they expire (1 hour lifetime).
    This avoids making a new token request for every API call.

    Args:
        installation_id: The GitHub installation ID (sent in webhook payloads).
                         Each org/user that installs our app gets a unique ID.

    Returns:
        A valid installation access token string.
    """
    # Check cache first (outside lock for fast path)
    cached = _token_cache.get(installation_id)
    if cached and cached["expires_at"] > time.time() + 60:
        return cached["token"]

    # Lock prevents race condition: two coroutines seeing cache miss simultaneously
    async with _token_lock:
        # Double-check inside lock (another coroutine may have filled the cache)
        cached = _token_cache.get(installation_id)
        if cached and cached["expires_at"] > time.time() + 60:
            return cached["token"]

        app_jwt = _generate_jwt()

        # Exchange the JWT for an installation-scoped access token
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()

        # Cache the token
        _token_cache[installation_id] = {
            "token": data["token"],
            "expires_at": time.time() + 3500,
        }

        return data["token"]
