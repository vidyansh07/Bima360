"""
AWS Cognito JWT verification.
Fetches JWKS from Cognito and verifies RS256 JWT tokens.
JWKS is cached in-memory for 1 hour to avoid per-request HTTP calls.
"""
import time
import logging
from typing import Optional

import httpx
from jose import JWTError, jwt

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Module-level JWKS cache: pool_url -> (jwks_dict, expires_at_unix)
_jwks_cache: dict[str, tuple[dict, float]] = {}
_JWKS_TTL_SECONDS = 3600


def _pool_url(pool_id: str) -> str:
    return f"https://cognito-idp.{settings.AWS_REGION}.amazonaws.com/{pool_id}"


async def _fetch_jwks(pool_id: str) -> dict:
    """Fetch JWKS from Cognito, using in-memory cache."""
    url = _pool_url(pool_id)
    now = time.monotonic()

    if url in _jwks_cache:
        cached_data, expires_at = _jwks_cache[url]
        if now < expires_at:
            return cached_data

    jwks_url = f"{url}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        data = resp.json()

    _jwks_cache[url] = (data, now + _JWKS_TTL_SECONDS)
    logger.debug("JWKS refreshed for pool %s", pool_id)
    return data


async def verify_cognito_token(token: str, pool_id: str) -> dict:
    """
    Verify a Cognito JWT and return decoded claims.
    Raises jose.JWTError if the token is invalid, expired, or from the wrong pool.
    """
    # Decode header without verification to get kid
    try:
        headers = jwt.get_unverified_headers(token)
    except Exception as exc:
        raise JWTError(f"Cannot decode token headers: {exc}") from exc

    kid = headers.get("kid")
    if not kid:
        raise JWTError("Token header missing 'kid'")

    jwks = await _fetch_jwks(pool_id)

    matching_key: Optional[dict] = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            matching_key = key
            break

    if not matching_key:
        # Force refresh and retry once (key rotation)
        _jwks_cache.pop(_pool_url(pool_id), None)
        jwks = await _fetch_jwks(pool_id)
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                matching_key = key
                break

    if not matching_key:
        raise JWTError("Public key not found in Cognito JWKS")

    expected_issuer = _pool_url(pool_id)

    try:
        claims = jwt.decode(
            token,
            matching_key,
            algorithms=["RS256"],
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise JWTError(f"Token verification failed: {exc}") from exc

    if claims.get("iss") != expected_issuer:
        raise JWTError(
            f"Issuer mismatch: expected {expected_issuer}, got {claims.get('iss')}"
        )

    if claims.get("token_use") not in ("access", "id"):
        raise JWTError("Invalid token_use claim")

    return claims
