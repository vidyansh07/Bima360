"""Shared pytest fixtures for all backend tests."""
import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.main import app
from backend.models.models import Base

# ── In-memory SQLite engine (avoids needing a real PG instance) ───────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DB_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Return an AsyncClient wired to the FastAPI app, with auth bypassed."""
    from backend.core.dependencies import get_current_agent

    async def _mock_agent():
        return {"sub": "agent-test-001", "user_type": "agent", "email": "test@bima360.in"}

    app.dependency_overrides[get_current_agent] = _mock_agent
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    with patch("backend.core.redis_client.get_redis") as mock:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.set.return_value = True
        redis.incr.return_value = 1
        redis.expire.return_value = True
        mock.return_value = redis
        yield redis


@pytest.fixture
def mock_s3():
    with patch("boto3.client") as mock:
        s3 = MagicMock()
        s3.generate_presigned_url.return_value = "https://example.s3.amazonaws.com/test"
        mock.return_value = s3
        yield s3
