"""Admin API endpoints for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import Superuser, require_permissions
from core.models.user import User
from core.models.permission import Role, Permission
from apps.crawler.models import (
    Article,
    ArxivCategory,
    RssFeed,
    WechatAccount,
    SystemConfig,
    BackupRecord,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Dashboard Stats
# ============================================================================

@router.get("/stats")
async def get_stats(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get dashboard statistics."""
    from datetime import timedelta

    # User count
    users_count = await session.execute(select(func.count(User.id)))
    users = users_count.scalar() or 0

    # Article count
    articles_count = await session.execute(select(func.count(Article.id)))
    articles = articles_count.scalar() or 0

    # Source count
    arxiv_count = await session.execute(select(func.count(ArxivCategory.id)).where(ArxivCategory.is_active == True))
    rss_count = await session.execute(select(func.count(RssFeed.id)).where(RssFeed.is_active == True))
    sources = (arxiv_count.scalar() or 0) + (rss_count.scalar() or 0)

    # Today's articles
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await session.execute(
        select(func.count(Article.id)).where(Article.crawl_time >= today)
    )
    today_articles = today_count.scalar() or 0

    return {
        "users": users,
        "articles": articles,
        "sources": sources,
        "today_articles": today_articles,
    }


# ============================================================================
# User Management
# ============================================================================

class UserListResponse(BaseModel):
    users: List[Dict[str, Any]]
    total: int


class UserRoleUpdate(BaseModel):
    role_name: str


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List all users (admin only)."""
    # Count total
    count_result = await session.execute(select(func.count(User.id)))
    total = count_result.scalar() or 0

    # Get users
    result = await session.execute(
        select(User)
        .order_by(desc(User.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().all()

    return UserListResponse(
        users=[
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "roles": [role.name for role in user.roles],
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }
            for user in users
        ],
        total=total,
    )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    update: UserRoleUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update user's role (admin only)."""
    # Get user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get role
    role_result = await session.execute(select(Role).where(Role.name == update.role_name))
    role = role_result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Update roles (replace all)
    user.roles = [role]

    return {"status": "ok", "message": f"Role updated to {update.role_name}"}


@router.put("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Toggle user active status (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active

    return {"status": "ok", "is_active": user.is_active}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    is_active: Optional[bool] = None,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if is_active is not None:
        user.is_active = is_active

    return {"status": "ok"}


# ============================================================================
# Crawler Management
# ============================================================================

class CrawlerStatusResponse(BaseModel):
    sources: Dict[str, Any]
    recent_articles: int


@router.get("/crawler/status", response_model=CrawlerStatusResponse)
async def get_crawler_status(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> CrawlerStatusResponse:
    """Get crawler status (admin only)."""
    # Count sources
    arxiv_count = await session.execute(select(func.count(ArxivCategory.id)).where(ArxivCategory.is_active == True))
    rss_count = await session.execute(select(func.count(RssFeed.id)).where(RssFeed.is_active == True))
    wechat_count = await session.execute(select(func.count(WechatAccount.id)).where(WechatAccount.is_active == True))

    # Count recent articles (last 24 hours)
    from datetime import timedelta
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    recent_count = await session.execute(
        select(func.count(Article.id)).where(Article.crawl_time >= yesterday)
    )

    return CrawlerStatusResponse(
        sources={
            "arxiv_categories": arxiv_count.scalar() or 0,
            "rss_feeds": rss_count.scalar() or 0,
            "wechat_accounts": wechat_count.scalar() or 0,
        },
        recent_articles=recent_count.scalar() or 0,
    )


@router.post("/crawler/trigger")
async def trigger_crawl(
    source_type: str,
    source_id: str,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Manually trigger a crawl task (admin only)."""
    # This would integrate with the scheduler to trigger a crawl
    # For now, return a placeholder response
    return {
        "status": "ok",
        "message": f"Crawl triggered for {source_type}:{source_id}",
        "task_id": "placeholder",
    }


# ============================================================================
# Configuration Management
# ============================================================================

@router.get("/config")
async def list_config(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List system configuration (admin only)."""
    result = await session.execute(select(SystemConfig))
    configs = result.scalars().all()

    return {
        "configs": [
            {
                "key": config.config_key,
                "value": "***" if config.is_sensitive else config.config_value,
                "description": config.description,
                "is_sensitive": config.is_sensitive,
            }
            for config in configs
        ]
    }


class ConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None


@router.put("/config/{key}")
async def update_config(
    key: str,
    update: ConfigUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update system configuration (admin only)."""
    result = await session.execute(select(SystemConfig).where(SystemConfig.config_key == key))
    config = result.scalar_one_or_none()

    if config:
        config.config_value = update.value
        if update.description:
            config.description = update.description
        config.updated_by = admin.id
    else:
        config = SystemConfig(
            config_key=key,
            config_value=update.value,
            description=update.description or "",
            updated_by=admin.id,
        )
        session.add(config)

    return {"status": "ok", "key": key}


# ============================================================================
# Backup Management
# ============================================================================

@router.get("/backups")
async def list_backups(
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List backup records (admin only)."""
    result = await session.execute(
        select(BackupRecord)
        .order_by(desc(BackupRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    backups = result.scalars().all()

    return {
        "backups": [
            {
                "id": backup.id,
                "backup_date": backup.backup_date.isoformat() if backup.backup_date else None,
                "backup_file": backup.backup_file,
                "backup_size": backup.backup_size,
                "article_count": backup.article_count,
                "status": backup.status,
                "created_at": backup.created_at.isoformat() if backup.created_at else None,
            }
            for backup in backups
        ]
    }


@router.post("/backups/create")
async def create_backup(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Trigger a manual backup (admin only)."""
    # This would integrate with the scheduler to trigger a backup
    return {
        "status": "ok",
        "message": "Backup task triggered",
    }


# ============================================================================
# Statistics
# ============================================================================

@router.get("/stats")
async def get_stats(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get system statistics (admin only)."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Article stats
    total_articles = await session.execute(select(func.count(Article.id)))
    articles_today = await session.execute(
        select(func.count(Article.id)).where(Article.crawl_time >= today)
    )
    articles_week = await session.execute(
        select(func.count(Article.id)).where(Article.crawl_time >= week_ago)
    )
    articles_archived = await session.execute(
        select(func.count(Article.id)).where(Article.is_archived == True)
    )

    # User stats
    total_users = await session.execute(select(func.count(User.id)))
    active_users = await session.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )

    return {
        "articles": {
            "total": total_articles.scalar() or 0,
            "today": articles_today.scalar() or 0,
            "this_week": articles_week.scalar() or 0,
            "archived": articles_archived.scalar() or 0,
        },
        "users": {
            "total": total_users.scalar() or 0,
            "active": active_users.scalar() or 0,
        },
    }
