"""
Health check endpoints.
/health         — lightweight, always 200 (used by Docker HEALTHCHECK and load balancers)
/health/detailed — checks Postgres + Redis health
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.redis_client import get_redis
from backend.core.responses import ok

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    """Lightweight liveness probe — always returns 200 if the process is up."""
    return ok({"status": "ok"})


@router.get("/health/detailed")
async def health_detailed(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Readiness probe — checks DB and Redis connectivity."""
    services: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as e:
        services["postgres"] = f"error: {e}"

    try:
        await redis.ping()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return ok({"status": overall, "services": services})
