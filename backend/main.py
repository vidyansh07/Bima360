"""
Bima360 FastAPI application entry point.
Routes are registered here as phases are completed.
Business logic never lives here — only in /services/.
"""
import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.database import init_db
from backend.core.redis_client import close_redis, init_redis
from backend.routers import health

logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

if settings.SENTRY_DSN and settings.ENVIRONMENT == "production":
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.2,
        environment=settings.ENVIRONMENT,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Bima360 API...")
    await init_db()
    logger.info("✓ PostgreSQL connected")
    await init_redis()
    logger.info("✓ Redis connected")
    logger.info(f"✓ Ready — environment: {settings.ENVIRONMENT}")
    yield
    logger.info("Shutting down...")
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI + Blockchain Micro-Insurance for Rural India.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "data": None, "error": "Internal server error"},
    )


# ── Routers — uncomment as phases complete ───────────────────
app.include_router(health.router)
# Phase 01-B: app.include_router(auth.router, prefix="/api/v1/auth")
# Phase 02:   app.include_router(ai.router,   prefix="/api/v1/ai")
# Phase 02-03:app.include_router(policies.router, prefix="/api/v1/policies")
# Phase 03:   app.include_router(claims.router,   prefix="/api/v1/claims")
# Phase 03:   app.include_router(payments.router, prefix="/api/v1/payments")
