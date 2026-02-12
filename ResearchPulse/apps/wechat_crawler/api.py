from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from .database import get_session
from .models import Article
from .tasks import get_status, run_crawl

router = APIRouter()


@router.get("/status")
async def status() -> dict:
    return get_status()


@router.post("/trigger")
async def trigger() -> dict:
    return await run_crawl()


# --- Mitmproxy push endpoint (reserved interface) ---


class PushArticleItem(BaseModel):
    title: str = ""
    author: str = ""
    account_name: str = ""
    account_id: str = ""
    digest: str = ""
    content_url: str
    cover_image_url: str = ""
    publish_time: Optional[datetime] = None
    raw_content_html: str = ""
    read_count: int = 0
    like_count: int = 0


class PushRequest(BaseModel):
    articles: List[PushArticleItem]


@router.post("/push")
async def push_articles(payload: PushRequest) -> dict:
    """Receive articles pushed from mitmproxy interceptor."""
    new_count = 0
    async with get_session() as session:
        for item in payload.articles:
            existing = await session.execute(
                select(Article.id).where(Article.content_url == item.content_url)
            )
            if existing.scalar_one_or_none() is not None:
                continue
            article = Article(
                **item.model_dump(),
                source_type="mitmproxy",
                crawl_time=datetime.now(timezone.utc),
            )
            session.add(article)
            new_count += 1
    return {"status": "ok", "new_articles": new_count}
