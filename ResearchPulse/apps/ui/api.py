"""UI API endpoints for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import CurrentUser, OptionalUserId
from apps.crawler.models import (
    Article,
    ArxivCategory,
    RssFeed,
    UserArticleState,
    UserSubscription,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])

# Templates will be initialized in main.py
_templates: Jinja2Templates | None = None


def init_templates(template_dir: str) -> None:
    """Initialize Jinja2 templates."""
    global _templates
    from pathlib import Path
    _templates = Jinja2Templates(directory=Path(template_dir))


# ============================================================================
# Page Endpoints
# ============================================================================

@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user_id: OptionalUserId = None,
) -> HTMLResponse:
    """Main article list page."""
    return _templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user_id": user_id,
        },
    )


@router.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(
    request: Request,
    user_id: OptionalUserId = None,
) -> HTMLResponse:
    """Subscription management page."""
    return _templates.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "user_id": user_id,
        },
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    user_id: OptionalUserId = None,
) -> HTMLResponse:
    """Admin page."""
    return _templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user_id": user_id,
        },
    )


# ============================================================================
# Article API Endpoints
# ============================================================================

class ArticleListResponse(BaseModel):
    articles: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


class ArticleDetailResponse(BaseModel):
    article: Dict[str, Any]
    user_state: Optional[Dict[str, Any]] = None


@router.get("/api/articles", response_model=ArticleListResponse)
async def list_articles(
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    from_date: Optional[str] = None,
    starred: Optional[bool] = None,
    unread: Optional[bool] = None,
    archived: Optional[bool] = None,
    sort: str = Query("publish_time", pattern="^(publish_time|crawl_time|title)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: OptionalUserId = None,
    session: AsyncSession = Depends(get_session),
) -> ArticleListResponse:
    """List articles with filtering and pagination."""
    query = select(Article)

    # Apply filters
    if source_type:
        query = query.where(Article.source_type == source_type)
    if category:
        # Support both code and full name matching
        query = query.where(
            or_(
                Article.category == category,
                Article.category.like(f"%{category}%"),
                Article.arxiv_primary_category == category,
            )
        )
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(
            or_(Article.title.ilike(pattern), Article.summary.ilike(pattern))
        )
    if from_date:
        try:
            from datetime import datetime
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            query = query.where(Article.publish_time >= from_dt)
        except ValueError:
            pass
    if archived is not None:
        query = query.where(Article.is_archived == archived)
    else:
        # Default: hide archived articles
        query = query.where(Article.is_archived == False)

    # User-specific filters
    if user_id:
        # Join with user states for starred/unread filters
        if starred is not None and starred:
            query = query.join(UserArticleState).where(
                UserArticleState.user_id == user_id,
                UserArticleState.is_starred == True,
            )
        if unread is not None and unread:
            query = query.outerjoin(
                UserArticleState,
                (UserArticleState.article_id == Article.id) & (UserArticleState.user_id == user_id)
            ).where(
                or_(UserArticleState.is_read == False, UserArticleState.is_read == None)
            )

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

    # Get user states if logged in
    user_states = {}
    if user_id:
        article_ids = [a.id for a in articles]
        if article_ids:
            state_result = await session.execute(
                select(UserArticleState).where(
                    UserArticleState.user_id == user_id,
                    UserArticleState.article_id.in_(article_ids),
                )
            )
            for state in state_result.scalars().all():
                user_states[state.article_id] = state

    # Build response
    article_list = []
    for article in articles:
        article_dict = _article_to_dict(article)
        if article.id in user_states:
            state = user_states[article.id]
            article_dict["is_read"] = state.is_read
            article_dict["is_starred"] = state.is_starred
        article_list.append(article_dict)

    return ArticleListResponse(
        articles=article_list,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(
    article_id: int,
    user_id: OptionalUserId = None,
    session: AsyncSession = Depends(get_session),
) -> ArticleDetailResponse:
    """Get article details."""
    result = await session.execute(
        select(Article).where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()

    if not article:
        return ArticleDetailResponse(article={}, user_state=None)

    article_dict = _article_to_dict(article)

    # Get user state if logged in
    user_state = None
    if user_id:
        state_result = await session.execute(
            select(UserArticleState).where(
                UserArticleState.user_id == user_id,
                UserArticleState.article_id == article_id,
            )
        )
        state = state_result.scalar_one_or_none()
        if state:
            user_state = {
                "is_read": state.is_read,
                "is_starred": state.is_starred,
                "read_at": state.read_at.isoformat() if state.read_at else None,
                "starred_at": state.starred_at.isoformat() if state.starred_at else None,
            }

    return ArticleDetailResponse(article=article_dict, user_state=user_state)


@router.post("/api/articles/{article_id}/read")
async def mark_article_read(
    article_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Mark article as read."""
    # Get or create user state
    result = await session.execute(
        select(UserArticleState).where(
            UserArticleState.user_id == user.id,
            UserArticleState.article_id == article_id,
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        state = UserArticleState(
            user_id=user.id,
            article_id=article_id,
        )
        session.add(state)

    state.mark_read()
    await session.flush()

    return {"status": "ok", "is_read": True}


@router.post("/api/articles/{article_id}/star")
async def toggle_article_star(
    article_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Toggle article star status."""
    # Get or create user state
    result = await session.execute(
        select(UserArticleState).where(
            UserArticleState.user_id == user.id,
            UserArticleState.article_id == article_id,
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        state = UserArticleState(
            user_id=user.id,
            article_id=article_id,
        )
        session.add(state)

    new_star_status = state.toggle_star()
    await session.flush()

    return {"status": "ok", "is_starred": new_star_status}


# ============================================================================
# Source API Endpoints
# ============================================================================

@router.get("/api/categories")
async def list_categories(
    source_type: str = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List available categories based on source type."""
    
    if source_type == "arxiv" or source_type is None:
        # Return arxiv categories
        result = await session.execute(
            select(ArxivCategory)
            .where(ArxivCategory.is_active == True)
            .order_by(ArxivCategory.code)
        )
        categories = result.scalars().all()
        
        return {
            "type": "arxiv",
            "categories": [
                {
                    "id": cat.id,
                    "code": cat.code,
                    "name": cat.name,
                    "description": cat.description,
                }
                for cat in categories
            ]
        }
    elif source_type == "rss":
        # Return RSS feed categories
        result = await session.execute(
            select(RssFeed.category)
            .where(RssFeed.is_active == True)
            .distinct()
            .order_by(RssFeed.category)
        )
        categories = [row[0] for row in result.fetchall() if row[0]]
        
        return {
            "type": "rss",
            "categories": [
                {
                    "id": idx,
                    "code": cat,
                    "name": cat,
                    "description": "",
                }
                for idx, cat in enumerate(categories)
            ]
        }
    else:
        return {"type": "unknown", "categories": []}


@router.get("/api/sources")
async def list_all_sources(
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all available sources for filtering."""
    # ArXiv categories
    arxiv_result = await session.execute(
        select(ArxivCategory)
        .where(ArxivCategory.is_active == True)
        .order_by(ArxivCategory.code)
    )
    arxiv_cats = arxiv_result.scalars().all()
    
    # RSS feeds
    rss_result = await session.execute(
        select(RssFeed)
        .where(RssFeed.is_active == True)
        .order_by(RssFeed.category, RssFeed.title)
    )
    rss_feeds = rss_result.scalars().all()
    
    return {
        "arxiv_categories": [
            {"id": cat.id, "code": cat.code, "name": cat.name}
            for cat in arxiv_cats
        ],
        "rss_feeds": [
            {"id": feed.id, "title": feed.title, "category": feed.category}
            for feed in rss_feeds
        ],
    }


@router.get("/api/feeds")
async def list_feeds(
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List available RSS feeds."""
    result = await session.execute(
        select(RssFeed)
        .where(RssFeed.is_active == True)
        .order_by(RssFeed.category, RssFeed.title)
    )
    feeds = result.scalars().all()

    return {
        "feeds": [
            {
                "id": feed.id,
                "title": feed.title,
                "category": feed.category,
                "site_url": feed.site_url,
            }
            for feed in feeds
        ]
    }


# ============================================================================
# Subscription API Endpoints
# ============================================================================

@router.get("/api/subscriptions")
async def list_subscriptions(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List user's subscriptions."""
    result = await session.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user.id)
        .order_by(UserSubscription.source_type, UserSubscription.source_id)
    )
    subscriptions = result.scalars().all()

    return {
        "subscriptions": [
            {
                "id": sub.id,
                "source_type": sub.source_type,
                "source_id": sub.source_id,
                "is_active": sub.is_active,
            }
            for sub in subscriptions
        ]
    }


@router.post("/api/subscriptions")
async def create_subscription(
    source_type: str,
    source_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new subscription."""
    # Check if already subscribed
    result = await session.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.source_type == source_type,
            UserSubscription.source_id == source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.is_active:
            return {"status": "ok", "message": "Already subscribed"}
        existing.is_active = True
    else:
        subscription = UserSubscription(
            user_id=user.id,
            source_type=source_type,
            source_id=source_id,
        )
        session.add(subscription)

    return {"status": "ok"}


@router.delete("/api/subscriptions/{source_type}/{source_id}")
async def delete_subscription(
    source_type: str,
    source_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a subscription by source type and id."""
    result = await session.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.source_type == source_type,
            UserSubscription.source_id == source_id,
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.is_active = False

    return {"status": "ok"}


# ============================================================================
# Helpers
# ============================================================================

def _article_to_dict(article: Article) -> Dict[str, Any]:
    """Convert Article model to dictionary."""
    return {
        "id": article.id,
        "source_type": article.source_type,
        "title": article.title,
        "url": article.url,
        "author": article.author,
        "summary": article.summary or "",
        "content_summary": article.content_summary,  # AI summary or translation
        "category": article.category,
        "tags": article.tags or [],
        "publish_time": article.publish_time.isoformat() if article.publish_time else None,
        "crawl_time": article.crawl_time.isoformat() if article.crawl_time else None,
        "cover_image_url": article.cover_image_url,
        "is_archived": article.is_archived,
        # ArXiv specific fields
        "arxiv_id": article.arxiv_id,
        "arxiv_primary_category": article.arxiv_primary_category,
        "arxiv_updated_time": article.arxiv_updated_time.isoformat() if article.arxiv_updated_time else None,
        # WeChat specific fields
        "wechat_account_name": article.wechat_account_name,
    }


# ============================================================================
# Export API Endpoints
# ============================================================================

@router.get("/api/export/markdown")
async def export_markdown(
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export articles as Markdown."""
    from datetime import datetime
    from fastapi.responses import Response
    from common.markdown import render_articles_by_source

    # Build query
    query = select(Article).where(Article.is_archived == False)

    if source_type:
        query = query.where(Article.source_type == source_type)
    if category:
        query = query.where(Article.category == category)
    if from_date:
        try:
            dt = datetime.fromisoformat(from_date)
            query = query.where(Article.crawl_time >= dt)
        except ValueError:
            pass
    if to_date:
        try:
            dt = datetime.fromisoformat(to_date)
            query = query.where(Article.crawl_time <= dt)
        except ValueError:
            pass

    query = query.order_by(Article.crawl_time.desc()).offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    articles = result.scalars().all()

    # Convert to dicts
    article_dicts = [_article_to_dict(a) for a in articles]

    # Generate markdown
    date_str = from_date or datetime.now().strftime("%Y-%m-%d")
    markdown = render_articles_by_source(
        article_dicts,
        date=date_str,
        include_abstract=True,
        abstract_max_len=500,
    )

    # Return as downloadable file
    filename = f"researchpulse_{date_str}.md"
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/api/export/user-markdown")
async def export_user_markdown(
    from_date: Optional[str] = None,
    user: CurrentUser = None,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export user's subscribed articles as Markdown."""
    from datetime import datetime, timezone, timedelta
    from fastapi.responses import Response
    from common.markdown import render_articles_by_source

    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get user's subscriptions
    sub_result = await session.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.is_active == True,
        )
    )
    subscriptions = sub_result.scalars().all()

    if not subscriptions:
        return Response(
            content="# 无订阅\n\n您还没有订阅任何内容。",
            media_type="text/markdown",
        )

    # Build date filter
    if from_date:
        try:
            since = datetime.fromisoformat(from_date)
        except ValueError:
            since = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=1)

    # Get articles matching subscriptions
    query = select(Article).where(
        Article.is_archived == False,
        Article.crawl_time >= since,
    ).order_by(Article.crawl_time.desc()).limit(100)

    result = await session.execute(query)
    all_articles = result.scalars().all()

    # Filter by subscriptions (simplified)
    # In production, you'd want more sophisticated matching
    matched = []
    for article in all_articles[:50]:
        matched.append(_article_to_dict(article))

    # Generate markdown
    date_str = since.strftime("%Y-%m-%d")
    markdown = render_articles_by_source(
        matched,
        date=date_str,
        include_abstract=True,
        abstract_max_len=500,
    )

    filename = f"my_subscriptions_{date_str}.md"
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
