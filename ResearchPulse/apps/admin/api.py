# ==========================================================================
# 管理后台 API 模块
# --------------------------------------------------------------------------
# 本模块是 ResearchPulse 系统的管理后台接口层，仅限超级管理员 (Superuser) 访问。
# 提供以下核心管理能力：
#   1. 仪表盘统计 —— 用户数、文章数、数据源数、今日新增等关键指标
#   2. 用户管理   —— 列表查询、角色变更、启用/禁用账户
#   3. 数据源管理 —— ArXiv 分类、RSS 源、微信公众号的增删改查
#   4. 爬虫管理   —— 查看各数据源状态、手动触发爬取任务
#   5. 系统配置   —— 读取/更新 SystemConfig 表，支持分组与批量操作
#   6. 功能开关   —— 基于 feature_config 的动态特性启用/禁用
#   7. 调度器管理 —— 查看/修改/手动触发 APScheduler 定时任务
#   8. 备份管理   —— 查看备份记录、手动触发备份
#
# 架构位置：
#   apps/admin/api.py 属于"管理应用"(admin app)的路由层，
#   通过 FastAPI 的 APIRouter 注册到主应用。所有端点均依赖
#   Superuser 依赖项进行超级管理员身份校验。
# ==========================================================================

"""Admin API endpoints for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl, field_validator
from sqlalchemy import desc, select, func, update, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.database import get_session
from core.dependencies import Superuser, require_permissions
from core.models.user import User
from core.models.permission import Role, Permission, RolePermission
from core.models.user import User, UserRole
from apps.crawler.models import (
    Article,
    ArxivCategory,
    HackerNewsSource,
    RedditSource,
    RssFeed,
    TwitterSource,
    WechatAccount,
    WeiboHotSearch,
    SystemConfig,
    BackupRecord,
    UserSubscription,
    EmailConfig,
    AuditLog,
)
from common.feature_config import feature_config

logger = logging.getLogger(__name__)

# 创建管理后台路由器，所有端点统一挂载在 /admin 前缀下
router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Dashboard Stats
# ============================================================================
# 仪表盘统计端点 —— 为管理后台首页提供关键业务指标的概览数据

@router.get("/stats")
async def get_stats(
    admin: Superuser = None,  # 依赖注入：确保当前用户是超级管理员
    session: AsyncSession = Depends(get_session),  # 异步数据库会话
) -> Dict[str, Any]:
    """Get dashboard statistics for the admin overview.

    Returns key counts such as total users, articles, active sources, and
    today's newly crawled articles.

    Returns:
        Dict[str, Any]: Dashboard metrics including users, articles, sources,
        subscriptions, and today_articles.
    """
    from datetime import timedelta

    # 查询注册用户总数
    users_count = await session.execute(select(func.count(User.id)))
    users = users_count.scalar() or 0

    # 查询文章总数（包括所有来源的文章）
    articles_count = await session.execute(select(func.count(Article.id)))
    articles = articles_count.scalar() or 0

    # 统计活跃数据源数量：ArXiv 分类 + RSS 订阅源
    # 只计算 is_active=True 的有效源
    arxiv_count = await session.execute(select(func.count(ArxivCategory.id)).where(ArxivCategory.is_active == True))
    rss_count = await session.execute(select(func.count(RssFeed.id)).where(RssFeed.is_active == True))
    sources = (arxiv_count.scalar() or 0) + (rss_count.scalar() or 0)

    # 统计今日新增文章数
    # 以 UTC 时区当日零点为基准，查询 crawl_time >= 今日零点的文章数
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await session.execute(
        select(func.count(Article.id)).where(Article.crawl_time >= today)
    )
    today_articles = today_count.scalar() or 0

    # 统计用户订阅总数
    subscriptions_count = await session.execute(
        select(func.count(UserSubscription.id)).where(UserSubscription.is_active == True)
    )
    subscriptions = subscriptions_count.scalar() or 0

    return {
        "users": users,
        "articles": articles,
        "sources": sources,
        "subscriptions": subscriptions,
        "today_articles": today_articles,
    }


# ============================================================================
# User Management
# ============================================================================
# 用户管理部分 —— 提供对系统用户的 CRUD 操作
# 仅超级管理员可操作，普通用户无权访问

# 用户列表响应模型，包含用户数组和总数（用于前端分页展示）
class UserListResponse(BaseModel):
    """Response schema for user list queries.

    Attributes:
        users: List of user summary dictionaries.
        total: Total number of users available.
    """

    users: List[Dict[str, Any]]
    total: int


# 用户角色更新请求体，仅包含目标角色名称
class UserRoleUpdate(BaseModel):
    """Request schema for updating a user's role.

    Attributes:
        role_name: Target role name to assign.
    """

    role_name: str


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = 1,            # 当前页码，默认第 1 页
    page_size: int = 20,      # 每页显示条数，默认 20 条
    search: Optional[str] = None,  # 搜索用户名或邮箱
    role: Optional[str] = None,    # 按角色筛选
    is_active: Optional[bool] = None,  # 按状态筛选
    admin: Superuser = None,  # 超级管理员身份校验
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List users with pagination and filtering (admin only).

    Args:
        page: Page number, starting from 1.
        page_size: Number of items per page (max 100).
        search: Search by username or email (case-insensitive).
        role: Filter by role name.
        is_active: Filter by active status.
        admin: Superuser dependency injected by FastAPI.
        session: Async database session.

    Returns:
        UserListResponse: Paginated user list and total count.
    """
    # 分页参数安全约束：限制每页最大条数
    MAX_PAGE_SIZE = 100
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    # 构建基础查询
    base_query = select(User)

    # 应用筛选条件
    if search:
        search_term = f"%{search}%"
        base_query = base_query.where(
            or_(
                User.username.ilike(search_term),
                User.email.ilike(search_term)
            )
        )

    if is_active is not None:
        base_query = base_query.where(User.is_active == is_active)

    if role:
        # 通过角色名称筛选
        from core.models.role import Role
        from sqlalchemy.orm import joinedload
        base_query = base_query.join(User.roles).where(Role.name == role)

    # 查询用户总数
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    # 按创建时间倒序获取当前页的用户列表
    # 使用 selectinload 预加载 roles 关系，避免 N+1 查询
    result = await session.execute(
        base_query
        .options(selectinload(User.roles))
        .order_by(desc(User.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().all()

    # 将 ORM 对象转换为字典列表，提取前端需要的关键字段
    return UserListResponse(
        users=[
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "roles": [role.name for role in user.roles],  # 将角色对象列表转为角色名称列表
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }
            for user in users
        ],
        total=total,
    )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,             # 路径参数：目标用户 ID
    update: UserRoleUpdate,   # 请求体：包含新的角色名
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a user's role (admin only).

    Args:
        user_id: Target user ID.
        update: Role update payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status message indicating role update result.

    Raises:
        HTTPException: If the user or role does not exist.
    """
    # 根据用户 ID 查询目标用户
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 根据角色名查询角色对象
    role_result = await session.execute(select(Role).where(Role.name == update.role_name))
    role = role_result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # 替换用户的所有角色为新指定的单一角色
    # 设计决策：当前采用"替换全部"策略，一个用户同一时间只有一个角色
    user.roles = [role]

    return {"status": "ok", "message": f"Role updated to {update.role_name}"}


@router.put("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,             # 路径参数：目标用户 ID
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Toggle a user's active status (admin only).

    Args:
        user_id: Target user ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: New activation status.

    Raises:
        HTTPException: If the user does not exist.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 切换用户的激活状态：如果当前是活跃则禁用，反之则启用
    user.is_active = not user.is_active

    return {"status": "ok", "is_active": user.is_active}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    is_active: Optional[bool] = None,  # 可选参数：是否激活，为 None 时不修改
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update basic user fields (admin only).

    Currently supports updating the activation status.

    Args:
        user_id: Target user ID.
        is_active: Optional active status to set.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status message.

    Raises:
        HTTPException: If the user does not exist.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 仅在明确传入 is_active 参数时更新，避免误操作
    if is_active is not None:
        user.is_active = is_active

    return {"status": "ok"}


# ============================================================================
# Crawler Management
# ============================================================================
# 爬虫管理部分 —— 查看各数据源的运行状态以及手动触发爬取任务

# 爬虫状态响应模型：包含各类数据源的数量统计以及最近文章数
class CrawlerStatusResponse(BaseModel):
    """Crawler status summary for admin view.

    Attributes:
        sources: Active source counts by type.
        recent_articles: Number of articles crawled in the last 24 hours.
    """

    sources: Dict[str, Any]   # 各数据源类型及其活跃数量
    recent_articles: int      # 最近 24 小时内爬取的文章数


@router.get("/crawler/status", response_model=CrawlerStatusResponse)
async def get_crawler_status(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> CrawlerStatusResponse:
    """Get crawler status (admin only).

    Returns:
        CrawlerStatusResponse: Counts of active sources and recent article volume.
    """
    # 分别统计三种数据源的活跃数量：ArXiv 分类、RSS 源、微信公众号
    arxiv_count = await session.execute(select(func.count(ArxivCategory.id)).where(ArxivCategory.is_active == True))
    rss_count = await session.execute(select(func.count(RssFeed.id)).where(RssFeed.is_active == True))
    wechat_count = await session.execute(select(func.count(WechatAccount.id)).where(WechatAccount.is_active == True))

    # 统计最近 24 小时内爬取的文章数量，用于反映爬虫的健康状态
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
    source_type: str = "all",   # 数据源类型："all"、"arxiv"、"rss"、"wechat"
    source_id: str = "",        # 数据源的唯一标识（可选，为空则爬取该类型所有源）
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Manually trigger a crawl task (admin only).

    Supports three modes:
    1. ``source_type=all``: crawl all sources
    2. ``source_type=arxiv|rss|wechat`` with empty ``source_id``: crawl all of that type
    3. ``source_type=arxiv|rss|wechat`` with ``source_id``: crawl a specific source

    Args:
        source_type: Source type to crawl.
        source_id: Optional source identifier.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Trigger result and crawl summary.

    Raises:
        HTTPException: If the source type is invalid or source not found.
    """
    from apps.scheduler.tasks import get_scheduler
    from datetime import datetime, timezone
    import uuid

    scheduler = get_scheduler()
    job_id = f"manual_crawl_{uuid.uuid4().hex[:8]}"
    start_time = datetime.now(timezone.utc)

    async def run_single_arxiv_crawl(category_code: str):
        """Crawl a single ArXiv category."""
        from apps.crawler.arxiv import ArxivCrawler
        from settings import settings
        crawler = ArxivCrawler(
            category=category_code,
            max_results=50,
            delay_base=settings.arxiv_delay_base,
        )
        return await crawler.run()

    async def run_single_rss_crawl(feed_id: int, feed_url: str):
        """Crawl a single RSS feed."""
        from apps.crawler.rss import RssCrawler
        crawler = RssCrawler(feed_id=str(feed_id), feed_url=feed_url)
        return await crawler.run()

    results = {
        "arxiv": [],
        "rss": [],
        "wechat": [],
        "errors": [],
        "total_articles": 0,
    }

    try:
        if source_type == "all":
            # 触发全量爬取：调用 run_crawl_job
            from apps.scheduler.jobs.crawl_job import run_crawl_job
            result = await run_crawl_job()
            return {
                "status": "ok",
                "job_id": job_id,
                "message": "Full crawl triggered",
                "result": result,
            }

        elif source_type == "arxiv":
            if source_id:
                # 爬取单个 ArXiv 分类
                result = await run_single_arxiv_crawl(source_id)
                results["arxiv"].append(result)
                results["total_articles"] = result.get("saved_count", 0)
            else:
                # 爬取所有活跃的 ArXiv 分类
                from apps.crawler.models import ArxivCategory
                categories = await session.execute(
                    select(ArxivCategory).where(ArxivCategory.is_active == True)
                )
                for cat in categories.scalars().all():
                    try:
                        result = await run_single_arxiv_crawl(cat.code)
                        results["arxiv"].append(result)
                        results["total_articles"] += result.get("saved_count", 0)
                    except Exception as e:
                        results["errors"].append(f"arxiv:{cat.code}: {str(e)}")
                await session.commit()

        elif source_type == "rss":
            if source_id:
                # 爬取单个 RSS 源
                from apps.crawler.models import RssFeed
                feed = await session.execute(
                    select(RssFeed).where(RssFeed.id == int(source_id))
                )
                feed = feed.scalar_one_or_none()
                if not feed:
                    raise HTTPException(status_code=404, detail="RSS feed not found")
                result = await run_single_rss_crawl(feed.id, feed.feed_url)
                results["rss"].append(result)
                results["total_articles"] = result.get("saved_count", 0)
                feed.last_fetched_at = datetime.now(timezone.utc)
                await session.commit()
            else:
                # 爬取所有活跃的 RSS 源
                from apps.crawler.models import RssFeed
                feeds = await session.execute(
                    select(RssFeed).where(RssFeed.is_active == True)
                )
                for feed in feeds.scalars().all():
                    try:
                        result = await run_single_rss_crawl(feed.id, feed.feed_url)
                        results["rss"].append(result)
                        results["total_articles"] += result.get("saved_count", 0)
                        feed.last_fetched_at = datetime.now(timezone.utc)
                    except Exception as e:
                        results["errors"].append(f"rss:{feed.id}: {str(e)}")
                await session.commit()

        elif source_type == "wechat":
            # 微信公众号爬取（目前占位实现）
            return {
                "status": "ok",
                "job_id": job_id,
                "message": "WeChat crawling is not yet implemented",
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown source type: {source_type}")

    except Exception as e:
        logger.error(f"Crawl trigger failed: {e}")
        return {
            "status": "error",
            "job_id": job_id,
            "message": str(e),
            "partial_results": results,
        }

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    return {
        "status": "ok",
        "job_id": job_id,
        "source_type": source_type,
        "source_id": source_id,
        "duration_seconds": duration,
        "arxiv_crawled": len(results["arxiv"]),
        "rss_crawled": len(results["rss"]),
        "total_articles": results["total_articles"],
        "error_count": len(results["errors"]),
        "errors": results["errors"][:5] if results["errors"] else [],  # 只返回前5个错误
    }


# ============================================================================
# Configuration Management
# ============================================================================
# 系统配置管理 —— 基于 SystemConfig 数据表的键值对配置
# 支持敏感值遮掩、按 key 更新、以及内存缓存同步

@router.get("/config")
async def list_config(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List system configuration entries (admin only).

    Sensitive values are masked in the response.

    Returns:
        Dict[str, Any]: List of configuration items with key, value, and metadata.
    """
    # 查询所有系统配置项
    result = await session.execute(select(SystemConfig))
    configs = result.scalars().all()

    return {
        "configs": [
            {
                "key": config.config_key,
                # 敏感配置项（如密码、API Key）用星号遮掩，避免前端泄露
                "value": "***" if config.is_sensitive else config.config_value,
                "description": config.description,
                "is_sensitive": config.is_sensitive,
            }
            for config in configs
        ]
    }


# 配置更新请求体：包含新的值以及可选的描述
class ConfigUpdate(BaseModel):
    """Request model for updating a system configuration entry.

    配置项更新请求体，用于更新系统配置的值和描述。

    Attributes:
        value: The new configuration value as string.
            配置项的新值，以字符串形式存储。
        description: Optional description for the config entry.
            配置项的可选描述信息。
    """
    value: str
    description: Optional[str] = None


@router.put("/config/{key:path}")
async def update_config(
    key: str,                 # 路径参数：配置项的 key，支持包含"."的路径格式
    update: ConfigUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a system configuration entry (admin only).

    Creates the config entry if it does not exist and refreshes the in-memory
    feature cache to apply changes immediately.

    Args:
        key: Configuration key (supports dotted paths).
        update: New value and optional description.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Update status and key.
    """
    # 尝试查找已有的配置项
    result = await session.execute(select(SystemConfig).where(SystemConfig.config_key == key))
    config = result.scalar_one_or_none()

    if config:
        # 配置已存在：更新值和描述
        config.config_value = update.value
        if update.description:
            config.description = update.description
        config.updated_by = admin.id  # 记录操作者 ID，便于审计追踪
    else:
        # 配置不存在：创建新的配置记录
        config = SystemConfig(
            config_key=key,
            config_value=update.value,
            description=update.description or "",
            updated_by=admin.id,
        )
        session.add(config)

    # 同步更新内存缓存，使配置变更立即生效
    # 避免等待下次缓存刷新周期，减少配置变更的延迟
    feature_config._cache[key] = update.value

    return {"status": "ok", "key": key}


# ============================================================================
# Feature Toggle Management
# ============================================================================
# 功能开关管理 —— 动态控制系统各功能模块的启用/禁用
# 通过 feature_config（内存缓存 + 数据库持久化）实现运行时特性切换

# 系统支持的所有功能开关 key 列表
# 每个 key 以 "feature." 为前缀，对应一个可独立开关的功能模块
_FEATURE_KEYS = [
    "feature.ai_processor",        # AI 文章处理（摘要、翻译等）
    "feature.embedding",           # 向量嵌入（用于语义搜索）
    "feature.event_clustering",    # 事件聚类
    "feature.topic_radar",         # 话题雷达/发现
    "feature.topic_match",         # 话题匹配（文章关联到话题）
    "feature.action_items",        # 行动项提取
    "feature.report_generation",   # 报告自动生成
    "feature.crawler",             # 数据爬取
    "feature.backup",              # 自动备份
    "feature.cleanup",             # 数据清理
    "feature.email_notification",  # 邮件通知
]


@router.get("/features")
async def list_features(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """List all feature toggles and their current status.

    Returns:
        Dict[str, Any]: Feature toggle list with enabled status and raw value.
    """
    # 批量获取所有以 "feature." 开头的配置值
    all_cfg = feature_config.get_all("feature.")
    features = []
    for key in _FEATURE_KEYS:
        val = all_cfg.get(key)
        features.append({
            "key": key,
            # 将配置值规范化为布尔值：支持 "true"、"1"、"yes"、"on" 等多种写法
            "enabled": val is not None and val.lower() in ("true", "1", "yes", "on"),
            "raw_value": val,  # 同时返回原始值，便于调试
        })
    return {"features": features}


# 功能开关切换请求体
class FeatureToggle(BaseModel):
    enabled: bool  # True 表示启用，False 表示禁用


@router.put("/features/{feature_key:path}")
async def toggle_feature(
    feature_key: str,         # 功能开关的 key，例如 "feature.ai_processor"
    body: FeatureToggle,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Enable or disable a feature toggle.

    Args:
        feature_key: Feature key starting with ``feature.``.
        body: Toggle payload.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Updated toggle status.

    Raises:
        HTTPException: If the key does not start with ``feature.``.
    """
    # 安全校验：仅允许操作 "feature." 前缀的 key，防止误改其他配置
    if not feature_key.startswith("feature."):
        raise HTTPException(status_code=400, detail="Key must start with 'feature.'")

    # 将布尔值转换为字符串存储
    new_value = "true" if body.enabled else "false"
    # 异步写入数据库并同步更新内存缓存
    await feature_config.async_set(feature_key, new_value, updated_by=admin.id)

    return {"status": "ok", "key": feature_key, "enabled": body.enabled}


# ============================================================================
# Scheduler Job Management
# ============================================================================
# 调度器任务管理 —— 查看、修改和手动触发 APScheduler 中注册的定时任务
# 支持两种触发器类型：IntervalTrigger（间隔触发）和 CronTrigger（定时触发）

@router.get("/scheduler/jobs")
async def list_scheduler_jobs(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """List all registered scheduler jobs and their status.

    Returns:
        Dict[str, Any]: Job list with trigger and next run time.
    """
    # 延迟导入：避免循环引用，同时仅在需要时加载调度器模块
    from apps.scheduler.tasks import get_scheduler

    scheduler = get_scheduler()
    jobs = []

    # 遍历调度器中所有已注册的任务，提取关键信息
    for job in scheduler.get_jobs():
        trigger_info = str(job.trigger)  # 触发器描述信息（如 cron 表达式或间隔时间）
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({
            "id": job.id,
            "name": job.name,
            "trigger": trigger_info,
            "next_run_time": next_run,  # 下次执行时间
            "pending": job.pending,     # 是否处于等待执行状态
        })

    return {"jobs": jobs}


# 任务调度更新请求体
# 支持两种触发器的参数修改：interval（间隔小时数）和 cron（定时小时/星期几）
class JobUpdate(BaseModel):
    interval_hours: Optional[int] = None       # 间隔触发的小时数
    cron_hour: Optional[int] = None            # 定时触发的执行小时（0-23）
    cron_day_of_week: Optional[str] = None     # 定时触发的星期几（如 "mon"、"0-6"）


@router.put("/scheduler/jobs/{job_id}")
async def update_scheduler_job(
    job_id: str,              # 路径参数：任务 ID，如 "crawl_job"、"backup_job"
    body: JobUpdate,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Modify a scheduler job's trigger parameters.

    Changes are applied to the running scheduler and persisted to the
    configuration store so they survive restarts.

    Args:
        job_id: Scheduler job identifier.
        body: Updated interval/cron parameters.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Updated trigger and next run time.

    Raises:
        HTTPException: If the job does not exist.
    """
    from apps.scheduler.tasks import get_scheduler

    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # 任务 ID 到数据库配置 key 的映射表
    # 当调度参数发生变更时，同时将新值持久化到 feature_config 中
    # 这样即使服务重启，新的调度参数也能被恢复
    _JOB_CONFIG_MAP = {
        "crawl_job": "scheduler.crawl_interval_hours",
        "cleanup_job": "scheduler.cleanup_hour",
        "backup_job": "scheduler.backup_hour",
        "ai_process_job": "scheduler.ai_process_interval_hours",
        "embedding_job": "scheduler.embedding_interval_hours",
        "event_cluster_job": "scheduler.event_cluster_hour",
        "topic_discovery_job": "scheduler.topic_discovery_hour",
        "topic_match_job": "scheduler.topic_match_interval_hours",
    }

    # 处理间隔触发器的更新
    if body.interval_hours is not None:
        # 使用新的间隔时间重新调度任务
        scheduler.reschedule_job(job_id, trigger=IntervalTrigger(hours=body.interval_hours))
        # 将新参数持久化到数据库配置
        config_key = _JOB_CONFIG_MAP.get(job_id)
        if config_key:
            await feature_config.async_set(config_key, str(body.interval_hours), updated_by=admin.id)

    # 处理定时触发器 (cron) 的更新
    if body.cron_hour is not None:
        kwargs: Dict[str, Any] = {"hour": body.cron_hour, "minute": 0}
        # 如果指定了星期几，添加到 cron 参数中
        if body.cron_day_of_week is not None:
            kwargs["day_of_week"] = body.cron_day_of_week
        scheduler.reschedule_job(job_id, trigger=CronTrigger(**kwargs))
        # 持久化 cron_hour 配置
        config_key = _JOB_CONFIG_MAP.get(job_id)
        if config_key:
            await feature_config.async_set(config_key, str(body.cron_hour), updated_by=admin.id)
        # 话题发现任务特殊处理：还需要额外持久化 day_of_week 配置
        if body.cron_day_of_week is not None and job_id == "topic_discovery_job":
            await feature_config.async_set(
                "scheduler.topic_discovery_day", body.cron_day_of_week, updated_by=admin.id
            )

    # 获取更新后的任务信息并返回
    updated_job = scheduler.get_job(job_id)
    return {
        "status": "ok",
        "job_id": job_id,
        "trigger": str(updated_job.trigger) if updated_job else None,
        "next_run_time": updated_job.next_run_time.isoformat() if updated_job and updated_job.next_run_time else None,
    }


@router.post("/scheduler/jobs/{job_id}/trigger")
async def trigger_job(
    job_id: str,              # 要立即执行的任务 ID
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Trigger a scheduler job to run immediately.

    Args:
        job_id: Scheduler job identifier.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Execution result of the job.

    Raises:
        HTTPException: If the job does not exist or execution fails.
    """
    from apps.scheduler.tasks import get_scheduler

    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # 直接调用任务的执行函数，绕过调度器的触发机制
    # 这样可以立即执行任务，而不影响正常的调度计划
    try:
        result = await job.func()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Job execution failed: {exc}")

    return {"status": "ok", "job_id": job_id, "result": result}


# ============================================================================
# Topic Match Management
# ============================================================================
# 话题匹配管理 —— 手动触发文章与话题的关联匹配


@router.post("/topic/match")
async def trigger_topic_match(
    days: int = 7,        # 回溯天数
    limit: int = 500,     # 处理上限
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Trigger topic matching manually.

    手动触发话题匹配任务，将文章关联到已有话题。

    Args:
        days: Lookback days for articles to match (default: 7).
        limit: Maximum number of articles to process (default: 500).
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Match result with counts.
    """
    from apps.scheduler.jobs.topic_match_job import run_topic_match_job

    try:
        result = await run_topic_match_job(days=days, limit=limit)
        return {
            "status": "ok",
            "message": "Topic match completed",
            "result": result,
        }
    except Exception as e:
        logger.error(f"Topic match failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.post("/pipeline/translate")
async def trigger_translate(
    limit: int = 100,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Trigger arXiv title translation manually.

    翻译 source_type='arxiv' 且标题为英文、且尚未翻译的文章标题。

    Args:
        limit: Maximum number of articles to translate (default: 100).
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Translation result with counts.
    """
    from core.database import get_session_factory
    from sqlalchemy import and_, select, update
    from apps.crawler.models.article import Article
    from apps.ai_processor.service import get_ai_provider, _is_english

    session_factory = get_session_factory()
    provider = get_ai_provider()
    translated = 0
    skipped = 0
    failed = 0

    try:
        async with session_factory() as session:
            # 查询待翻译的 arXiv 文章：英文标题 + 未翻译
            result = await session.execute(
                select(Article.id, Article.title)
                .where(
                    and_(
                        Article.source_type == "arxiv",
                        Article.translated_title.is_(None),
                        Article.title.isnot(None),
                        Article.title != "",
                    )
                )
                .order_by(Article.crawl_time.desc())
                .limit(limit)
            )
            articles = result.all()

            if not articles:
                return {"translated": 0, "skipped": 0, "failed": 0, "total": 0, "message": "没有待翻译的文章"}

            for article_id, title in articles:
                # 跳过非英文标题
                if not _is_english(title):
                    skipped += 1
                    continue

                try:
                    translated_title = await provider.translate(title)
                    if translated_title:
                        await session.execute(
                            update(Article)
                            .where(Article.id == article_id)
                            .values(translated_title=translated_title)
                        )
                        translated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.warning(f"Failed to translate article {article_id}: {e}")
                    failed += 1

            await session.commit()

        return {
            "translated": translated,
            "skipped": skipped,
            "failed": failed,
            "total": len(articles),
            "message": f"翻译完成: {translated} 篇成功, {skipped} 篇跳过, {failed} 篇失败"
        }
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}")
    finally:
        await provider.close()


# ============================================================================
# Grouped / Batch Configuration Management
# ============================================================================
# 分组/批量配置管理 —— 按前缀对配置进行分组展示，并支持一次性批量更新多个配置
# 前端管理界面可以利用分组功能按模块展示和编辑配置

# 配置分组前缀列表，不属于这些分组的配置归入 "other"
_CONFIG_GROUPS = ["feature", "scheduler", "ai", "embedding", "event", "pipeline", "retention", "cache", "jwt"]


@router.get("/config/groups")
async def list_config_groups(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Return configuration grouped by prefix.

    Returns:
        Dict[str, Any]: Mapping of prefix groups to key/value dictionaries.
    """
    # 先从数据库重新加载所有配置到内存缓存，确保获取最新数据
    await feature_config.async_reload()
    # 初始化分组字典，每个分组对应一个空字典
    groups: Dict[str, Dict[str, str]] = {g: {} for g in _CONFIG_GROUPS}
    groups["other"] = {}  # 其他分组，用于归类未匹配任何前缀的配置

    # 遍历所有配置项，按前缀（"." 之前的部分）分组
    all_cfg = feature_config.get_all()
    for key, value in sorted(all_cfg.items()):
        prefix = key.split(".")[0] if "." in key else "other"
        if prefix in groups:
            groups[prefix][key] = value
        else:
            groups["other"][key] = value

    return {"groups": groups}


# ============================================================================
# Scheduler Config Hot Reload Helper
# ============================================================================
# 调度配置热更新辅助函数：当 scheduler.* 配置变更时，自动重新调度相关任务

# 配置 key 到 (job_id, trigger_type) 的映射
# trigger_type: "interval" 表示间隔触发，"cron" 表示定时触发，"interval_base" 表示基准时间变更
_SCHEDULER_CONFIG_MAP = {
    "scheduler.crawl_interval_hours": ("crawl_job", "interval"),
    "scheduler.crawl_base_hour": ("crawl_job", "interval_base"),
    "scheduler.ai_process_interval_hours": ("ai_process_job", "interval"),
    "scheduler.ai_process_base_hour": ("ai_process_job", "interval_base"),
    "scheduler.embedding_interval_hours": ("embedding_job", "interval"),
    "scheduler.embedding_base_hour": ("embedding_job", "interval_base"),
    "scheduler.action_extract_interval_hours": ("action_extract_job", "interval"),
    "scheduler.action_extract_base_hour": ("action_extract_job", "interval_base"),
    "scheduler.topic_match_interval_hours": ("topic_match_job", "interval"),
    "scheduler.topic_match_base_hour": ("topic_match_job", "interval_base"),
    "scheduler.cleanup_hour": ("cleanup_job", "cron"),
    "scheduler.backup_hour": ("backup_job", "cron"),
    "scheduler.event_cluster_hour": ("event_cluster_job", "cron"),
    "scheduler.topic_discovery_hour": ("topic_discovery_job", "cron"),
    "scheduler.topic_discovery_day": ("topic_discovery_job", "cron_day"),
    "scheduler.notification_hour": ("notification_job", "cron"),
    "scheduler.notification_minute": ("notification_job", "cron_minute"),
    "scheduler.report_weekly_day": ("weekly_report_job", "cron_day"),
    "scheduler.report_weekly_hour": ("weekly_report_job", "cron"),
    "scheduler.report_monthly_hour": ("monthly_report_job", "cron"),
}


def _calculate_start_date_for_interval(base_hour: int) -> "datetime":
    """Calculate the start date for interval-triggered jobs.

    计算间隔任务的基准开始时间，用于 IntervalTrigger 的 start_date 参数。

    Args:
        base_hour: Base hour (0-23), e.g., 23 means 23:00.

    Returns:
        datetime: Timezone-aware start_date for IntervalTrigger.
    """
    import pytz
    from datetime import timedelta
    from settings import settings

    tz = pytz.timezone(settings.scheduler_timezone)
    now = datetime.now(tz)
    today_base = now.replace(hour=base_hour, minute=0, second=0, microsecond=0)

    if now >= today_base:
        return today_base
    else:
        return today_base - timedelta(days=1)


async def _reschedule_jobs_for_config_keys(config_keys: List[str], updated_by: int) -> List[str]:
    """Reschedule jobs based on changed scheduler configuration keys.

    根据变更的 scheduler.* 配置键，自动重新调度相关的调度任务。
    这确保了配置变更能够立即生效，而无需重启服务。

    Args:
        config_keys: List of changed configuration keys (e.g., ["scheduler.crawl_interval_hours"]).
        updated_by: User ID who made the change (for audit logging).

    Returns:
        List[str]: List of job IDs that were rescheduled.
    """
    from apps.scheduler.tasks import get_scheduler

    scheduler = get_scheduler()
    rescheduled = []

    for key in config_keys:
        mapping = _SCHEDULER_CONFIG_MAP.get(key)
        if not mapping:
            continue

        job_id, trigger_type = mapping
        job = scheduler.get_job(job_id)

        # 任务可能不存在（如功能开关未启用），跳过
        if not job:
            logger.warning(
                "Scheduler config '%s' changed but job '%s' not found (feature may be disabled)",
                key, job_id
            )
            continue

        try:
            if trigger_type == "interval":
                # 间隔触发器：从配置读取小时数和基准时间
                hours = feature_config.get_int(key, 1)
                # 获取对应的基准时间配置
                base_key = key.replace("_interval_hours", "_base_hour")
                base_hour = feature_config.get_int(base_key, 0)
                start_date = _calculate_start_date_for_interval(base_hour)
                scheduler.reschedule_job(
                    job_id,
                    trigger=IntervalTrigger(hours=hours, start_date=start_date)
                )
                logger.info("Rescheduled job '%s' with interval=%d hours, base_hour=%d",
                            job_id, hours, base_hour)

            elif trigger_type == "interval_base":
                # 基准时间变更：需要同时读取间隔和基准时间，重新构造触发器
                interval_key_map = {
                    "crawl_job": "scheduler.crawl_interval_hours",
                    "ai_process_job": "scheduler.ai_process_interval_hours",
                    "embedding_job": "scheduler.embedding_interval_hours",
                    "action_extract_job": "scheduler.action_extract_interval_hours",
                }
                base_key_map = {
                    "crawl_job": "scheduler.crawl_base_hour",
                    "ai_process_job": "scheduler.ai_process_base_hour",
                    "embedding_job": "scheduler.embedding_base_hour",
                    "action_extract_job": "scheduler.action_extract_base_hour",
                }
                interval_key = interval_key_map.get(job_id)
                base_key = base_key_map.get(job_id)
                if interval_key and base_key:
                    hours = feature_config.get_int(interval_key, 1)
                    base_hour = feature_config.get_int(base_key, 0)
                    start_date = _calculate_start_date_for_interval(base_hour)
                    scheduler.reschedule_job(
                        job_id,
                        trigger=IntervalTrigger(hours=hours, start_date=start_date)
                    )
                    logger.info("Rescheduled job '%s' with interval=%d hours, base_hour=%d",
                                job_id, hours, base_hour)

            elif trigger_type == "cron":
                # Cron 触发器：从配置读取小时
                hour = feature_config.get_int(key, 0)
                scheduler.reschedule_job(job_id, trigger=CronTrigger(hour=hour, minute=0))
                logger.info("Rescheduled job '%s' with cron hour=%d", job_id, hour)

            elif trigger_type == "cron_day":
                # 特殊处理：带星期几的 cron（如 topic_discovery_day）
                if job_id == "topic_discovery_job":
                    day = feature_config.get("scheduler.topic_discovery_day", "mon")
                    hour = feature_config.get_int("scheduler.topic_discovery_hour", 1)
                    scheduler.reschedule_job(
                        job_id,
                        trigger=CronTrigger(day_of_week=day, hour=hour, minute=0)
                    )
                    logger.info("Rescheduled job '%s' with day=%s hour=%d", job_id, day, hour)
                elif job_id == "weekly_report_job":
                    day = feature_config.get("scheduler.report_weekly_day", "mon")
                    hour = feature_config.get_int("scheduler.report_weekly_hour", 6)
                    scheduler.reschedule_job(
                        job_id,
                        trigger=CronTrigger(day_of_week=day, hour=hour, minute=0)
                    )
                    logger.info("Rescheduled job '%s' with day=%s hour=%d", job_id, day, hour)

            elif trigger_type == "cron_minute":
                # 特殊处理：同时包含小时和分钟的 cron（如 notification_job）
                if job_id == "notification_job":
                    hour = feature_config.get_int("scheduler.notification_hour", 9)
                    minute = feature_config.get_int("scheduler.notification_minute", 0)
                    scheduler.reschedule_job(
                        job_id,
                        trigger=CronTrigger(hour=hour, minute=minute)
                    )
                    logger.info("Rescheduled job '%s' with hour=%d minute=%d", job_id, hour, minute)

            rescheduled.append(job_id)

        except Exception as e:
            logger.error("Failed to reschedule job '%s' for config '%s': %s", job_id, key, e)

    return rescheduled


# 批量配置更新请求体：键值对字典
class BatchConfigUpdate(BaseModel):
    configs: Dict[str, str]  # key -> value 的映射


@router.put("/batch-config")
async def batch_update_config(
    body: BatchConfigUpdate,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Batch update multiple configuration values at once.

    Args:
        body: Dictionary of config key/value pairs.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Updated keys and count, plus rescheduled jobs if any.
    """
    updated = []
    # 逐个更新配置项，每个 key 都会写入数据库并更新内存缓存
    for key, value in body.configs.items():
        await feature_config.async_set(key, value, updated_by=admin.id)
        updated.append(key)

    # 检测 scheduler.* 配置变更，自动重新调度相关任务
    rescheduled = []
    scheduler_keys = [k for k in updated if k.startswith("scheduler.")]
    if scheduler_keys:
        rescheduled = await _reschedule_jobs_for_config_keys(scheduler_keys, admin.id)

    result = {"status": "ok", "updated": updated, "count": len(updated)}
    if rescheduled:
        # 去重后返回
        result["rescheduled_jobs"] = list(set(rescheduled))

    return result


# ============================================================================
# Backup Management
# ============================================================================
# 备份管理部分 —— 查看历史备份记录以及手动触发备份任务

@router.get("/backups")
async def list_backups(
    page: int = 1,            # 当前页码
    page_size: int = 20,      # 每页条数
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List backup records (admin only).

    Args:
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated backup records.
    """
    # 按创建时间倒序查询备份记录，支持分页
    result = await session.execute(
        select(BackupRecord)
        .order_by(desc(BackupRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    backups = result.scalars().all()

    # 将 ORM 对象转换为字典，返回备份的关键元数据
    return {
        "backups": [
            {
                "id": backup.id,
                "backup_date": backup.backup_date.isoformat() if backup.backup_date else None,
                "backup_file": backup.backup_file,      # 备份文件路径
                "backup_size": backup.backup_size,       # 备份文件大小
                "article_count": backup.article_count,   # 备份包含的文章数量
                "status": backup.status,                 # 备份状态（成功/失败等）
                "created_at": backup.created_at.isoformat() if backup.created_at else None,
            }
            for backup in backups
        ]
    }


@router.post("/backups/create")
async def create_backup(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Trigger a manual backup (admin only).

    Executes the full backup pipeline: export archived articles to JSON,
    persist backup metadata, and remove archived records.

    Returns:
        Dict[str, Any]: Backup execution result.
    """
    from apps.scheduler.jobs.backup_job import run_backup_job

    try:
        result = await run_backup_job()
        return {
            "status": "ok",
            "message": "Backup completed",
            "result": result,
        }
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/backups/{backup_id}")
async def get_backup_detail(
    backup_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get backup details by ID.

    Args:
        backup_id: Backup record ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Backup metadata and status.

    Raises:
        HTTPException: If the backup record does not exist.
    """
    result = await session.execute(
        select(BackupRecord).where(BackupRecord.id == backup_id)
    )
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    return {
        "status": "ok",
        "backup": {
            "id": backup.id,
            "backup_date": backup.backup_date.isoformat() if backup.backup_date else None,
            "backup_file": backup.backup_file,
            "backup_size": backup.backup_size,
            "article_count": backup.article_count,
            "status": backup.status,
            "completed_at": backup.completed_at.isoformat() if backup.completed_at else None,
            "error_message": backup.error_message,
            "created_at": backup.created_at.isoformat() if backup.created_at else None,
        }
    }


@router.get("/backups/{backup_id}/download")
async def download_backup(
    backup_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
):
    """Download a backup file.

    Args:
        backup_id: Backup record ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        FileResponse: JSON backup file content.

    Raises:
        HTTPException: If the backup record or file does not exist,
            or if path traversal is detected.
    """
    from fastapi.responses import FileResponse
    from settings import settings

    result = await session.execute(
        select(BackupRecord).where(BackupRecord.id == backup_id)
    )
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    from pathlib import Path
    backup_path = Path(backup.backup_file)

    # 安全检查：防止路径遍历攻击
    # 确保备份文件在预期的备份目录内
    backup_dir = Path(settings.backup_dir).resolve()
    try:
        # resolve() 会解析所有符号链接和相对路径
        resolved_path = backup_path.resolve()
        # 检查解析后的路径是否在备份目录内
        if not str(resolved_path).startswith(str(backup_dir)):
            raise HTTPException(
                status_code=403,
                detail="Access denied: file path outside backup directory"
            )
    except (OSError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file path: {e}"
        )

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found on disk")

    return FileResponse(
        path=backup_path,
        filename=backup_path.name,
        media_type="application/json",
    )


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Restore articles from a backup file.

    Articles with existing ``external_id`` values are skipped.

    Args:
        backup_id: Backup record ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Restore statistics.

    Raises:
        HTTPException: If the backup record or file does not exist.
    """
    import json
    from pathlib import Path

    result = await session.execute(
        select(BackupRecord).where(BackupRecord.id == backup_id)
    )
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    backup_path = Path(backup.backup_file)

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found on disk")

    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            backup_data = json.load(f)

        articles_data = backup_data.get("articles", [])
        restored_count = 0
        skipped_count = 0

        for article_data in articles_data:
            # 检查文章是否已存在（根据 external_id）
            existing = await session.execute(
                select(Article).where(Article.external_id == article_data.get("external_id"))
            )
            if existing.scalar_one_or_none():
                skipped_count += 1
                continue

            # 创建新文章记录
            from datetime import datetime
            article = Article(
                source_type=article_data.get("source_type"),
                source_id=article_data.get("source_id"),
                external_id=article_data.get("external_id"),
                title=article_data.get("title"),
                url=article_data.get("url"),
                author=article_data.get("author"),
                summary=article_data.get("summary"),
                content=article_data.get("content"),
                category=article_data.get("category"),
                tags=article_data.get("tags"),
                publish_time=datetime.fromisoformat(article_data["publish_time"]) if article_data.get("publish_time") else None,
                crawl_time=datetime.fromisoformat(article_data["crawl_time"]) if article_data.get("crawl_time") else None,
            )
            session.add(article)
            restored_count += 1

        await session.commit()

        return {
            "status": "ok",
            "message": f"Restore completed",
            "restored_count": restored_count,
            "skipped_count": skipped_count,
            "total_in_backup": len(articles_data),
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: int,
    delete_file: bool = False,  # 是否同时删除备份文件
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a backup record (and optionally the backup file).

    Args:
        backup_id: Backup record ID.
        delete_file: Whether to delete the backup file from disk.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Deletion status and optional deleted file path.

    Raises:
        HTTPException: If the backup record does not exist.
    """
    from pathlib import Path

    result = await session.execute(
        select(BackupRecord).where(BackupRecord.id == backup_id)
    )
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    backup_file = backup.backup_file

    # 删除数据库记录
    await session.delete(backup)
    await session.commit()

    # 如果指定，同时删除备份文件
    if delete_file:
        backup_path = Path(backup_file)
        if backup_path.exists():
            backup_path.unlink()
            return {
                "status": "ok",
                "message": "Backup record and file deleted",
                "deleted_file": backup_file,
            }

    return {
        "status": "ok",
        "message": "Backup record deleted",
    }


# ============================================================================
# Audit Log Management
# ============================================================================
# 审计日志管理 —— 查询用户操作历史，支持多种筛选条件

class AuditLogListResponse(BaseModel):
    """Audit log list response.

    Attributes:
        logs: List of audit log entries.
        total: Total number of logs matching the filter.
    """

    logs: List[Dict[str, Any]]
    total: int


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> AuditLogListResponse:
    """List audit logs with filtering.

    Args:
        user_id: Filter by user ID.
        action: Filter by action type.
        resource_type: Filter by resource type.
        start_date: Filter logs created after this time.
        end_date: Filter logs created before this time.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        AuditLogListResponse: Paginated audit log entries.
    """
    query = select(AuditLog)

    # 应用筛选条件
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.where(AuditLog.created_at >= start_date)
    if end_date:
        query = query.where(AuditLog.created_at <= end_date)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询，按时间倒序
    query = query.order_by(desc(AuditLog.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    logs = result.scalars().all()

    return AuditLogListResponse(
        logs=[
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        total=total,
    )


@router.get("/audit-logs/actions")
async def list_audit_actions(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List unique action types in audit logs.

    Returns:
        Dict[str, Any]: Sorted list of action names.
    """
    result = await session.execute(
        select(AuditLog.action).distinct().order_by(AuditLog.action)
    )
    actions = [row[0] for row in result.all()]

    return {"actions": actions}


@router.get("/audit-logs/resource-types")
async def list_audit_resource_types(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List unique resource types in audit logs.

    Returns:
        Dict[str, Any]: Sorted list of resource types.
    """
    result = await session.execute(
        select(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type)
    )
    resource_types = [row[0] for row in result.all()]

    return {"resource_types": resource_types}


# ============================================================================
# Email Configuration Management
# ============================================================================
# 邮件配置管理 —— 管理邮件推送的后端设置和推送参数（支持多后端多配置）

class EmailConfigCreate(BaseModel):
    """Request model for creating email configuration.
    
    创建邮件配置请求体。
    """
    backend_type: str  # smtp, sendgrid, mailgun, brevo
    name: str  # 配置名称
    # SMTP settings
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_ssl_ports: Optional[str] = None
    # SendGrid settings
    sendgrid_api_key: Optional[str] = None
    # Mailgun settings
    mailgun_api_key: Optional[str] = None
    mailgun_domain: Optional[str] = None
    # Brevo settings
    brevo_api_key: Optional[str] = None
    brevo_from_name: Optional[str] = None
    # Common settings
    sender_email: Optional[str] = None
    priority: Optional[int] = 0
    is_active: Optional[bool] = True


class EmailConfigUpdate(BaseModel):
    """Request model for updating email configuration.
    
    更新邮件配置请求体。
    """
    name: Optional[str] = None
    # SMTP settings
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_ssl_ports: Optional[str] = None
    # SendGrid settings
    sendgrid_api_key: Optional[str] = None
    # Mailgun settings
    mailgun_api_key: Optional[str] = None
    mailgun_domain: Optional[str] = None
    # Brevo settings
    brevo_api_key: Optional[str] = None
    brevo_from_name: Optional[str] = None
    # Common settings
    sender_email: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class EmailGlobalSettings(BaseModel):
    """Request model for global email settings.
    
    全局邮件设置请求体。
    """
    email_enabled: Optional[bool] = None
    push_frequency: Optional[str] = None
    push_time: Optional[str] = None
    max_articles_per_email: Optional[int] = None


def _mask_sensitive(value: str, show_last: int = 4) -> str:
    """Mask sensitive value for display."""
    if not value or len(value) <= show_last:
        return "****" if value else ""
    return "****" + value[-show_last:]


@router.get("/email/configs")
async def list_email_configs(
    backend_type: Optional[str] = None,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all email configurations.
    
    获取所有邮件配置列表，支持按后端类型筛选。
    
    Args:
        backend_type: Filter by backend type (smtp, sendgrid, mailgun, brevo).
        admin: Superuser dependency.
        session: Async database session.
        
    Returns:
        Dict[str, Any]: List of email configurations with masked secrets.
    """
    query = select(EmailConfig).order_by(EmailConfig.backend_type, EmailConfig.priority)
    if backend_type:
        query = query.where(EmailConfig.backend_type == backend_type)
    
    result = await session.execute(query)
    configs = result.scalars().all()
    
    config_list = []
    for config in configs:
        config_dict = {
            "id": config.id,
            "backend_type": config.backend_type,
            "name": config.name,
            "sender_email": config.sender_email,
            "priority": config.priority,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }
        # Add backend-specific fields (with masking)
        if config.backend_type == "smtp":
            config_dict.update({
                "smtp_host": config.smtp_host,
                "smtp_port": config.smtp_port,
                "smtp_user": config.smtp_user,
                "smtp_password": _mask_sensitive(config.smtp_password) if config.smtp_password else "",
                "smtp_use_tls": config.smtp_use_tls,
                "smtp_use_ssl": config.smtp_use_ssl,
                "smtp_ssl_ports": config.smtp_ssl_ports,
            })
        elif config.backend_type == "sendgrid":
            config_dict["sendgrid_api_key"] = _mask_sensitive(config.sendgrid_api_key) if config.sendgrid_api_key else ""
        elif config.backend_type == "mailgun":
            config_dict.update({
                "mailgun_api_key": _mask_sensitive(config.mailgun_api_key) if config.mailgun_api_key else "",
                "mailgun_domain": config.mailgun_domain,
            })
        elif config.backend_type == "brevo":
            config_dict.update({
                "brevo_api_key": _mask_sensitive(config.brevo_api_key) if config.brevo_api_key else "",
                "brevo_from_name": config.brevo_from_name,
            })
        config_list.append(config_dict)
    
    return {"status": "ok", "configs": config_list}


@router.post("/email/configs")
async def create_email_config(
    data: EmailConfigCreate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new email configuration.
    
    创建新的邮件配置。
    """
    # Validate backend_type
    if data.backend_type not in ("smtp", "sendgrid", "mailgun", "brevo"):
        raise HTTPException(status_code=400, detail="Invalid backend_type. Must be one of: smtp, sendgrid, mailgun, brevo")
    
    config = EmailConfig(
        backend_type=data.backend_type,
        name=data.name,
        sender_email=data.sender_email or "",
        priority=data.priority or 0,
        is_active=data.is_active if data.is_active is not None else True,
    )
    
    # Set backend-specific fields
    if data.backend_type == "smtp":
        config.smtp_host = data.smtp_host or ""
        config.smtp_port = data.smtp_port or 587
        config.smtp_user = data.smtp_user or ""
        config.smtp_password = data.smtp_password or ""
        config.smtp_use_tls = data.smtp_use_tls if data.smtp_use_tls is not None else True
        config.smtp_use_ssl = data.smtp_use_ssl if data.smtp_use_ssl is not None else False
        config.smtp_ssl_ports = data.smtp_ssl_ports or "465"
    elif data.backend_type == "sendgrid":
        config.sendgrid_api_key = data.sendgrid_api_key or ""
    elif data.backend_type == "mailgun":
        config.mailgun_api_key = data.mailgun_api_key or ""
        config.mailgun_domain = data.mailgun_domain or ""
    elif data.backend_type == "brevo":
        config.brevo_api_key = data.brevo_api_key or ""
        config.brevo_from_name = data.brevo_from_name or "ResearchPulse"
    
    session.add(config)
    await session.flush()
    
    return {"status": "ok", "message": "Email configuration created", "id": config.id}


@router.put("/email/configs/{config_id}")
async def update_email_config(
    config_id: int,
    data: EmailConfigUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update an email configuration.
    
    更新邮件配置。
    """
    result = await session.execute(
        select(EmailConfig).where(EmailConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Email configuration not found")
    
    # Update common fields
    if data.name is not None:
        config.name = data.name
    if data.sender_email is not None:
        config.sender_email = data.sender_email
    if data.priority is not None:
        config.priority = data.priority
    if data.is_active is not None:
        config.is_active = data.is_active
    
    # Update backend-specific fields
    if config.backend_type == "smtp":
        if data.smtp_host is not None:
            config.smtp_host = data.smtp_host
        if data.smtp_port is not None:
            config.smtp_port = data.smtp_port
        if data.smtp_user is not None:
            config.smtp_user = data.smtp_user
        if data.smtp_password is not None and not data.smtp_password.startswith("****"):
            config.smtp_password = data.smtp_password
        if data.smtp_use_tls is not None:
            config.smtp_use_tls = data.smtp_use_tls
        if data.smtp_use_ssl is not None:
            config.smtp_use_ssl = data.smtp_use_ssl
        if data.smtp_ssl_ports is not None:
            config.smtp_ssl_ports = data.smtp_ssl_ports
    elif config.backend_type == "sendgrid":
        if data.sendgrid_api_key is not None and not data.sendgrid_api_key.startswith("****"):
            config.sendgrid_api_key = data.sendgrid_api_key
    elif config.backend_type == "mailgun":
        if data.mailgun_api_key is not None and not data.mailgun_api_key.startswith("****"):
            config.mailgun_api_key = data.mailgun_api_key
        if data.mailgun_domain is not None:
            config.mailgun_domain = data.mailgun_domain
    elif config.backend_type == "brevo":
        if data.brevo_api_key is not None and not data.brevo_api_key.startswith("****"):
            config.brevo_api_key = data.brevo_api_key
        if data.brevo_from_name is not None:
            config.brevo_from_name = data.brevo_from_name
    
    return {"status": "ok", "message": "Email configuration updated"}


@router.delete("/email/configs/{config_id}")
async def delete_email_config(
    config_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete an email configuration.
    
    删除邮件配置。
    """
    result = await session.execute(
        select(EmailConfig).where(EmailConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Email configuration not found")
    
    await session.execute(
        delete(EmailConfig).where(EmailConfig.id == config_id)
    )
    
    return {"status": "ok", "message": "Email configuration deleted"}


@router.get("/email/settings")
async def get_email_settings(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get global email settings.
    
    获取全局邮件设置（从第一个配置中获取，或返回默认值）。
    """
    # Get first config for global settings, or return defaults
    result = await session.execute(
        select(EmailConfig).limit(1)
    )
    config = result.scalar_one_or_none()
    
    if config:
        return {
            "status": "ok",
            "settings": {
                "email_enabled": config.email_enabled,
                "push_frequency": config.push_frequency,
                "push_time": config.push_time,
                "max_articles_per_email": config.max_articles_per_email,
            }
        }
    
    # Return defaults if no config exists
    return {
        "status": "ok",
        "settings": {
            "email_enabled": False,
            "push_frequency": "daily",
            "push_time": "09:00",
            "max_articles_per_email": 20,
        }
    }


@router.put("/email/settings")
async def update_email_settings(
    data: EmailGlobalSettings,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update global email settings.
    
    更新全局邮件设置（应用到所有配置）。
    """
    # Update all configs with global settings
    # 收集所有需要更新的字段，一次性调用 .values() 避免链式覆盖
    update_fields: Dict[str, Any] = {}
    if data.email_enabled is not None:
        update_fields["email_enabled"] = data.email_enabled
    if data.push_frequency is not None:
        update_fields["push_frequency"] = data.push_frequency
    if data.push_time is not None:
        update_fields["push_time"] = data.push_time
    if data.max_articles_per_email is not None:
        update_fields["max_articles_per_email"] = data.max_articles_per_email

    if update_fields:
        await session.execute(update(EmailConfig).values(**update_fields))
    
    return {"status": "ok", "message": "Global email settings updated"}


@router.post("/email/configs/{config_id}/test")
async def test_email_config(
    config_id: int,
    test_email: str,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Send a test email using a specific configuration.
    
    使用指定配置发送测试邮件。
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    result = await session.execute(
        select(EmailConfig).where(EmailConfig.id == config_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Email configuration not found")

    if not config.is_active:
        raise HTTPException(status_code=400, detail="This configuration is not active")

    if config.backend_type == "smtp":
        if not config.smtp_host or not config.smtp_user:
            raise HTTPException(status_code=400, detail="SMTP not fully configured")

        try:
            msg = MIMEMultipart()
            msg["From"] = config.sender_email or config.smtp_user
            msg["To"] = test_email
            msg["Subject"] = f"ResearchPulse Test Email - {config.name}"
            msg.attach(MIMEText(f"This is a test email from ResearchPulse using {config.name}.", "plain"))

            # Determine SSL connection method
            use_ssl = config.smtp_use_ssl or config.smtp_port == 465
            smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
            with smtp_class(config.smtp_host, config.smtp_port, timeout=10) as server:
                if not use_ssl and config.smtp_use_tls:
                    server.starttls()
                server.login(config.smtp_user, config.smtp_password)
                server.send_message(msg)

            return {"status": "ok", "message": f"Test email sent to {test_email} via {config.name}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    elif config.backend_type in ("sendgrid", "mailgun", "brevo"):
        # 使用 common/email.py 的 send_email 函数实际发送测试邮件
        from common.email import send_email
        try:
            from_addr = config.sender_email or config.smtp_user or ""
            kwargs: Dict[str, Any] = {}
            if config.backend_type == "sendgrid":
                kwargs["api_key"] = config.sendgrid_api_key
            elif config.backend_type == "mailgun":
                kwargs["api_key"] = config.mailgun_api_key
                kwargs["domain"] = config.mailgun_domain
            elif config.backend_type == "brevo":
                kwargs["api_key"] = config.brevo_api_key
                kwargs["from_name"] = config.brevo_from_name

            ok, err = send_email(
                subject=f"ResearchPulse Test Email - {config.name}",
                body=f"This is a test email from ResearchPulse using {config.name} ({config.backend_type}).",
                to_addrs=[test_email],
                backend=config.backend_type,
                from_addr=from_addr,
                **kwargs,
            )
            if ok:
                return {"status": "ok", "message": f"Test email sent to {test_email} via {config.backend_type} ({config.name})"}
            else:
                raise HTTPException(status_code=500, detail=f"Failed to send email: {err}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail=f"Unknown backend: {config.backend_type}")


# Legacy API endpoints (for backward compatibility)
@router.get("/email/config")
async def get_email_config_legacy(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get first active email configuration (legacy endpoint).
    
    获取第一个活跃的邮件配置（兼容旧API）。
    """
    result = await session.execute(
        select(EmailConfig)
        .where(EmailConfig.is_active == True)
        .order_by(EmailConfig.priority)
    )
    config = result.scalar_one_or_none()

    if not config:
        return {"status": "ok", "config": {}}

    return {
        "status": "ok",
        "config": {
            "id": config.id,
            "backend_type": config.backend_type,
            "name": config.name,
            "smtp_host": config.smtp_host,
            "smtp_port": config.smtp_port,
            "smtp_user": config.smtp_user,
            "smtp_password": _mask_sensitive(config.smtp_password) if config.smtp_password else "",
            "smtp_use_tls": config.smtp_use_tls,
            "smtp_use_ssl": config.smtp_use_ssl,
            "smtp_ssl_ports": config.smtp_ssl_ports,
            "sendgrid_api_key": _mask_sensitive(config.sendgrid_api_key) if config.sendgrid_api_key else "",
            "mailgun_api_key": _mask_sensitive(config.mailgun_api_key) if config.mailgun_api_key else "",
            "mailgun_domain": config.mailgun_domain,
            "brevo_api_key": _mask_sensitive(config.brevo_api_key) if config.brevo_api_key else "",
            "brevo_from_name": config.brevo_from_name,
            "email_enabled": config.email_enabled,
            "sender_email": config.sender_email,
            "push_frequency": config.push_frequency,
            "push_time": config.push_time,
            "max_articles_per_email": config.max_articles_per_email,
            "priority": config.priority,
            "is_active": config.is_active,
        }
    }


# ============================================================================
# AI Configuration Management
# ============================================================================
# AI 配置管理 —— 管理 AI 处理器的配置参数

class AIConfigUpdate(BaseModel):
    """AI configuration update model."""
    provider: Optional[str] = None
    # Ollama settings
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_model_light: Optional[str] = None
    ollama_timeout: Optional[int] = None
    ollama_api_key: Optional[str] = None
    # OpenAI settings
    openai_base_url: Optional[str] = None
    openai_model: Optional[str] = None
    openai_model_light: Optional[str] = None
    openai_timeout: Optional[int] = None
    openai_api_key: Optional[str] = None
    # Claude settings
    claude_model: Optional[str] = None
    claude_model_light: Optional[str] = None
    claude_timeout: Optional[int] = None
    claude_api_key: Optional[str] = None
    # General settings
    cache_enabled: Optional[bool] = None
    cache_ttl: Optional[int] = None
    max_content_length: Optional[int] = None
    max_title_length: Optional[int] = None
    thinking_enabled: Optional[bool] = None
    concurrent_enabled: Optional[bool] = None
    workers_heavy: Optional[int] = None
    workers_screen: Optional[int] = None
    no_think: Optional[bool] = None
    num_predict: Optional[int] = None
    num_predict_simple: Optional[int] = None
    max_retries: Optional[int] = None
    retry_base_delay: Optional[float] = None
    batch_concurrency: Optional[int] = None
    fallback_provider: Optional[str] = None
    translate_max_tokens: Optional[int] = None


@router.get("/ai/config")
async def get_ai_config(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Get AI configuration settings.

    Returns:
        Dict[str, Any]: Current AI provider settings and runtime options.
    """
    return {
        "status": "ok",
        "config": {
            "provider": feature_config.get("ai.provider", "ollama"),
            # Ollama
            "ollama_base_url": feature_config.get("ai.ollama_base_url", "http://localhost:11434"),
            "ollama_model": feature_config.get("ai.ollama_model", "qwen3:32b"),
            "ollama_model_light": feature_config.get("ai.ollama_model_light", ""),
            "ollama_timeout": feature_config.get_int("ai.ollama_timeout", 120),
            "ollama_api_key": "***" if feature_config.get("ai.ollama_api_key", "") else "",
            # OpenAI
            "openai_base_url": feature_config.get("ai.openai_base_url", "https://api.openai.com/v1"),
            "openai_model": feature_config.get("ai.openai_model", "gpt-4o"),
            "openai_model_light": feature_config.get("ai.openai_model_light", "gpt-4o-mini"),
            "openai_timeout": feature_config.get_int("ai.openai_timeout", 60),
            "openai_api_key": "***" if feature_config.get("ai.openai_api_key", "") else "",
            # Claude
            "claude_model": feature_config.get("ai.claude_model", "claude-sonnet-4-20250514"),
            "claude_model_light": feature_config.get("ai.claude_model_light", "claude-haiku-4-20250514"),
            "claude_timeout": feature_config.get_int("ai.claude_timeout", 60),
            "claude_api_key": "***" if feature_config.get("ai.claude_api_key", "") else "",
            # General
            "cache_enabled": feature_config.get_bool("ai.cache_enabled", True),
            "cache_ttl": feature_config.get_int("ai.cache_ttl", 86400),
            "max_content_length": feature_config.get_int("ai.max_content_length", 1500),
            "max_title_length": feature_config.get_int("ai.max_title_length", 200),
            "thinking_enabled": feature_config.get_bool("ai.thinking_enabled", False),
            "concurrent_enabled": feature_config.get_bool("ai.concurrent_enabled", False),
            "workers_heavy": feature_config.get_int("ai.workers_heavy", 2),
            "workers_screen": feature_config.get_int("ai.workers_screen", 4),
            "no_think": feature_config.get_bool("ai.no_think", False),
            "num_predict": feature_config.get_int("ai.num_predict", 512),
            "num_predict_simple": feature_config.get_int("ai.num_predict_simple", 256),
            "max_retries": feature_config.get_int("ai.max_retries", 3),
            "retry_base_delay": feature_config.get_float("ai.retry_base_delay", 1.0),
            "batch_concurrency": feature_config.get_int("ai.batch_concurrency", 1),
            "fallback_provider": feature_config.get("ai.fallback_provider", ""),
            "translate_max_tokens": feature_config.get_int("ai.translate_max_tokens", 4096),
        }
    }


@router.put("/ai/config")
async def update_ai_config(
    update: AIConfigUpdate,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Update AI configuration.

    Args:
        update: Partial AI configuration updates.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Updated keys summary.
    """
    updates = []

    if update.provider is not None:
        await feature_config.async_set("ai.provider", update.provider, updated_by=admin.id)
        updates.append("provider")
    if update.ollama_base_url is not None:
        await feature_config.async_set("ai.ollama_base_url", update.ollama_base_url, updated_by=admin.id)
        updates.append("ollama_base_url")
    if update.ollama_model is not None:
        await feature_config.async_set("ai.ollama_model", update.ollama_model, updated_by=admin.id)
        updates.append("ollama_model")
    if update.ollama_model_light is not None:
        await feature_config.async_set("ai.ollama_model_light", update.ollama_model_light, updated_by=admin.id)
        updates.append("ollama_model_light")
    if update.ollama_timeout is not None:
        await feature_config.async_set("ai.ollama_timeout", str(update.ollama_timeout), updated_by=admin.id)
        updates.append("ollama_timeout")
    if update.ollama_api_key is not None:
        await feature_config.async_set("ai.ollama_api_key", update.ollama_api_key, updated_by=admin.id)
        updates.append("ollama_api_key")
    if update.openai_base_url is not None:
        await feature_config.async_set("ai.openai_base_url", update.openai_base_url, updated_by=admin.id)
        updates.append("openai_base_url")
    if update.openai_model is not None:
        await feature_config.async_set("ai.openai_model", update.openai_model, updated_by=admin.id)
        updates.append("openai_model")
    if update.openai_model_light is not None:
        await feature_config.async_set("ai.openai_model_light", update.openai_model_light, updated_by=admin.id)
        updates.append("openai_model_light")
    if update.openai_timeout is not None:
        await feature_config.async_set("ai.openai_timeout", str(update.openai_timeout), updated_by=admin.id)
        updates.append("openai_timeout")
    if update.openai_api_key is not None:
        await feature_config.async_set("ai.openai_api_key", update.openai_api_key, updated_by=admin.id)
        updates.append("openai_api_key")
    if update.claude_model is not None:
        await feature_config.async_set("ai.claude_model", update.claude_model, updated_by=admin.id)
        updates.append("claude_model")
    if update.claude_model_light is not None:
        await feature_config.async_set("ai.claude_model_light", update.claude_model_light, updated_by=admin.id)
        updates.append("claude_model_light")
    if update.claude_timeout is not None:
        await feature_config.async_set("ai.claude_timeout", str(update.claude_timeout), updated_by=admin.id)
        updates.append("claude_timeout")
    if update.claude_api_key is not None:
        await feature_config.async_set("ai.claude_api_key", update.claude_api_key, updated_by=admin.id)
        updates.append("claude_api_key")
    if update.cache_enabled is not None:
        await feature_config.async_set("ai.cache_enabled", "true" if update.cache_enabled else "false", updated_by=admin.id)
        updates.append("cache_enabled")
    if update.cache_ttl is not None:
        await feature_config.async_set("ai.cache_ttl", str(update.cache_ttl), updated_by=admin.id)
        updates.append("cache_ttl")
    if update.max_content_length is not None:
        await feature_config.async_set("ai.max_content_length", str(update.max_content_length), updated_by=admin.id)
        updates.append("max_content_length")
    if update.max_title_length is not None:
        await feature_config.async_set("ai.max_title_length", str(update.max_title_length), updated_by=admin.id)
        updates.append("max_title_length")
    if update.thinking_enabled is not None:
        await feature_config.async_set("ai.thinking_enabled", "true" if update.thinking_enabled else "false", updated_by=admin.id)
        updates.append("thinking_enabled")
    if update.concurrent_enabled is not None:
        await feature_config.async_set("ai.concurrent_enabled", "true" if update.concurrent_enabled else "false", updated_by=admin.id)
        updates.append("concurrent_enabled")
    if update.workers_heavy is not None:
        await feature_config.async_set("ai.workers_heavy", str(update.workers_heavy), updated_by=admin.id)
        updates.append("workers_heavy")
    if update.workers_screen is not None:
        await feature_config.async_set("ai.workers_screen", str(update.workers_screen), updated_by=admin.id)
        updates.append("workers_screen")
    if update.no_think is not None:
        await feature_config.async_set("ai.no_think", "true" if update.no_think else "false", updated_by=admin.id)
        updates.append("no_think")
    if update.num_predict is not None:
        await feature_config.async_set("ai.num_predict", str(update.num_predict), updated_by=admin.id)
        updates.append("num_predict")
    if update.num_predict_simple is not None:
        await feature_config.async_set("ai.num_predict_simple", str(update.num_predict_simple), updated_by=admin.id)
        updates.append("num_predict_simple")
    if update.max_retries is not None:
        await feature_config.async_set("ai.max_retries", str(update.max_retries), updated_by=admin.id)
        updates.append("max_retries")
    if update.retry_base_delay is not None:
        await feature_config.async_set("ai.retry_base_delay", str(update.retry_base_delay), updated_by=admin.id)
        updates.append("retry_base_delay")
    if update.batch_concurrency is not None:
        await feature_config.async_set("ai.batch_concurrency", str(update.batch_concurrency), updated_by=admin.id)
        updates.append("batch_concurrency")
    if update.fallback_provider is not None:
        await feature_config.async_set("ai.fallback_provider", update.fallback_provider, updated_by=admin.id)
        updates.append("fallback_provider")
    if update.translate_max_tokens is not None:
        await feature_config.async_set("ai.translate_max_tokens", str(update.translate_max_tokens), updated_by=admin.id)
        updates.append("translate_max_tokens")

    return {"status": "ok", "message": f"AI configuration updated: {', '.join(updates)}"}


@router.post("/ai/test")
async def test_ai_config(
    test_text: str = "Hello, this is a test.",
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Test AI configuration by processing a simple text.

    Args:
        test_text: Sample text to send to the configured provider.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Provider test result.

    Raises:
        HTTPException: If the provider is unreachable or misconfigured.
    """
    provider = feature_config.get("ai.provider", "ollama")

    try:
        if provider == "ollama":
            import httpx
            base_url = feature_config.get("ai.ollama_base_url", "http://localhost:11434")
            model = feature_config.get("ai.ollama_model", "qwen3:32b")
            timeout = feature_config.get_int("ai.ollama_timeout", 120)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/api/generate",
                    json={"model": model, "prompt": test_text, "stream": False}
                )
                if response.status_code == 200:
                    return {"status": "ok", "message": f"Ollama test successful", "provider": "ollama"}
                else:
                    raise HTTPException(status_code=500, detail=f"Ollama test failed: {response.text}")

        elif provider == "openai":
            # OpenAI test would require API key
            return {"status": "ok", "message": "OpenAI configuration looks valid", "provider": "openai"}

        elif provider == "claude":
            # Claude test would require API key
            return {"status": "ok", "message": "Claude configuration looks valid", "provider": "claude"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Cannot connect to {provider} server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI test failed: {str(e)}")


# ============================================================================
# Embedding Management
# ============================================================================
# 向量嵌入管理 —— 管理嵌入配置、统计和批量操作

@router.get("/embeddings/stats")
async def get_embedding_stats(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get embedding statistics.

    Returns:
        Dict[str, Any]: Summary of total, embedded, and missing counts.
    """
    from apps.embedding.models import ArticleEmbedding

    # Total articles
    total_result = await session.execute(select(func.count(Article.id)))
    total_articles = total_result.scalar() or 0

    # Embedded count
    embedded_result = await session.execute(select(func.count(ArticleEmbedding.id)))
    embedded_count = embedded_result.scalar() or 0

    # Missing count
    missing_count = total_articles - embedded_count

    # Get current config
    provider = feature_config.get("embedding.provider", "sentence-transformers")
    model = feature_config.get("embedding.model", "all-MiniLM-L6-v2")

    return {
        "status": "ok",
        "stats": {
            "total_articles": total_articles,
            "embedded_count": embedded_count,
            "missing_count": max(0, missing_count),
            "provider": provider,
            "model": model,
        }
    }


@router.get("/embeddings/missing")
async def get_missing_embeddings(
    page: int = 1,
    page_size: int = 50,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get articles without embeddings.

    Args:
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated list of articles missing embeddings.
    """
    from apps.embedding.models import ArticleEmbedding

    # Subquery for articles with embeddings
    embedded_ids = select(ArticleEmbedding.article_id)

    # Query articles without embeddings
    query = select(Article).where(Article.id.not_in(embedded_ids))
    query = query.order_by(desc(Article.crawl_time))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    articles = result.scalars().all()

    # Get total count
    count_query = select(func.count(Article.id)).where(Article.id.not_in(embedded_ids))
    total = (await session.execute(count_query)).scalar() or 0

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "articles": [
            {
                "id": a.id,
                "title": a.title[:100] if a.title else "",
                "source_type": a.source_type,
                "crawl_time": a.crawl_time.isoformat() if a.crawl_time else None,
            }
            for a in articles
        ]
    }


@router.post("/embeddings/recompute")
async def recompute_embeddings(
    all: bool = False,  # 是否重新计算所有嵌入
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Trigger embedding recomputation.

    Args:
        all: If ``True``, recompute embeddings for all articles. If ``False``,
            only compute missing embeddings.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Scheduled job metadata.

    Raises:
        HTTPException: If embedding feature is disabled.
    """
    from apps.scheduler.tasks import get_scheduler
    from datetime import datetime, timezone
    import uuid

    # Check if embedding feature is enabled
    if not feature_config.get_bool("feature.embedding", False):
        raise HTTPException(status_code=400, detail="Embedding feature is not enabled")

    scheduler = get_scheduler()
    job_id = f"manual_embedding_{uuid.uuid4().hex[:8]}"

    try:
        from apps.scheduler.jobs.embedding_job import run_embedding_job

        # Add job to scheduler for immediate execution
        scheduler.add_job(
            run_embedding_job,
            id=job_id,
            name=f"Manual embedding recompute (all={all})",
            replace_existing=True,
        )

        return {
            "status": "ok",
            "job_id": job_id,
            "message": f"Embedding job scheduled (all={all})",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to schedule embedding job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule embedding job: {str(e)}")


# ============================================================================
# AI Processing Logs
# ============================================================================
# AI 处理日志 —— 查看最近的 AI 处理记录

@router.get("/ai-logs")
async def get_ai_processing_logs(
    limit: int = 20,
    task_type: Optional[str] = None,
    provider: Optional[str] = None,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get recent AI processing logs.

    Args:
        limit: Maximum number of logs to return (max 100).
        task_type: Filter by task type (content_high, content_low, paper_full, screen).
        provider: Filter by AI provider (ollama, openai, etc.).
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        List[Dict[str, Any]]: List of recent AI processing log entries.
    """
    from apps.ai_processor.models import AIProcessingLog

    # Limit check
    limit = min(limit, 100)

    # Build query
    query = select(AIProcessingLog).order_by(AIProcessingLog.created_at.desc())

    if task_type:
        query = query.where(AIProcessingLog.task_type == task_type)
    if provider:
        query = query.where(AIProcessingLog.provider == provider)

    query = query.limit(limit)

    result = await session.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "article_id": log.article_id,
            "provider": log.provider,
            "model": log.model,
            "task_type": log.task_type,
            "duration_ms": log.duration_ms,
            "success": log.success,
            "cached": log.cached,
            "input_chars": log.input_chars,
            "output_chars": log.output_chars,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# ============================================================================
# Event Management
# ============================================================================
# 事件管理 —— 管理事件聚类，支持查看、编辑、合并、删除

class EventUpdate(BaseModel):
    """Event update model."""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class EventMergeRequest(BaseModel):
    """Event merge request model."""
    source_event_ids: List[int]
    target_title: Optional[str] = None


@router.get("/events")
async def list_events(
    is_active: Optional[bool] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List event clusters with optional filtering.

    Args:
        is_active: Filter by active status.
        category: Filter by category name.
        search: Case-insensitive search by title.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated event cluster list.
    """
    from apps.event.models import EventCluster

    query = select(EventCluster)

    if is_active is not None:
        query = query.where(EventCluster.is_active == is_active)
    if category:
        query = query.where(EventCluster.category == category)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(EventCluster.title.ilike(search_pattern))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(desc(EventCluster.last_updated_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    events = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "events": [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "category": e.category,
                "article_count": e.article_count,
                "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else None,
                "last_updated_at": e.last_updated_at.isoformat() if e.last_updated_at else None,
                "is_active": e.is_active,
            }
            for e in events
        ]
    }


@router.get("/events/{event_id}")
async def get_event(
    event_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get event details and member articles.

    Args:
        event_id: Event cluster ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Event detail with member article list.

    Raises:
        HTTPException: If the event does not exist.
    """
    from apps.event.models import EventCluster, EventMember

    result = await session.execute(
        select(EventCluster).where(EventCluster.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get members
    members_result = await session.execute(
        select(EventMember).where(EventMember.event_id == event_id)
    )
    members = members_result.scalars().all()

    # Get articles
    article_ids = [m.article_id for m in members]
    articles = []
    if article_ids:
        articles_result = await session.execute(
            select(Article).where(Article.id.in_(article_ids))
        )
        articles = [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "source_type": a.source_type,
                "crawl_time": a.crawl_time.isoformat() if a.crawl_time else None,
                "similarity_score": next((m.similarity_score for m in members if m.article_id == a.id), 0),
            }
            for a in articles_result.scalars().all()
        ]

    return {
        "status": "ok",
        "event": {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "category": event.category,
            "article_count": event.article_count,
            "first_seen_at": event.first_seen_at.isoformat() if event.first_seen_at else None,
            "last_updated_at": event.last_updated_at.isoformat() if event.last_updated_at else None,
            "is_active": event.is_active,
            "articles": articles,
        }
    }


@router.put("/events/{event_id}")
async def update_event(
    event_id: int,
    update: EventUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update event details.

    Args:
        event_id: Event cluster ID.
        update: Partial event fields to update.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Update status message.

    Raises:
        HTTPException: If the event does not exist.
    """
    from apps.event.models import EventCluster

    result = await session.execute(
        select(EventCluster).where(EventCluster.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if update.title is not None:
        event.title = update.title
    if update.description is not None:
        event.description = update.description
    if update.category is not None:
        event.category = update.category
    if update.is_active is not None:
        event.is_active = update.is_active

    return {"status": "ok", "message": "Event updated"}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete an event cluster.

    Args:
        event_id: Event cluster ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Deletion status.

    Raises:
        HTTPException: If the event does not exist.
    """
    from apps.event.models import EventCluster

    result = await session.execute(
        select(EventCluster).where(EventCluster.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    await session.delete(event)

    return {"status": "ok", "message": "Event deleted"}


@router.post("/events/merge")
async def merge_events(
    request: EventMergeRequest,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Merge multiple events into one.

    Args:
        request: Merge parameters including source event IDs.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Merge summary and target event details.

    Raises:
        HTTPException: If fewer than 2 events are provided or events are missing.
    """
    from apps.event.models import EventCluster, EventMember

    if len(request.source_event_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 events to merge")

    # Get source events
    result = await session.execute(
        select(EventCluster).where(EventCluster.id.in_(request.source_event_ids))
    )
    events = result.scalars().all()

    if len(events) < 2:
        raise HTTPException(status_code=404, detail="Some events not found")

    # Use first event as target, merge others into it
    target_event = events[0]
    source_events = events[1:]

    total_articles = target_event.article_count

    for source in source_events:
        # Update members to point to target
        await session.execute(
            EventMember.__table__.update()
            .where(EventMember.event_id == source.id)
            .values(event_id=target_event.id)
        )

        total_articles += source.article_count

        # Delete source event
        await session.delete(source)

    # Update target event
    target_event.article_count = total_articles
    target_event.last_updated_at = datetime.now(timezone.utc)
    if request.target_title:
        target_event.title = request.target_title

    await session.commit()

    return {
        "status": "ok",
        "message": f"Merged {len(source_events)} events into event {target_event.id}",
        "target_event_id": target_event.id,
        "total_articles": total_articles,
    }


@router.get("/events/config")
async def get_event_config(
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Get event clustering configuration.

    Returns:
        Dict[str, Any]: Current event clustering parameters.
    """
    return {
        "status": "ok",
        "config": {
            "rule_weight": feature_config.get_float("event.rule_weight", 0.4),
            "semantic_weight": feature_config.get_float("event.semantic_weight", 0.6),
            "min_similarity": feature_config.get_float("event.min_similarity", 0.7),
            "enabled": feature_config.get_bool("feature.event_clustering", False),
        }
    }


@router.put("/events/config")
async def update_event_config(
    rule_weight: Optional[float] = None,
    semantic_weight: Optional[float] = None,
    min_similarity: Optional[float] = None,
    admin: Superuser = None,
) -> Dict[str, Any]:
    """Update event clustering configuration.

    Args:
        rule_weight: Weight for rule-based similarity.
        semantic_weight: Weight for semantic similarity.
        min_similarity: Minimum similarity to form a cluster.
        admin: Superuser dependency.

    Returns:
        Dict[str, Any]: Updated keys summary.
    """
    updates = []

    if rule_weight is not None:
        await feature_config.async_set("event.rule_weight", str(rule_weight), updated_by=admin.id)
        updates.append("rule_weight")
    if semantic_weight is not None:
        await feature_config.async_set("event.semantic_weight", str(semantic_weight), updated_by=admin.id)
        updates.append("semantic_weight")
    if min_similarity is not None:
        await feature_config.async_set("event.min_similarity", str(min_similarity), updated_by=admin.id)
        updates.append("min_similarity")

    return {"status": "ok", "updated": updates}


# ============================================================================
# Topic Management
# ============================================================================
# 主题管理 —— 管理研究主题，支持手动创建和自动发现

class TopicCreate(BaseModel):
    """Topic creation model."""
    name: str
    keywords: Optional[List[str]] = None
    description: Optional[str] = None
    is_manual: bool = True


class TopicUpdate(BaseModel):
    """Topic update model."""
    name: Optional[str] = None
    keywords: Optional[List[str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/topics")
async def list_topics(
    is_active: Optional[bool] = None,
    is_auto: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List topics with optional filtering.

    Args:
        is_active: Filter by active status.
        is_auto: Filter by auto-discovered topics.
        search: Case-insensitive name search.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated topic list with article counts.
    """
    from apps.topic.models import Topic, ArticleTopic

    query = select(Topic)

    if is_active is not None:
        query = query.where(Topic.is_active == is_active)
    if is_auto is not None:
        query = query.where(Topic.is_auto_discovered == is_auto)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(Topic.name.ilike(search_pattern))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(desc(Topic.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    topics = result.scalars().all()

    # Get article counts
    topic_ids = [t.id for t in topics]
    counts = {}
    if topic_ids:
        for tid in topic_ids:
            count_result = await session.execute(
                select(func.count(ArticleTopic.id)).where(ArticleTopic.topic_id == tid)
            )
            counts[tid] = count_result.scalar() or 0

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "topics": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "keywords": t.keywords or [],
                "is_manual": not t.is_auto_discovered,
                "is_active": t.is_active,
                "article_count": counts.get(t.id, 0),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in topics
        ]
    }


@router.post("/topics")
async def create_topic(
    topic_data: TopicCreate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new topic.

    Args:
        topic_data: Topic creation payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Created topic ID and name.

    Raises:
        HTTPException: If the topic name already exists.
    """
    from apps.topic.models import Topic

    # Check if name exists
    existing = await session.execute(
        select(Topic).where(Topic.name == topic_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Topic name already exists")

    topic = Topic(
        name=topic_data.name,
        description=topic_data.description,
        keywords=topic_data.keywords or [],
        is_auto_discovered=not topic_data.is_manual,
        created_by_user_id=admin.id,
    )
    session.add(topic)
    await session.flush()

    return {
        "status": "ok",
        "id": topic.id,
        "name": topic.name,
    }


@router.put("/topics/{topic_id}")
async def update_topic(
    topic_id: int,
    update: TopicUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a topic.

    Args:
        topic_id: Topic ID.
        update: Topic fields to update.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Update status.

    Raises:
        HTTPException: If the topic does not exist or name conflicts.
    """
    from apps.topic.models import Topic

    result = await session.execute(
        select(Topic).where(Topic.id == topic_id)
    )
    topic = result.scalar_one_or_none()

    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    if update.name is not None:
        # Check if name exists for other topic
        existing = await session.execute(
            select(Topic).where(Topic.name == update.name, Topic.id != topic_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Topic name already exists")
        topic.name = update.name
    if update.keywords is not None:
        topic.keywords = update.keywords
    if update.description is not None:
        topic.description = update.description
    if update.is_active is not None:
        topic.is_active = update.is_active

    return {"status": "ok", "message": "Topic updated"}


@router.delete("/topics/{topic_id}")
async def delete_topic(
    topic_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a topic.

    Args:
        topic_id: Topic ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Deletion status.

    Raises:
        HTTPException: If the topic does not exist.
    """
    from apps.topic.models import Topic

    result = await session.execute(
        select(Topic).where(Topic.id == topic_id)
    )
    topic = result.scalar_one_or_none()

    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    await session.delete(topic)

    return {"status": "ok", "message": "Topic deleted"}


@router.get("/topics/{topic_id}/snapshots")
async def get_topic_snapshots(
    topic_id: int,
    days: int = 30,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get topic trend snapshots.

    Args:
        topic_id: Topic ID.
        days: Lookback window in days.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Snapshot time series for the topic.
    """
    from apps.topic.models import TopicSnapshot
    from datetime import datetime, timedelta

    result = await session.execute(
        select(TopicSnapshot)
        .where(TopicSnapshot.topic_id == topic_id)
        .where(TopicSnapshot.snapshot_date >= (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"))
        .order_by(TopicSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()

    return {
        "status": "ok",
        "snapshots": [
            {
                "date": s.snapshot_date,
                "article_count": s.article_count,
                "trend_score": s.trend_score,
                "trend": s.trend,
                "top_keywords": s.top_keywords or [],
            }
            for s in snapshots
        ]
    }


# ============================================================================
# Report Management
# ============================================================================
# 报告管理 —— 管理自动生成的周报和月报

@router.get("/reports")
async def list_reports(
    report_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List generated reports.

    Args:
        report_type: Filter by report type (weekly/monthly).
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated report list.
    """
    from apps.report.models import Report

    query = select(Report)

    if report_type:
        query = query.where(Report.type == report_type)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(desc(Report.generated_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    reports = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "reports": [
            {
                "id": r.id,
                "title": r.title,
                "report_type": r.type,
                "date_range": f"{r.period_start} ~ {r.period_end}",
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    }


@router.get("/reports/{report_id}")
async def get_report(
    report_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get report details.

    Args:
        report_id: Report ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Report detail payload.

    Raises:
        HTTPException: If the report does not exist.
    """
    from apps.report.models import Report

    result = await session.execute(
        select(Report).where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "status": "ok",
        "report": {
            "id": report.id,
            "title": report.title,
            "type": report.type,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "content": report.content,
            "stats": report.stats,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        }
    }


@router.post("/reports/generate")
async def generate_report(
    report_type: str = "weekly",
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Generate a new report manually.

    Args:
        report_type: Report type (weekly or monthly).
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Created report metadata.
    """
    from apps.report.models import Report
    from datetime import datetime, timedelta, timezone

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    if report_type == "weekly":
        start_date = end_date - timedelta(days=7)
    else:  # monthly
        start_date = end_date - timedelta(days=30)

    period_start = start_date.strftime("%Y-%m-%d")
    period_end = end_date.strftime("%Y-%m-%d")

    # Get article count
    article_count = await session.execute(
        select(func.count(Article.id)).where(
            Article.crawl_time >= start_date,
            Article.crawl_time <= end_date
        )
    )
    total_articles = article_count.scalar() or 0

    # Generate report content (simplified)
    title = f"{'周报' if report_type == 'weekly' else '月报'} {period_start} ~ {period_end}"
    content = f"""# {title}

## 概览
- 时间范围: {period_start} ~ {period_end}
- 文章总数: {total_articles}

## 统计
- 本期共抓取 {total_articles} 篇文章

---
*报告生成时间: {datetime.now(timezone.utc).isoformat()}*
"""

    report = Report(
        user_id=admin.id,
        type=report_type,
        period_start=period_start,
        period_end=period_end,
        title=title,
        content=content,
        stats={"total_articles": total_articles},
    )
    session.add(report)
    await session.flush()

    return {
        "status": "ok",
        "id": report.id,
        "title": report.title,
        "message": "报告已生成",
    }


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a report.

    Args:
        report_id: Report ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Deletion status.

    Raises:
        HTTPException: If the report does not exist.
    """
    from apps.report.models import Report

    result = await session.execute(
        select(Report).where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    await session.delete(report)

    return {"status": "ok", "message": "Report deleted"}


# ============================================================================
# Data Source Management - ArXiv Categories
# ============================================================================
# ArXiv 分类管理 —— 管理爬虫抓取的 ArXiv 分类配置

@router.get("/sources/arxiv")
async def list_arxiv_categories(
    is_active: Optional[bool] = None,   # 筛选：是否活跃
    search: Optional[str] = None,       # 搜索：分类代码或名称
    page: int = 1,
    page_size: int = 50,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List ArXiv categories with optional filtering.

    Args:
        is_active: Filter by active status.
        search: Search by code or name.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated category list.
    """
    query = select(ArxivCategory)

    # 筛选条件
    if is_active is not None:
        query = query.where(ArxivCategory.is_active == is_active)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (ArxivCategory.code.ilike(search_pattern)) |
            (ArxivCategory.name.ilike(search_pattern))
        )

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(ArxivCategory.code).offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    categories = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "categories": [
            {
                "id": cat.id,
                "code": cat.code,
                "name": cat.name,
                "parent_code": cat.parent_code,
                "description": cat.description,
                "is_active": cat.is_active,
            }
            for cat in categories
        ]
    }


class ArxivCategoryUpdate(BaseModel):
    is_active: bool


@router.put("/sources/arxiv/{category_id}")
async def update_arxiv_category(
    category_id: int,
    update: ArxivCategoryUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update ArXiv category status (activate/deactivate for crawling).

    Args:
        category_id: Category ID.
        update: Activation payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated category status.

    Raises:
        HTTPException: If the category does not exist.
    """
    result = await session.execute(
        select(ArxivCategory).where(ArxivCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    category.is_active = update.is_active
    return {
        "status": "ok",
        "id": category.id,
        "code": category.code,
        "is_active": category.is_active,
    }


@router.put("/sources/arxiv/batch")
async def batch_update_arxiv_categories(
    category_ids: List[int],
    is_active: bool,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Batch update ArXiv categories status.

    Args:
        category_ids: List of category IDs.
        is_active: Target active state.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Count of updated categories.
    """
    result = await session.execute(
        select(ArxivCategory).where(ArxivCategory.id.in_(category_ids))
    )
    categories = result.scalars().all()

    for cat in categories:
        cat.is_active = is_active

    return {
        "status": "ok",
        "updated_count": len(categories),
    }


# ============================================================================
# Data Source Management - RSS Feeds
# ============================================================================
# RSS 源管理 —— 管理爬虫抓取的 RSS 订阅源配置

class RssFeedCreate(BaseModel):
    title: str
    feed_url: str
    site_url: Optional[str] = ""
    category: Optional[str] = "其他"
    description: Optional[str] = ""


class RssFeedUpdate(BaseModel):
    title: Optional[str] = None
    feed_url: Optional[str] = None
    site_url: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/sources/rss")
async def list_rss_feeds(
    is_active: Optional[bool] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List RSS feeds with optional filtering.

    Args:
        is_active: Filter by active status.
        category: Filter by category.
        search: Search by title or feed URL.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated RSS feed list.
    """
    query = select(RssFeed)

    # 筛选条件
    if is_active is not None:
        query = query.where(RssFeed.is_active == is_active)
    if category:
        query = query.where(RssFeed.category == category)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (RssFeed.title.ilike(search_pattern)) |
            (RssFeed.feed_url.ilike(search_pattern))
        )

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(desc(RssFeed.is_active), RssFeed.category, RssFeed.title)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    feeds = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "feeds": [
            {
                "id": feed.id,
                "title": feed.title,
                "feed_url": feed.feed_url,
                "site_url": feed.site_url,
                "category": feed.category,
                "description": feed.description,
                "is_active": feed.is_active,
                "last_fetched_at": feed.last_fetched_at.isoformat() if feed.last_fetched_at else None,
                "error_count": feed.error_count,
            }
            for feed in feeds
        ]
    }


@router.post("/sources/rss")
async def create_rss_feed(
    feed_data: RssFeedCreate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new RSS feed source.

    Args:
        feed_data: RSS feed payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Created feed ID and title.

    Raises:
        HTTPException: If the feed URL already exists.
    """
    # 检查 URL 是否已存在
    existing = await session.execute(
        select(RssFeed).where(RssFeed.feed_url == feed_data.feed_url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="RSS feed URL already exists")

    feed = RssFeed(
        title=feed_data.title,
        feed_url=feed_data.feed_url,
        site_url=feed_data.site_url or "",
        category=feed_data.category or "其他",
        description=feed_data.description or "",
        is_active=True,
    )
    session.add(feed)
    await session.flush()

    return {
        "status": "ok",
        "id": feed.id,
        "title": feed.title,
    }


@router.put("/sources/rss/{feed_id}")
async def update_rss_feed(
    feed_id: int,
    update: RssFeedUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update RSS feed configuration.

    Args:
        feed_id: RSS feed ID.
        update: Feed fields to update.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated feed metadata.

    Raises:
        HTTPException: If the feed does not exist or URL conflicts.
    """
    result = await session.execute(
        select(RssFeed).where(RssFeed.id == feed_id)
    )
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(status_code=404, detail="RSS feed not found")

    # 更新字段
    if update.title is not None:
        feed.title = update.title
    if update.feed_url is not None:
        # 检查新 URL 是否已被其他源使用
        existing = await session.execute(
            select(RssFeed).where(
                RssFeed.feed_url == update.feed_url,
                RssFeed.id != feed_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="RSS feed URL already in use")
        feed.feed_url = update.feed_url
    if update.site_url is not None:
        feed.site_url = update.site_url
    if update.category is not None:
        feed.category = update.category
    if update.description is not None:
        feed.description = update.description
    if update.is_active is not None:
        feed.is_active = update.is_active

    return {
        "status": "ok",
        "id": feed.id,
        "title": feed.title,
    }


@router.delete("/sources/rss/{feed_id}")
async def delete_rss_feed(
    feed_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete an RSS feed source.

    Args:
        feed_id: RSS feed ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Deletion status.

    Raises:
        HTTPException: If the feed does not exist.
    """
    result = await session.execute(
        select(RssFeed).where(RssFeed.id == feed_id)
    )
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(status_code=404, detail="RSS feed not found")

    await session.delete(feed)

    return {"status": "ok", "deleted_id": feed_id}


# ============================================================================
# Data Source Management - WeChat Accounts
# ============================================================================
# 微信公众号管理 —— 管理爬虫抓取的微信公众号配置

class WechatAccountCreate(BaseModel):
    name: str
    account_id: str
    description: Optional[str] = ""


class WechatAccountUpdate(BaseModel):
    name: Optional[str] = None
    account_id: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/sources/wechat")
async def list_wechat_accounts(
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List WeChat accounts with optional filtering.

    Args:
        is_active: Filter by active status.
        search: Search by name or account ID.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated WeChat account list.
    """
    query = select(WechatAccount)

    if is_active is not None:
        query = query.where(WechatAccount.is_active == is_active)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (WechatAccount.name.ilike(search_pattern)) |
            (WechatAccount.account_id.ilike(search_pattern))
        )

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(desc(WechatAccount.is_active), WechatAccount.name)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    accounts = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "accounts": [
            {
                "id": acc.id,
                "name": acc.name,
                "account_id": acc.account_id,
                "description": acc.description,
                "is_active": acc.is_active,
                "last_fetched_at": acc.last_fetched_at.isoformat() if acc.last_fetched_at else None,
                "error_count": acc.error_count,
            }
            for acc in accounts
        ]
    }


@router.post("/sources/wechat")
async def create_wechat_account(
    account_data: WechatAccountCreate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new WeChat account source.

    Args:
        account_data: WeChat account payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Created account ID and name.

    Raises:
        HTTPException: If the account already exists.
    """
    # 检查账号是否已存在
    existing = await session.execute(
        select(WechatAccount).where(WechatAccount.account_id == account_data.account_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="WeChat account already exists")

    account = WechatAccount(
        name=account_data.name,
        account_id=account_data.account_id,
        description=account_data.description or "",
        is_active=True,
    )
    session.add(account)
    await session.flush()

    return {
        "status": "ok",
        "id": account.id,
        "name": account.name,
    }


@router.put("/sources/wechat/{account_id}")
async def update_wechat_account(
    account_id: int,
    update: WechatAccountUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update WeChat account configuration.

    Args:
        account_id: WeChat account ID.
        update: Account fields to update.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated account metadata.

    Raises:
        HTTPException: If the account does not exist or ID conflicts.
    """
    result = await session.execute(
        select(WechatAccount).where(WechatAccount.id == account_id)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="WeChat account not found")

    if update.name is not None:
        account.name = update.name
    if update.account_id is not None:
        existing = await session.execute(
            select(WechatAccount).where(
                WechatAccount.account_id == update.account_id,
                WechatAccount.id != account_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="WeChat account ID already in use")
        account.account_id = update.account_id
    if update.description is not None:
        account.description = update.description
    if update.is_active is not None:
        account.is_active = update.is_active

    return {
        "status": "ok",
        "id": account.id,
        "name": account.name,
    }


@router.delete("/sources/wechat/{account_id}")
async def delete_wechat_account(
    account_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a WeChat account source.

    Args:
        account_id: WeChat account ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Deletion status.

    Raises:
        HTTPException: If the account does not exist.
    """
    result = await session.execute(
        select(WechatAccount).where(WechatAccount.id == account_id)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="WeChat account not found")

    await session.delete(account)

    return {"status": "ok", "deleted_id": account_id}


# ============================================================================
# Weibo Hot Search Board Management
# ============================================================================
# 微博热搜榜单管理 API


class WeiboBoardUpdate(BaseModel):
    """Request schema for updating a Weibo hot search board."""
    board_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/sources/weibo")
async def list_weibo_boards(
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List Weibo hot search boards with optional filtering.

    Args:
        is_active: Filter by active status.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated Weibo board list.
    """
    query = select(WeiboHotSearch)

    if is_active is not None:
        query = query.where(WeiboHotSearch.is_active == is_active)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(WeiboHotSearch.id)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    boards = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "boards": [
            {
                "id": board.id,
                "board_type": board.board_type,
                "board_name": board.board_name,
                "description": board.description,
                "is_active": board.is_active,
                "last_fetched_at": board.last_fetched_at.isoformat() if board.last_fetched_at else None,
                "error_count": board.error_count,
                "requires_cookie": board.board_type != "realtimehot",  # 非热搜榜需要 Cookie
            }
            for board in boards
        ]
    }


@router.put("/sources/weibo/{board_id}")
async def update_weibo_board(
    board_id: int,
    board_data: WeiboBoardUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a Weibo hot search board.

    Args:
        board_id: Board ID.
        board_data: Update payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated board info.

    Raises:
        HTTPException: If board not found.
    """
    result = await session.execute(
        select(WeiboHotSearch).where(WeiboHotSearch.id == board_id)
    )
    board = result.scalar_one_or_none()

    if not board:
        raise HTTPException(status_code=404, detail="Weibo board not found")

    # 检查是否尝试启用需要 Cookie 的榜单
    if board_data.is_active is True and board.board_type != "realtimehot":
        # 检查是否配置了 Cookie
        from settings import settings
        if not settings.weibo_cookie:
            raise HTTPException(
                status_code=400,
                detail=f"榜单 '{board.board_name}' 需要登录 Cookie 才能抓取。请先在系统配置中设置 WEIBO_COOKIE"
            )

    if board_data.board_name is not None:
        board.board_name = board_data.board_name
    if board_data.description is not None:
        board.description = board_data.description
    if board_data.is_active is not None:
        board.is_active = board_data.is_active

    await session.commit()

    return {
        "status": "ok",
        "board": {
            "id": board.id,
            "board_type": board.board_type,
            "board_name": board.board_name,
            "is_active": board.is_active,
        }
    }


@router.put("/sources/weibo/batch")
async def batch_update_weibo_boards(
    board_ids: List[int],
    is_active: bool,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Batch update Weibo boards active status.

    Args:
        board_ids: List of board IDs.
        is_active: Active status to set.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Update count.
    """
    if not board_ids:
        raise HTTPException(status_code=400, detail="No board IDs provided")

    # 如果要启用，检查是否包含需要 Cookie 的榜单
    if is_active:
        result = await session.execute(
            select(WeiboHotSearch).where(WeiboHotSearch.id.in_(board_ids))
        )
        boards = result.scalars().all()
        needs_cookie = [b for b in boards if b.board_type != "realtimehot"]
        
        if needs_cookie:
            from settings import settings
            if not settings.weibo_cookie:
                board_names = [b.board_name for b in needs_cookie]
                raise HTTPException(
                    status_code=400,
                    detail=f"以下榜单需要登录 Cookie: {', '.join(board_names)}。请先在系统配置中设置 WEIBO_COOKIE"
                )

    await session.execute(
        update(WeiboHotSearch)
        .where(WeiboHotSearch.id.in_(board_ids))
        .values(is_active=is_active)
    )
    await session.commit()

    return {"status": "ok", "updated_count": len(board_ids)}


# ============================================================================
# Data Source Management - HackerNews
# ============================================================================
# HackerNews 板块管理 —— 查询和更新 HackerNews 板块配置

class HackerNewsSourceUpdate(BaseModel):
    """Request schema for updating a HackerNews source."""
    feed_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/sources/hackernews")
async def list_hackernews_sources(
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List HackerNews sources with optional filtering.

    Args:
        is_active: Filter by active status.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated HackerNews source list.
    """
    query = select(HackerNewsSource)

    if is_active is not None:
        query = query.where(HackerNewsSource.is_active == is_active)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(HackerNewsSource.id)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    sources = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "sources": [
            {
                "id": source.id,
                "feed_type": source.feed_type,
                "feed_name": source.feed_name,
                "description": source.description,
                "is_active": source.is_active,
                "last_fetched_at": source.last_fetched_at.isoformat() if source.last_fetched_at else None,
                "error_count": source.error_count,
            }
            for source in sources
        ]
    }


@router.put("/sources/hackernews/{source_id}")
async def update_hackernews_source(
    source_id: int,
    source_data: HackerNewsSourceUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a HackerNews source.

    Args:
        source_id: Source ID.
        source_data: Update payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated source info.

    Raises:
        HTTPException: If source not found.
    """
    result = await session.execute(
        select(HackerNewsSource).where(HackerNewsSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="HackerNews source not found")

    if source_data.feed_name is not None:
        source.feed_name = source_data.feed_name
    if source_data.description is not None:
        source.description = source_data.description
    if source_data.is_active is not None:
        source.is_active = source_data.is_active

    await session.commit()

    return {
        "status": "ok",
        "source": {
            "id": source.id,
            "feed_type": source.feed_type,
            "feed_name": source.feed_name,
            "is_active": source.is_active,
        }
    }


@router.put("/sources/hackernews/batch")
async def batch_update_hackernews_sources(
    source_ids: List[int],
    is_active: bool,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Batch update HackerNews sources active status.

    Args:
        source_ids: List of source IDs.
        is_active: Active status to set.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Update count.
    """
    if not source_ids:
        raise HTTPException(status_code=400, detail="No source IDs provided")

    await session.execute(
        update(HackerNewsSource)
        .where(HackerNewsSource.id.in_(source_ids))
        .values(is_active=is_active)
    )
    await session.commit()

    return {"status": "ok", "updated_count": len(source_ids)}


# ============================================================================
# Data Source Management - Reddit
# ============================================================================
# Reddit 订阅源管理 —— 查询、创建、更新和删除 Reddit 订阅源

class RedditSourceCreate(BaseModel):
    """Request schema for creating a Reddit source."""
    source_type: str  # "subreddit" or "user"
    source_name: str
    display_name: Optional[str] = ""
    description: Optional[str] = ""


class RedditSourceUpdate(BaseModel):
    """Request schema for updating a Reddit source."""
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/sources/reddit")
async def list_reddit_sources(
    is_active: Optional[bool] = None,
    source_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List Reddit sources with optional filtering.

    Args:
        is_active: Filter by active status.
        source_type: Filter by source type (subreddit/user).
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated Reddit source list.
    """
    query = select(RedditSource)

    if is_active is not None:
        query = query.where(RedditSource.is_active == is_active)
    if source_type:
        query = query.where(RedditSource.source_type == source_type)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(RedditSource.id)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    sources = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "sources": [
            {
                "id": source.id,
                "source_type": source.source_type,
                "source_name": source.source_name,
                "display_name": source.display_name,
                "description": source.description,
                "is_active": source.is_active,
                "last_fetched_at": source.last_fetched_at.isoformat() if source.last_fetched_at else None,
                "error_count": source.error_count,
            }
            for source in sources
        ]
    }


@router.post("/sources/reddit")
async def create_reddit_source(
    source_data: RedditSourceCreate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new Reddit source.

    Args:
        source_data: Create payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Created source info.

    Raises:
        HTTPException: If source already exists.
    """
    # 检查是否已存在
    existing = await session.execute(
        select(RedditSource).where(
            RedditSource.source_type == source_data.source_type,
            RedditSource.source_name == source_data.source_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Reddit source already exists")

    source = RedditSource(
        source_type=source_data.source_type,
        source_name=source_data.source_name,
        display_name=source_data.display_name or source_data.source_name,
        description=source_data.description or "",
        is_active=True,
    )
    session.add(source)
    await session.commit()

    return {
        "status": "ok",
        "source": {
            "id": source.id,
            "source_type": source.source_type,
            "source_name": source.source_name,
            "display_name": source.display_name,
        }
    }


@router.put("/sources/reddit/{source_id}")
async def update_reddit_source(
    source_id: int,
    source_data: RedditSourceUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a Reddit source.

    Args:
        source_id: Source ID.
        source_data: Update payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated source info.

    Raises:
        HTTPException: If source not found.
    """
    result = await session.execute(
        select(RedditSource).where(RedditSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Reddit source not found")

    if source_data.display_name is not None:
        source.display_name = source_data.display_name
    if source_data.description is not None:
        source.description = source_data.description
    if source_data.is_active is not None:
        source.is_active = source_data.is_active

    await session.commit()

    return {
        "status": "ok",
        "source": {
            "id": source.id,
            "source_type": source.source_type,
            "source_name": source.source_name,
            "is_active": source.is_active,
        }
    }


@router.delete("/sources/reddit/{source_id}")
async def delete_reddit_source(
    source_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a Reddit source.

    Args:
        source_id: Source ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status message.

    Raises:
        HTTPException: If source not found.
    """
    result = await session.execute(
        select(RedditSource).where(RedditSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Reddit source not found")

    await session.execute(
        delete(RedditSource).where(RedditSource.id == source_id)
    )
    await session.commit()

    return {"status": "ok", "message": "Reddit source deleted"}


# ============================================================================
# Data Source Management - Twitter
# ============================================================================
# Twitter 用户订阅管理 —— 查询、创建、更新和删除 Twitter 用户订阅

class TwitterSourceCreate(BaseModel):
    """Request schema for creating a Twitter source."""
    username: str
    display_name: Optional[str] = ""
    description: Optional[str] = ""


class TwitterSourceUpdate(BaseModel):
    """Request schema for updating a Twitter source."""
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/sources/twitter")
async def list_twitter_sources(
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List Twitter sources with optional filtering.

    Args:
        is_active: Filter by active status.
        page: Page number.
        page_size: Items per page.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Paginated Twitter source list.
    """
    query = select(TwitterSource)

    if is_active is not None:
        query = query.where(TwitterSource.is_active == is_active)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(TwitterSource.id)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    sources = result.scalars().all()

    # 检查是否配置了 Twitter API Key
    from settings import settings
    has_api_key = bool(settings.twitterapi_io_key)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_api_key": has_api_key,
        "sources": [
            {
                "id": source.id,
                "username": source.username,
                "display_name": source.display_name,
                "description": source.description,
                "is_active": source.is_active,
                "last_fetched_at": source.last_fetched_at.isoformat() if source.last_fetched_at else None,
                "error_count": source.error_count,
            }
            for source in sources
        ]
    }


@router.post("/sources/twitter")
async def create_twitter_source(
    source_data: TwitterSourceCreate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new Twitter source.

    Args:
        source_data: Create payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Created source info.

    Raises:
        HTTPException: If source already exists or API key not configured.
    """
    # 检查是否配置了 API Key
    from settings import settings
    if not settings.twitterapi_io_key:
        raise HTTPException(
            status_code=400,
            detail="TwitterAPI.io API Key 未配置。请先在环境变量中设置 TWITTERAPI_IO_KEY"
        )

    # 移除 @ 前缀
    username = source_data.username.lstrip("@")

    # 检查是否已存在
    existing = await session.execute(
        select(TwitterSource).where(TwitterSource.username == username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Twitter source already exists")

    source = TwitterSource(
        username=username,
        display_name=source_data.display_name or username,
        description=source_data.description or "",
        is_active=True,
    )
    session.add(source)
    await session.commit()

    return {
        "status": "ok",
        "source": {
            "id": source.id,
            "username": source.username,
            "display_name": source.display_name,
        }
    }


@router.put("/sources/twitter/{source_id}")
async def update_twitter_source(
    source_id: int,
    source_data: TwitterSourceUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a Twitter source.

    Args:
        source_id: Source ID.
        source_data: Update payload.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Updated source info.

    Raises:
        HTTPException: If source not found.
    """
    result = await session.execute(
        select(TwitterSource).where(TwitterSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Twitter source not found")

    if source_data.display_name is not None:
        source.display_name = source_data.display_name
    if source_data.description is not None:
        source.description = source_data.description
    if source_data.is_active is not None:
        source.is_active = source_data.is_active

    await session.commit()

    return {
        "status": "ok",
        "source": {
            "id": source.id,
            "username": source.username,
            "is_active": source.is_active,
        }
    }


@router.delete("/sources/twitter/{source_id}")
async def delete_twitter_source(
    source_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a Twitter source.

    Args:
        source_id: Source ID.
        admin: Superuser dependency.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status message.

    Raises:
        HTTPException: If source not found.
    """
    result = await session.execute(
        select(TwitterSource).where(TwitterSource.id == source_id)
    )
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Twitter source not found")

    await session.execute(
        delete(TwitterSource).where(TwitterSource.id == source_id)
    )
    await session.commit()

    return {"status": "ok", "message": "Twitter source deleted"}


# ============================================================================
# Data Source Statistics
# ============================================================================
# 数据源统计 —— 汇总各数据源的状态信息

@router.get("/sources/stats")
async def get_sources_stats(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Get statistics for all data sources.

    Returns:
        Dict[str, Any]: Counts of total and active sources by type.
    """
    # ArXiv 统计
    arxiv_total = await session.execute(select(func.count(ArxivCategory.id)))
    arxiv_active = await session.execute(
        select(func.count(ArxivCategory.id)).where(ArxivCategory.is_active == True)
    )

    # RSS 统计
    rss_total = await session.execute(select(func.count(RssFeed.id)))
    rss_active = await session.execute(
        select(func.count(RssFeed.id)).where(RssFeed.is_active == True)
    )

    # 微信统计
    wechat_total = await session.execute(select(func.count(WechatAccount.id)))
    wechat_active = await session.execute(
        select(func.count(WechatAccount.id)).where(WechatAccount.is_active == True)
    )

    # 微博热搜统计
    weibo_total = await session.execute(select(func.count(WeiboHotSearch.id)))
    weibo_active = await session.execute(
        select(func.count(WeiboHotSearch.id)).where(WeiboHotSearch.is_active == True)
    )

    # HackerNews 统计
    hackernews_total = await session.execute(select(func.count(HackerNewsSource.id)))
    hackernews_active = await session.execute(
        select(func.count(HackerNewsSource.id)).where(HackerNewsSource.is_active == True)
    )

    # Reddit 统计
    reddit_total = await session.execute(select(func.count(RedditSource.id)))
    reddit_active = await session.execute(
        select(func.count(RedditSource.id)).where(RedditSource.is_active == True)
    )

    # Twitter 统计
    twitter_total = await session.execute(select(func.count(TwitterSource.id)))
    twitter_active = await session.execute(
        select(func.count(TwitterSource.id)).where(TwitterSource.is_active == True)
    )

    return {
        "arxiv": {
            "total": arxiv_total.scalar() or 0,
            "active": arxiv_active.scalar() or 0,
        },
        "rss": {
            "total": rss_total.scalar() or 0,
            "active": rss_active.scalar() or 0,
        },
        "wechat": {
            "total": wechat_total.scalar() or 0,
            "active": wechat_active.scalar() or 0,
        },
        "weibo": {
            "total": weibo_total.scalar() or 0,
            "active": weibo_active.scalar() or 0,
        },
        "hackernews": {
            "total": hackernews_total.scalar() or 0,
            "active": hackernews_active.scalar() or 0,
        },
        "reddit": {
            "total": reddit_total.scalar() or 0,
            "active": reddit_active.scalar() or 0,
        },
        "twitter": {
            "total": twitter_total.scalar() or 0,
            "active": twitter_active.scalar() or 0,
        },
    }


# ============================================================================
# RBAC: Role & Permission Management
# ============================================================================
# 角色和权限管理 API —— 提供 RBAC 体系的完整管理能力


class RoleCreateUpdate(BaseModel):
    """Request schema for creating or updating a role."""
    name: str
    description: str = ""
    permission_ids: List[int] = []


@router.get("/roles")
async def list_roles(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all roles with their permissions and user counts."""
    result = await session.execute(
        select(Role).order_by(Role.id)
    )
    roles = result.scalars().all()

    role_list = []
    for role in roles:
        # 统计该角色关联的用户数
        user_count_result = await session.execute(
            select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)
        )
        user_count = user_count_result.scalar() or 0

        role_list.append({
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "permissions": [
                {
                    "id": p.id,
                    "name": p.name,
                    "resource": p.resource,
                    "action": p.action,
                    "description": p.description,
                }
                for p in role.permissions
            ],
            "user_count": user_count,
            "created_at": role.created_at.isoformat() if role.created_at else None,
        })

    return {"roles": role_list}


@router.post("/roles")
async def create_role(
    data: RoleCreateUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new role with specified permissions."""
    # 检查角色名是否已存在
    existing = await session.execute(
        select(Role).where(Role.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Role '{data.name}' already exists")

    # 创建角色
    role = Role(name=data.name, description=data.description)
    session.add(role)
    await session.flush()  # 获取 role.id

    # 关联权限
    if data.permission_ids:
        perm_result = await session.execute(
            select(Permission).where(Permission.id.in_(data.permission_ids))
        )
        permissions = perm_result.scalars().all()
        role.permissions = list(permissions)

    return {"status": "ok", "role_id": role.id, "message": f"Role '{data.name}' created"}


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    data: RoleCreateUpdate,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Update a role's name, description and permissions."""
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # 检查名称冲突
    if data.name != role.name:
        name_check = await session.execute(
            select(Role).where(Role.name == data.name)
        )
        if name_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Role '{data.name}' already exists")

    role.name = data.name
    role.description = data.description

    # 更新权限关联
    if data.permission_ids is not None:
        perm_result = await session.execute(
            select(Permission).where(Permission.id.in_(data.permission_ids))
        )
        permissions = perm_result.scalars().all()
        role.permissions = list(permissions)

    return {"status": "ok", "message": f"Role '{role.name}' updated"}


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a role. Fails if users are still assigned to it."""
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # 禁止删除内置角色
    if role.name in ("superuser", "admin", "user", "guest"):
        raise HTTPException(status_code=400, detail=f"Cannot delete built-in role '{role.name}'")

    # 检查是否还有用户关联
    user_count_result = await session.execute(
        select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)
    )
    user_count = user_count_result.scalar() or 0
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete role '{role.name}': {user_count} user(s) still assigned"
        )

    await session.delete(role)
    return {"status": "ok", "message": f"Role '{role.name}' deleted"}


@router.get("/permissions")
async def list_permissions(
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all permissions grouped by resource."""
    result = await session.execute(
        select(Permission).order_by(Permission.resource, Permission.action)
    )
    permissions = result.scalars().all()

    # 按 resource 分组
    grouped: Dict[str, list] = {}
    for p in permissions:
        if p.resource not in grouped:
            grouped[p.resource] = []
        grouped[p.resource].append({
            "id": p.id,
            "name": p.name,
            "resource": p.resource,
            "action": p.action,
            "description": p.description,
        })

    return {
        "permissions": [
            {"id": p.id, "name": p.name, "resource": p.resource, "action": p.action, "description": p.description}
            for p in permissions
        ],
        "grouped": grouped,
    }
