"""FastAPI application entry point.

Run with::

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.core.database import dispose_db, init_db
from app.services.job_manager import get_job_manager

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Application startup/shutdown lifecycle."""
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting %s v%s (%s); inventory-service=%s; db=%s",
        settings.app_name,
        settings.app_version,
        settings.environment,
        settings.inventory_service_url,
        settings.postgres_db,
    )

    # Create DB tables in non-production mode (use Alembic in production).
    if settings.environment != "production":
        try:
            init_db()
            logger.info("Database tables ensured (dev mode).")
        except Exception:  # noqa: BLE001 - DB is optional at startup
            logger.exception(
                "Could not initialise database tables; running without DB persistence."
            )

    # Eagerly build the job manager singleton so configuration errors surface
    # at startup rather than on the first request.
    manager = get_job_manager()
    yield
    logger.info("Shutting down %s, stopping detection jobs...", settings.app_name)
    manager.shutdown()
    dispose_db()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Vision service that counts cartons and pallets from RTSP streams "
            "or video files using YOLO11 + OpenCV, reports counts to the "
            "inventory-service via REST, and persists detection events to "
            "Postgres. Data flow: Camera -> YOLO -> Inventory API -> Postgres."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/", tags=["root"], summary="Service info")
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "inventory_service": settings.inventory_service_url,
            "database": settings.postgres_db,
        }

    return app


app = create_app()
