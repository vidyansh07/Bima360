"""
Shared FastAPI dependencies.
get_current_agent — verifies Cognito Agent pool JWT
get_current_user  — verifies Cognito User pool JWT
get_db            — async PostgreSQL session
get_redis         — Redis connection
"""
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import verify_cognito_token
from backend.core.config import settings
from backend.core.database import get_db
from backend.core.redis_client import get_redis

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validates JWT from AWS Cognito Agent pool.
    Returns a dict with sub, user_type='agent', phone, email.
    """
    if not credentials:
        raise _UNAUTHORIZED
    try:
        claims = await verify_cognito_token(
            credentials.credentials,
            settings.AWS_COGNITO_AGENT_POOL_ID,
        )
    except JWTError as exc:
        logger.warning("Agent token rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired agent token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "sub": claims["sub"],
        "user_type": "agent",
        "phone": claims.get("phone_number"),
        "email": claims.get("email"),
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validates JWT from AWS Cognito User pool.
    Returns a dict with sub, user_type='user', phone, email.
    """
    if not credentials:
        raise _UNAUTHORIZED
    try:
        claims = await verify_cognito_token(
            credentials.credentials,
            settings.AWS_COGNITO_USER_POOL_ID,
        )
    except JWTError as exc:
        logger.warning("User token rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired user token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "sub": claims["sub"],
        "user_type": "user",
        "phone": claims.get("phone_number"),
        "email": claims.get("email"),
    }
