"""API-key authentication for the vision-service HTTP API.

Every ``/api/v1`` route requires the ``X-API-Key`` header to match the
configured ``API_KEY``. When no key is configured the service refuses
authenticated traffic in production (fail closed) and stays open in
development so the demo stack keeps working out of the box.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings

API_KEY_HEADER = "X-API-Key"


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    """FastAPI dependency enforcing the shared-secret API key."""
    settings = get_settings()
    expected = settings.api_key.strip()

    if not expected:
        if settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "API_KEY is not configured; refusing to serve the API "
                    "without authentication."
                ),
            )
        return

    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing or invalid {API_KEY_HEADER} header.",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


__all__ = ["require_api_key", "API_KEY_HEADER"]
