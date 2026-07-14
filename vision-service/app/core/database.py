"""Sync SQLAlchemy engine + session factory (lazy initialisation).

A *synchronous* engine (psycopg2) is used intentionally: detection runs in a
dedicated worker thread where blocking I/O is expected, and sync DB access
keeps that thread simple. FastAPI ``def`` endpoints that touch the DB run in
Starlette's threadpool automatically, so the event loop is never blocked.

The engine and session factory are created **lazily** (on first access) so the
FastAPI application can start and serve ``/health`` / ``/docs`` even when
psycopg2 or Postgres is unavailable — the service then degrades to in-memory
operation and logs the failure.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in the infrastructure layer."""

    pass


# Lazily-initialised singletons (created on first access via __getattr__).
_engine: Any = None
_SessionLocal: Any = None


def get_engine() -> Any:
    """Create the sync engine on first call and cache it."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_factory() -> Any:
    """Create the session factory on first call and cache it."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), class_=Session, expire_on_commit=False, autoflush=False
        )
    return _SessionLocal


def __getattr__(name: str) -> Any:
    """Expose ``engine`` and ``SessionLocal`` lazily to legacy importers."""
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped sync session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables (dev/demo). Prefer Alembic migrations in production."""
    Base.metadata.create_all(bind=get_engine())


def dispose_db() -> None:
    """Dispose of the connection pool (call on application shutdown)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


__all__ = [
    "Base",
    "get_engine",
    "get_session_factory",
    "get_db_session",
    "init_db",
    "dispose_db",
]
