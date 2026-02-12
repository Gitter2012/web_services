from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, or_, select

from apps.wechat_crawler.database import get_session
from apps.wechat_crawler.models import Article, Subscription

from .config import settings as ui_settings

logger = logging.getLogger(__name__)

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# --- Page endpoints ---


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


@router.get("/article/{article_id}", response_class=HTMLResponse)
async def detail(request: Request, article_id: int) -> HTMLResponse:
    """Article detail/reader page."""
    async with get_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
    if not article:
        return HTMLResponse("Article not found", status_code=404)
    return _templates.TemplateResponse(
        "detail.html.j2",
        {
            "request": request,
            "article": article,
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


# --- JSON API endpoints ---


@router.get("/api/articles")
async def api_articles(
    account: Optional[str] = None,
    keyword: Optional[str] = None,
    date: Optional[str] = None,
    sort: str = Query("publish_time", pattern="^(publish_time|crawl_time|title)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """List articles with filtering and pagination."""
    async with get_session() as session:
        query = select(Article)

        if account:
            query = query.where(Article.account_name == account)
        if keyword:
            pattern = f"%{keyword}%"
            query = query.where(
                or_(Article.title.ilike(pattern), Article.digest.ilike(pattern))
            )
        if date:
            # Filter articles by publish date (YYYY-MM-DD)
            query = query.where(func.date(Article.publish_time) == date)

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
        articles = result.scalars().all()

    return {
        "articles": [_article_to_dict(a) for a in articles],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/accounts")
async def api_accounts() -> dict:
    """List distinct account names."""
    async with get_session() as session:
        result = await session.execute(
            select(Article.account_name)
            .distinct()
            .where(Article.account_name != "")
            .order_by(Article.account_name)
        )
        accounts = [row[0] for row in result.all()]
    return {"accounts": accounts}


@router.get("/api/articles/{article_id}")
async def api_article_detail(article_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
    if not article:
        return {"error": "not found"}
    return {"article": _article_to_dict(article)}


@router.post("/api/articles/{article_id}/read")
async def api_mark_read(article_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
        if article:
            article.is_read = True
    return {"status": "ok"}


# --- Subscription management API ---


@router.get("/api/subscriptions")
async def api_subscriptions() -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Subscription).order_by(desc(Subscription.created_at))
        )
        subs = result.scalars().all()
    return {"subscriptions": [_sub_to_dict(s) for s in subs]}


class AddSubscriptionRequest(BaseModel):
    account_name: str = ""
    account_id: str = ""
    rss_url: str = ""


@router.post("/api/subscriptions")
async def api_add_subscription(payload: AddSubscriptionRequest) -> dict:
    if not payload.rss_url:
        return {"error": "rss_url is required"}
    async with get_session() as session:
        existing = await session.execute(
            select(Subscription).where(Subscription.rss_url == payload.rss_url)
        )
        if existing.scalar_one_or_none():
            return {"error": "subscription already exists"}
        sub = Subscription(
            account_name=payload.account_name,
            account_id=payload.account_id,
            rss_url=payload.rss_url,
        )
        session.add(sub)
    return {"status": "ok"}


@router.delete("/api/subscriptions/{sub_id}")
async def api_delete_subscription(sub_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            await session.delete(sub)
    return {"status": "ok"}


@router.put("/api/subscriptions/{sub_id}/toggle")
async def api_toggle_subscription(sub_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.is_active = not sub.is_active
    return {"status": "ok"}


# --- Image cache / proxy ---

_IMAGE_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wechat" / "images"

_MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
}


@router.get("/api/imgcache/{filename}")
async def api_image_cache(filename: str) -> Response:
    """Serve locally cached images downloaded during crawl."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    file_path = _IMAGE_CACHE_DIR / safe_name
    if not file_path.exists():
        return Response(status_code=404)

    ext = file_path.suffix.lower()
    content_type = _MIME_MAP.get(ext, "image/jpeg")
    return Response(
        content=file_path.read_bytes(),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=604800"},  # 7 days
    )


@router.get("/api/imgproxy")
async def api_image_proxy(url: str = Query(..., min_length=1)) -> Response:
    """Proxy external images as fallback when cache is unavailable."""
    import asyncio
    import requests as _req
    import warnings

    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Derive a plausible site Referer – many CDNs (e.g. image.example.com)
    # require Referer from the main site (www.example.com).
    # Strip common CDN/asset sub-domain prefixes and use "www." instead.
    _CDN_PREFIXES = ("image.", "img.", "static.", "assets.", "cdn.", "media.", "res.", "pic.")
    site_host = host
    for pfx in _CDN_PREFIXES:
        if host.startswith(pfx):
            site_host = "www." + host[len(pfx):]
            break
    referer = f"{parsed.scheme}://{site_host}/" if site_host else ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    try:
        def _fetch():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return _req.get(url, headers=headers, timeout=15, verify=False,
                                allow_redirects=True)

        resp = await asyncio.to_thread(_fetch)
        if resp.status_code != 200:
            return Response(status_code=resp.status_code)

        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return Response(
            content=resp.content,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Proxy-Source": host,
            },
        )
    except Exception:
        logger.exception("Image proxy failed for %s", url)
        return Response(status_code=502)


# --- Helpers ---


def _make_image_url(original_url: str) -> str:
    """Convert an image URL to a proxy/cache URL for the frontend."""
    if not original_url:
        return ""
    # If it's already a local cache path, return as-is
    if original_url.startswith("/wechat/ui/api/imgcache/"):
        return original_url
    # Otherwise, use proxy as fallback
    return f"/wechat/ui/api/imgproxy?url={original_url}"


def _article_to_dict(article: Article) -> dict:
    cover_url = article.cover_image_url or ""
    return {
        "id": article.id,
        "title": article.title,
        "author": article.author,
        "account_name": article.account_name,
        "account_id": article.account_id,
        "digest": article.digest,
        "content_url": article.content_url,
        "cover_image_url": _make_image_url(cover_url) if cover_url else "",
        "publish_time": article.publish_time.isoformat() if article.publish_time else "",
        "crawl_time": article.crawl_time.isoformat() if article.crawl_time else "",
        "source_type": article.source_type,
        "read_count": article.read_count,
        "like_count": article.like_count,
        "is_read": article.is_read,
        "tags": article.tags,
    }


def _sub_to_dict(sub: Subscription) -> dict:
    return {
        "id": sub.id,
        "account_name": sub.account_name,
        "account_id": sub.account_id,
        "rss_url": sub.rss_url,
        "source_type": sub.source_type,
        "is_active": sub.is_active,
        "created_at": sub.created_at.isoformat() if sub.created_at else "",
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else "",
    }
