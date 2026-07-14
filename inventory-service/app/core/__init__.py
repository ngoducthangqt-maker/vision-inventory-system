"""Core layer: cross-cutting concerns (configuration, database, logging...)."""

from app.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
