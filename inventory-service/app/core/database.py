"""Async database engine and session factory.

We use SQLAlchemy 2.0 style with ``asyncpg`` as the driver. The session
factory is exposed through a FastAPI dependency (``get_db_session``) so each
request gets its own session that is closed automatically.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in the infrastructure layer."""

    pass


settings = get_settings()

# ``future=True`` is the default in SQLAlchemy 2.x but kept explicit for clarity.
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a scoped async session.

    The session is committed when the request handler returns successfully
    and rolled back on any exception, then always closed.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables. Useful for dev/demo; migrations are preferred in prod."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    """Dispose of the connection pool (call on application shutdown)."""
    await engine.dispose()
