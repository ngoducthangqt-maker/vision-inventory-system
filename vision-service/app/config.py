"""Application configuration.

Settings are loaded from environment variables (and ``.env`` when present)
using ``pydantic-settings``. A cached singleton is exposed via
``get_settings``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
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
    app_name: str = "vision-service"
    app_version: str = "1.0.0"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    api_v1_prefix: str = "/api/v1"

    # --- CORS ------------------------------------------------------------ #
    cors_origins: str = Field(default="*")

    # --- PostgreSQL (vision-service own DB: jobs + detection events) ---- #
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="vision")
    postgres_password: str = Field(default="vision")
    postgres_db: str = Field(default="vision_db")
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)
    db_echo: bool = Field(default=False)
    # "inmemory" -> use InMemoryJobRepository (no Postgres needed); for demos/tests.
    repository_mode: str = Field(default="postgres")

    # --- YOLO11 / detection --------------------------------------------- #
    # Path/identifier of the YOLO11 model. The ultralytics package will
    # auto-download official weights (e.g. "yolo11n.pt") on first use.
    # For accurate carton detection, point this to a model fine-tuned on
    # carton data.
    default_model_path: str = Field(default="yolo11n.pt")
    # Class names (lower-cased, matched loosely) that should be counted as a
    # "carton". Override according to the classes your custom model emits.
    default_carton_class_names: str = Field(
        default="carton,box,cardboard box",
        description="Comma-separated class names counted as cartons.",
    )
    # Tracker config used by ``model.track`` (ByteTrack / BoT-SORT).
    tracker_config: str = Field(default="bytetrack.yaml")
    # Confidence threshold for accepting a detection.
    confidence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    # Process 1 frame every N to reduce CPU load on continuous streams.
    default_frame_sample_interval: int = Field(default=5, ge=1)
    # How often (seconds) the running count delta is reported upstream.
    default_report_interval_seconds: float = Field(default=10.0, ge=1.0)
    # Whether to draw bounding boxes on a debug frame (kept in memory).
    enable_debug_frames: bool = Field(default=False)

    # --- inventory-service integration ---------------------------------- #
    # Base URL of the inventory-service REST API.
    inventory_service_url: str = Field(default="http://localhost:8000")
    inventory_api_prefix: str = Field(default="/api/v1")
    inventory_request_timeout_seconds: float = Field(default=10.0, ge=1.0)

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        """Sync SQLAlchemy PostgreSQL DSN (psycopg2 driver)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def carton_class_names_list(self) -> list[str]:
        """Parse the comma-separated carton class names into a clean list."""
        return [c.strip().lower() for c in self.default_carton_class_names.split(",") if c.strip()]

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
