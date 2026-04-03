"""
Async Redis client.
Key naming convention (always use these builders, never raw strings):
  bot_session:{user_id}    TTL 30 min  — conversation history
  risk_cache:{hash}        TTL 24h     — cached risk scores
  rate_limit:{agent_id}    TTL 1h      — AI API call counter
  jwt_blacklist:{jti}      TTL = token expiry
"""
from typing import Optional
import redis.asyncio as aioredis
from backend.core.config import settings

_redis_client: Optional[aioredis.Redis] = None


async def init_redis() -> None:
    global _redis_client
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis_client.ping()


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> aioredis.Redis:
    """FastAPI dependency. Usage: redis: Redis = Depends(get_redis)"""
    if _redis_client is None:
        raise RuntimeError("Redis not initialised.")
    return _redis_client


# ── Key builders ─────────────────────────────────────────────
def bot_session_key(user_id: str) -> str:
    return f"bot_session:{user_id}"

def risk_cache_key(input_hash: str) -> str:
    return f"risk_cache:{input_hash}"

def rate_limit_key(agent_id: str) -> str:
    return f"rate_limit:{agent_id}"

def jwt_blacklist_key(jti: str) -> str:
    return f"jwt_blacklist:{jti}"
