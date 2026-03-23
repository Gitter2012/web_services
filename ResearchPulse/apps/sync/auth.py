"""API Key authentication for sync endpoints."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from settings import settings


async def verify_sync_api_key(
    x_sync_api_key: str | None = Header(default=None),
) -> bool:
    """Verify sync API key from request header.

    Validates the X-Sync-API-Key header against the configured key.
    Returns True on success, raises HTTPException on failure.
    """
    expected_key = settings.sync_receiver_api_key
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sync receiver not configured (no API key set)",
        )
    if not x_sync_api_key or x_sync_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid sync API key",
        )
    return True
