"""FastAPI application entry point.

Run with::

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import dispose_db, init_db
from app.core.security import require_api_key
from app.presentation.api.router import api_v1_router

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Application startup/shutdown lifecycle."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting %s v%s (%s)...", settings.app_name, settings.app_version, settings.environment)

    if not settings.api_key.strip():
        logger.warning(
            "API_KEY is not set: the API is unauthenticated and will reject "
            "every request when ENVIRONMENT=production."
        )

    if settings.environment != "production":
        logger.info("Auto-creating database tables (dev mode).")
        try:
            await init_db()
        except Exception:  # noqa: BLE001 - DB is optional at startup
            logger.exception(
                "Could not initialise database tables; running without DB persistence."
            )

    yield

    logger.info("Disposing database connection pool...")
    try:
        await dispose_db()
    except Exception:  # noqa: BLE001
        logger.exception("Error disposing database connection pool.")
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Inventory service following Clean Architecture. "
            "Provides CRUD + restock/consume operations for inventory items."
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    cors_origins = settings.cors_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        # Credentials cannot be combined with a wildcard origin.
        allow_credentials="*" not in cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    app.include_router(
        api_v1_router,
        prefix=settings.api_v1_prefix,
        dependencies=[Depends(require_api_key)],
    )

    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/", tags=["root"], summary="Service info")
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }

    return app


app = create_app()
