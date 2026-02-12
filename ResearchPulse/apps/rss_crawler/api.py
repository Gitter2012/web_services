from __future__ import annotations

from fastapi import APIRouter

from .tasks import get_status, run_crawl

router = APIRouter()


@router.get("/status")
async def status() -> dict:
    return get_status()


@router.post("/trigger")
async def trigger() -> dict:
    return await run_crawl()


@router.post("/import_opml")
async def import_opml() -> dict:
    """Import feeds from an OPML file (placeholder)."""
    return {"status": "not_implemented"}
