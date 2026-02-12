from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, or_, select

from apps.rss_crawler.database import get_session
from apps.rss_crawler.models import Article, Feed

from .config import settings as ui_settings

logger = logging.getLogger(__name__)

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ---------------------------------------------------------------------------
# Page endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Article list page."""
    return _templates.TemplateResponse(
        "index.html.j2",
        {
            "request": request,
            "page_size": ui_settings.default_page_size,
        },
    )


@router.get("/manage", response_class=HTMLResponse)
async def manage(request: Request) -> HTMLResponse:
    """Subscription management page."""
    return _templates.TemplateResponse(
        "manage.html.j2",
        {
            "request": request,
        },
    )


# ---------------------------------------------------------------------------
# JSON API endpoints
# ---------------------------------------------------------------------------


@router.get("/api/articles")
async def api_articles(
    category: Optional[str] = None,
    feed_id: Optional[int] = None,
    keyword: Optional[str] = None,
    starred: Optional[bool] = None,
    unread: Optional[bool] = None,
    sort: str = Query("publish_time", pattern="^(publish_time|crawl_time|title)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """List articles with filtering and pagination."""
    async with get_session() as session:
        query = select(Article, Feed.title.label("feed_title")).join(
            Feed, Article.feed_id == Feed.id
        )

        if category:
            query = query.where(Feed.category == category)
        if feed_id is not None:
            query = query.where(Article.feed_id == feed_id)
        if keyword:
            pattern = f"%{keyword}%"
            query = query.where(
                or_(Article.title.ilike(pattern), Article.summary.ilike(pattern))
            )
        if starred is not None and starred:
            query = query.where(Article.is_starred == True)  # noqa: E712
        if unread is not None and unread:
            query = query.where(Article.is_read == False)  # noqa: E712

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_query)).scalar() or 0

        # Sort and paginate
        if sort == "title":
            query = query.order_by(Article.title)
        elif sort == "crawl_time":
            query = query.order_by(desc(Article.crawl_time))
        else:
            query = query.order_by(desc(Article.publish_time))

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        rows = result.all()

    return {
        "articles": [_article_to_dict(row[0], feed_title=row[1]) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/categories")
async def api_categories() -> dict:
    """List distinct categories from feeds table."""
    async with get_session() as session:
        result = await session.execute(
            select(Feed.category)
            .distinct()
            .where(Feed.category != "")
            .order_by(Feed.category)
        )
        categories = [row[0] for row in result.all()]
    return {"categories": categories}


@router.get("/api/feeds")
async def api_feeds() -> dict:
    """List distinct feed titles with their categories."""
    async with get_session() as session:
        result = await session.execute(
            select(Feed.id, Feed.title, Feed.category)
            .where(Feed.is_active == True)  # noqa: E712
            .order_by(Feed.category, Feed.title)
        )
        feeds = [
            {"id": row[0], "title": row[1], "category": row[2]}
            for row in result.all()
        ]
    return {"feeds": feeds}


@router.get("/api/articles/{article_id}")
async def api_article_detail(article_id: int) -> dict:
    """Single article detail."""
    async with get_session() as session:
        result = await session.execute(
            select(Article, Feed.title.label("feed_title"))
            .join(Feed, Article.feed_id == Feed.id)
            .where(Article.id == article_id)
        )
        row = result.first()
    if not row:
        return {"error": "not found"}
    return {"article": _article_to_dict(row[0], feed_title=row[1])}


@router.post("/api/articles/{article_id}/read")
async def api_mark_read(article_id: int) -> dict:
    """Mark article as read."""
    async with get_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
        if article:
            article.is_read = True
    return {"status": "ok"}


@router.post("/api/articles/{article_id}/star")
async def api_toggle_star(article_id: int) -> dict:
    """Toggle article star status."""
    async with get_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
        if article:
            article.is_starred = not article.is_starred
            return {"status": "ok", "is_starred": article.is_starred}
    return {"error": "not found"}


# ---------------------------------------------------------------------------
# Subscription management API
# ---------------------------------------------------------------------------


@router.get("/api/subscriptions")
async def api_subscriptions() -> dict:
    """List all feeds with article counts."""
    async with get_session() as session:
        # Subquery for article counts per feed
        article_count_sub = (
            select(
                Article.feed_id,
                func.count(Article.id).label("article_count"),
            )
            .group_by(Article.feed_id)
            .subquery()
        )

        result = await session.execute(
            select(Feed, article_count_sub.c.article_count)
            .outerjoin(article_count_sub, Feed.id == article_count_sub.c.feed_id)
            .order_by(desc(Feed.created_at))
        )
        rows = result.all()

    return {
        "subscriptions": [
            _feed_to_dict(row[0], article_count=row[1] or 0) for row in rows
        ]
    }


class AddFeedRequest(BaseModel):
    title: str = ""
    feed_url: str = ""
    category: str = ""


@router.post("/api/subscriptions")
async def api_add_subscription(payload: AddFeedRequest) -> dict:
    """Add a new feed subscription."""
    if not payload.feed_url:
        return {"error": "feed_url is required"}
    async with get_session() as session:
        existing = await session.execute(
            select(Feed).where(Feed.feed_url == payload.feed_url)
        )
        if existing.scalar_one_or_none():
            return {"error": "subscription already exists"}
        feed = Feed(
            title=payload.title,
            feed_url=payload.feed_url,
            category=payload.category,
        )
        session.add(feed)
    return {"status": "ok"}


@router.delete("/api/subscriptions/{feed_id}")
async def api_delete_subscription(feed_id: int) -> dict:
    """Delete a feed and its articles."""
    async with get_session() as session:
        result = await session.execute(
            select(Feed).where(Feed.id == feed_id)
        )
        feed = result.scalar_one_or_none()
        if feed:
            await session.delete(feed)
    return {"status": "ok"}


@router.put("/api/subscriptions/{feed_id}/toggle")
async def api_toggle_subscription(feed_id: int) -> dict:
    """Toggle feed active state."""
    async with get_session() as session:
        result = await session.execute(
            select(Feed).where(Feed.id == feed_id)
        )
        feed = result.scalar_one_or_none()
        if feed:
            feed.is_active = not feed.is_active
            return {"status": "ok", "is_active": feed.is_active}
    return {"error": "not found"}


@router.post("/api/trigger")
async def api_trigger_crawl() -> dict:
    """Trigger RSS crawl manually."""
    try:
        from apps.rss_crawler.tasks import run_crawl

        result = await run_crawl()
        return {"status": "ok", "result": result}
    except Exception as exc:
        logger.exception("Failed to trigger crawl")
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _article_to_dict(article: Article, feed_title: str = "") -> dict:
    return {
        "id": article.id,
        "feed_id": article.feed_id,
        "feed_title": feed_title,
        "title": article.title,
        "url": article.url,
        "author": article.author,
        "summary": article.summary,
        "cover_image_url": article.cover_image_url,
        "publish_time": article.publish_time.isoformat() if article.publish_time else "",
        "crawl_time": article.crawl_time.isoformat() if article.crawl_time else "",
        "is_read": article.is_read,
        "is_starred": article.is_starred,
    }


def _feed_to_dict(feed: Feed, article_count: int = 0) -> dict:
    return {
        "id": feed.id,
        "title": feed.title,
        "feed_url": feed.feed_url,
        "site_url": feed.site_url,
        "category": feed.category,
        "description": feed.description,
        "is_active": feed.is_active,
        "last_fetched_at": feed.last_fetched_at.isoformat() if feed.last_fetched_at else "",
        "error_count": feed.error_count,
        "article_count": article_count,
        "created_at": feed.created_at.isoformat() if feed.created_at else "",
        "updated_at": feed.updated_at.isoformat() if feed.updated_at else "",
    }
