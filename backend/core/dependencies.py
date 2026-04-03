"""
Shared FastAPI dependencies.
Auth stubs here — fully implemented in Phase 01-B when Cognito is wired.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.redis_client import get_redis

bearer_scheme = HTTPBearer()


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validates JWT from AWS Cognito (Agent pool).
    STUB — Phase 01-B replaces this with real Cognito verification.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth not yet implemented — Phase 01-B",
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validates JWT from AWS Cognito (User pool).
    STUB — Phase 01-B replaces this with real Cognito verification.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth not yet implemented — Phase 01-B",
    )
