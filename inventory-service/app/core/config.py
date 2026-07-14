"""Application configuration.

Settings are loaded from environment variables (and ``.env`` file when
present) using ``pydantic-settings``. A cached singleton is exposed through
``get_settings`` so the same instance is reused across the application.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ----------------------------------------------------- #
    app_name: str = "inventory-service"
    app_version: str = "1.0.0"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    api_v1_prefix: str = "/api/v1"

    # --- Database -------------------------------------------------------- #
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="inventory")
    postgres_password: str = Field(default="inventory")
    postgres_db: str = Field(default="inventory_db")
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)
    db_echo: bool = Field(default=False)

    # --- CORS ------------------------------------------------------------ #
    cors_origins: str = Field(default="*")

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        """Build the SQLAlchemy async PostgreSQL DSN."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins string into a list."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` instance."""
    return Settings()
