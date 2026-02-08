from __future__ import annotations

import asyncio
from fastapi import APIRouter

from .tasks import get_status, run_crawl

router = APIRouter()


@router.get("/status")
async def status() -> dict:
    return get_status()


@router.post("/trigger")
async def trigger() -> dict:
    return await asyncio.to_thread(run_crawl)
