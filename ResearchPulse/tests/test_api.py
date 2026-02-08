from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from apps.arxiv_crawler import api


@pytest.mark.asyncio
async def test_status_endpoint() -> None:
    app = FastAPI()
    app.include_router(api.router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/status")
        assert response.status_code == 200
        assert "last_run_at" in response.json()


@pytest.mark.asyncio
async def test_trigger_endpoint(monkeypatch) -> None:
    def fake_run_crawl():
        return {"ok": True}

    monkeypatch.setattr(api, "run_crawl", fake_run_crawl)

    app = FastAPI()
    app.include_router(api.router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/trigger")
        assert response.status_code == 200
        assert response.json()["ok"] is True
