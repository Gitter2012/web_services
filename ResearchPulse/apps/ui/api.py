# ==========================================================================
# 前端 UI API 模块
# --------------------------------------------------------------------------
# 本模块是 ResearchPulse 系统的前端用户界面接口层，服务于 Web 前端页面和
# 面向用户的 REST API。包含以下功能区域：
#
#   1. 页面端点 (Page Endpoints)
#      - 首页（文章列表）、订阅管理页、管理后台页
#      - 使用 Jinja2 模板引擎渲染 HTML 页面
#
#   2. 文章 API (Article API)
#      - 文章列表（支持多维度筛选、排序、分页）
#      - 文章详情（包含用户个人阅读状态）
#      - 已读标记、收藏切换
#
#   3. 数据源 API (Source API)
#      - 按类型列出分类（ArXiv 分类、RSS 分类）
#      - 列出所有可用数据源
#      - 列出 RSS 订阅源
#
#   4. 订阅管理 API (Subscription API)
#      - 查看用户订阅列表
#      - 创建/取消订阅
#
#   5. RSS 源管理 API (RSS Feed Management)
#      - 用户添加自定义 RSS 源（需验证有效性）
#      - RSS 源候选列表
#
#   6. 导出 API (Export API)
#      - 按筛选条件导出文章为 Markdown 文件
#      - 导出用户订阅文章为 Markdown 文件
#
# 架构位置：
#   本模块位于 apps/ui/api.py，属于"用户界面应用"(ui app) 的路由层。
#   同时承担页面渲染（SSR）和 API 数据接口双重职责。
#   通过 FastAPI 的 APIRouter 注册到主应用，页面端点无前缀，
#   API 端点统一使用 /api/ 前缀。
# ==========================================================================

"""UI API endpoints for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl
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
    WechatAccount,
)

logger = logging.getLogger(__name__)

# 创建 UI 路由器，无 URL 前缀（页面端点挂载在根路径下）
router = APIRouter(tags=["ui"])

# Jinja2 模板引擎实例，在 main.py 启动时通过 init_templates 函数初始化
# 使用模块级变量延迟初始化，避免模块导入时就需要确定模板目录
_templates: Jinja2Templates | None = None


def init_templates(template_dir: str) -> None:
    """Initialize Jinja2 templates.

    初始化模板目录与 Jinja2 环境。

    Args:
        template_dir: Template directory path.
    """
    # 初始化 Jinja2 模板引擎，设置模板目录
    # 该函数在应用启动时由 main.py 调用
    global _templates
    from pathlib import Path
    _templates = Jinja2Templates(directory=Path(template_dir))


# ============================================================================
# Page Endpoints
# ============================================================================
# 页面端点 —— 使用 Jinja2 模板渲染 HTML 页面
# 这些端点返回 HTMLResponse，由浏览器直接渲染
# OptionalUserId 依赖项会尝试从请求中提取用户 ID，未登录时为 None

@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,                 # FastAPI Request 对象，Jinja2 模板渲染必需
    user_id: OptionalUserId = None,   # 可选的用户 ID，未登录时为 None
) -> HTMLResponse:
    """Main article list page.

    首页文章列表页面渲染入口。

    Args:
        request: FastAPI request object.
        user_id: Optional user ID.

    Returns:
        HTMLResponse: Rendered HTML page.
    """
    # 渲染首页模板，传入请求对象和用户 ID（用于前端判断登录状态）
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
    """Subscription management page.

    订阅管理页面渲染入口。

    Args:
        request: FastAPI request object.
        user_id: Optional user ID.

    Returns:
        HTMLResponse: Rendered HTML page.
    """
    # 渲染订阅管理页面
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
    """Admin page.

    管理后台页面渲染入口。

    Args:
        request: FastAPI request object.
        user_id: Optional user ID.

    Returns:
        HTMLResponse: Rendered HTML page.
    """
    # 渲染管理后台页面
    # 注意：前端页面需要自行检查用户权限（此处未做服务端权限校验）
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
# 文章相关 API —— 提供文章的列表查询、详情获取、已读/收藏状态管理

# 文章列表响应模型：包含文章数组、总数以及分页信息
class ArticleListResponse(BaseModel):
    """Response schema for article list queries.

    文章列表响应模型。

    Attributes:
        articles: List of article dictionaries.
        total: Total matched count.
        page: Current page number.
        page_size: Page size.
    """

    articles: List[Dict[str, Any]]  # 文章字典列表
    total: int                      # 符合筛选条件的文章总数
    page: int                       # 当前页码
    page_size: int                  # 每页条数


# 文章详情响应模型：包含单篇文章数据和可选的用户阅读状态
class ArticleDetailResponse(BaseModel):
    """Response schema for article detail.

    单篇文章详情响应模型。

    Attributes:
        article: Article detail dictionary.
        user_state: Optional user reading state.
    """

    article: Dict[str, Any]                      # 文章详细信息
    user_state: Optional[Dict[str, Any]] = None  # 用户阅读状态（已读/收藏等）


@router.get("/api/articles", response_model=ArticleListResponse)
async def list_articles(
    source_type: Optional[str] = None,    # 筛选条件：数据源类型（如 "arxiv"、"rss"、"wechat"）
    category: Optional[str] = None,       # 筛选条件：分类（支持分类代码和名称的模糊匹配）
    keyword: Optional[str] = None,        # 筛选条件：关键词（标题和摘要中搜索）
    from_date: Optional[str] = None,      # 筛选条件：起始日期（ISO 格式）
    starred: Optional[bool] = None,       # 筛选条件：仅显示收藏文章（需要登录）
    unread: Optional[bool] = None,        # 筛选条件：仅显示未读文章（需要登录）
    archived: Optional[bool] = None,      # 筛选条件：是否显示已归档文章
    sort: str = Query("publish_time", pattern="^(publish_time|crawl_time|title)$"),  # 排序字段
    page: int = Query(1, ge=1),           # 当前页码，最小为 1
    page_size: int = Query(20, ge=1, le=100),  # 每页条数，1-100
    user_id: OptionalUserId = None,       # 可选的用户 ID，用于个性化筛选
    session: AsyncSession = Depends(get_session),
) -> ArticleListResponse:
    """List articles with filtering and pagination.

    获取文章列表，支持多条件筛选与分页。

    Args:
        source_type: Source type filter.
        category: Category filter.
        keyword: Keyword search.
        from_date: Start date (ISO).
        starred: Filter starred articles (login required).
        unread: Filter unread articles (login required).
        archived: Whether to include archived articles.
        sort: Sort field.
        page: Page number.
        page_size: Items per page.
        user_id: Optional user ID for personalization.
        session: Async database session.

    Returns:
        ArticleListResponse: Paginated article list.
    """
    query = select(Article)

    # ---- 通用筛选条件 ----

    # 按数据源类型筛选
    if source_type:
        query = query.where(Article.source_type == source_type)

    # 按分类筛选：支持多种匹配方式
    if category:
        safe_category = category.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        if source_type == "rss":
            # RSS 文章的分类存储在 rss_feeds 表中，需要 JOIN 查询
            # RSS 文章的 source_id 对应 rss_feeds.id
            from apps.crawler.models.source import RssFeed

            # 创建子查询：找出指定分类的 RSS feed IDs
            rss_feed_subquery = select(RssFeed.id).where(
                RssFeed.category == category
            ).scalar_subquery()

            query = query.where(Article.source_id.in_(select(RssFeed.id).where(RssFeed.category == category)))
        else:
            # ArXiv 和其他来源：匹配 Article.category 或 arxiv_primary_category
            query = query.where(
                or_(
                    Article.category == category,
                    Article.category.like(f"%{safe_category}%"),
                    Article.arxiv_primary_category == category,
                )
            )

    # 按关键词搜索：在标题和摘要中进行不区分大小写的模糊匹配
    # 转义 LIKE 通配符 % 和 _，防止用户输入被解释为通配符
    if keyword:
        safe_keyword = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_keyword}%"
        query = query.where(
            or_(Article.title.ilike(pattern), Article.summary.ilike(pattern))
        )

    # 按发布日期筛选：只返回指定日期之后的文章
    if from_date:
        try:
            from datetime import datetime
            # 将 ISO 格式字符串转为 datetime 对象，兼容 "Z" 结尾的 UTC 时间格式
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            query = query.where(Article.publish_time >= from_dt)
        except ValueError:
            pass  # 日期格式无效时忽略该筛选条件，不抛出错误

    # 归档状态筛选
    if archived is not None:
        query = query.where(Article.is_archived == archived)
    else:
        # 默认行为：隐藏已归档的文章，只显示活跃内容
        query = query.where(Article.is_archived == False)

    # ---- 用户个性化筛选条件（需要登录） ----
    if user_id:
        # 收藏筛选：通过 JOIN 用户文章状态表，获取用户收藏的文章
        if starred is not None and starred:
            query = query.join(UserArticleState).where(
                UserArticleState.user_id == user_id,
                UserArticleState.is_starred == True,
            )
        # 未读筛选：使用 LEFT JOIN，没有状态记录或 is_read=False 的文章视为未读
        if unread is not None and unread:
            query = query.outerjoin(
                UserArticleState,
                (UserArticleState.article_id == Article.id) & (UserArticleState.user_id == user_id)
            ).where(
                or_(UserArticleState.is_read == False, UserArticleState.is_read == None)
            )

    # 统计符合筛选条件的文章总数（用于前端分页计算）
    # 使用子查询方式计数，确保筛选条件生效
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # ---- 排序和分页 ----
    if sort == "title":
        query = query.order_by(Article.title)            # 按标题字母顺序排序
    elif sort == "crawl_time":
        query = query.order_by(desc(Article.crawl_time)) # 按爬取时间倒序（最新爬取的在前）
    else:
        query = query.order_by(desc(Article.publish_time))  # 默认：按发布时间倒序

    # 分页处理：offset + limit
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    articles = result.scalars().all()

    # ---- 批量获取用户阅读状态 ----
    # 如果用户已登录，批量查询当前页所有文章的阅读/收藏状态
    # 使用 IN 查询避免 N+1 问题
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
            # 将查询结果转为 article_id -> state 的字典，方便后续查找
            for state in state_result.scalars().all():
                user_states[state.article_id] = state

    # ---- 构建响应数据 ----
    article_list = []
    for article in articles:
        article_dict = _article_to_dict(article)
        # 如果存在用户状态，将已读/收藏信息合并到文章数据中
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
    article_id: int,                # 路径参数：文章 ID
    user_id: OptionalUserId = None, # 可选的用户 ID，用于获取个人阅读状态
    session: AsyncSession = Depends(get_session),
) -> ArticleDetailResponse:
    """Get article details.

    获取文章详情及可选的用户阅读状态。

    Args:
        article_id: Article ID.
        user_id: Optional user ID.
        session: Async database session.

    Returns:
        ArticleDetailResponse: Article details and user state.
    """
    # 根据文章 ID 查询文章
    result = await session.execute(
        select(Article).where(Article.id == article_id)
    )
    article = result.scalar_one_or_none()

    # 文章不存在时返回空数据而非 404 错误
    # 设计决策：前端可以根据空 article 字典做更灵活的处理
    if not article:
        return ArticleDetailResponse(article={}, user_state=None)

    article_dict = _article_to_dict(article)

    # 如果用户已登录，获取该用户对此文章的阅读状态
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
    article_id: int,          # 路径参数：文章 ID
    user: CurrentUser,        # 依赖注入：当前已认证用户（必须登录）
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Mark article as read.

    标记文章为已读，并更新阅读时间戳。

    Args:
        article_id: Article ID.
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status payload with read state.
    """
    # 查询用户对该文章的现有状态记录
    result = await session.execute(
        select(UserArticleState).where(
            UserArticleState.user_id == user.id,
            UserArticleState.article_id == article_id,
        )
    )
    state = result.scalar_one_or_none()

    # 如果状态记录不存在，创建一个新的
    # 采用"按需创建"策略：只有在用户与文章产生交互时才创建状态记录
    if not state:
        state = UserArticleState(
            user_id=user.id,
            article_id=article_id,
        )
        session.add(state)

    # 调用模型方法标记为已读（会同时更新 read_at 时间戳）
    state.mark_read()
    await session.flush()

    return {"status": "ok", "is_read": True}


@router.post("/api/articles/{article_id}/star")
async def toggle_article_star(
    article_id: int,          # 路径参数：文章 ID
    user: CurrentUser,        # 依赖注入：当前已认证用户（必须登录）
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Toggle article star status.

    切换文章收藏状态。

    Args:
        article_id: Article ID.
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status payload with starred state.
    """
    # 查询用户对该文章的现有状态记录
    result = await session.execute(
        select(UserArticleState).where(
            UserArticleState.user_id == user.id,
            UserArticleState.article_id == article_id,
        )
    )
    state = result.scalar_one_or_none()

    # 如果状态记录不存在，创建一个新的
    if not state:
        state = UserArticleState(
            user_id=user.id,
            article_id=article_id,
        )
        session.add(state)

    # 切换收藏状态：如果已收藏则取消，未收藏则添加
    # toggle_star() 返回切换后的新状态值
    new_star_status = state.toggle_star()
    await session.flush()

    return {"status": "ok", "is_starred": new_star_status}


# ============================================================================
# Source API Endpoints
# ============================================================================
# 数据源相关 API —— 提供分类和数据源的列表查询，供前端筛选组件使用

@router.get("/api/categories")
async def list_categories(
    source_type: str = None,  # 数据源类型："arxiv"、"rss" 或 None（默认返回 ArXiv）
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List available categories by source type.

    根据数据源类型返回分类列表。

    Args:
        source_type: Source type (arxiv/rss).
        session: Async database session.

    Returns:
        Dict[str, Any]: Category list payload.
    """

    if source_type == "arxiv" or source_type is None:
        # 返回 ArXiv 分类列表，仅包含活跃的分类，按分类代码排序
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
                    "code": cat.code,         # 分类代码，如 "cs.AI"、"math.PR"
                    "name": cat.name,         # 分类名称
                    "description": cat.description,  # 分类描述
                }
                for cat in categories
            ]
        }
    elif source_type == "rss":
        # 返回 RSS 源的去重分类列表
        # 使用 DISTINCT 查询 RSS 订阅源的 category 字段
        result = await session.execute(
            select(RssFeed.category)
            .where(RssFeed.is_active == True)
            .distinct()
            .order_by(RssFeed.category)
        )
        # 过滤掉 None 值的分类
        categories = [row[0] for row in result.fetchall() if row[0]]

        # 为 RSS 分类生成与 ArXiv 分类统一的数据结构
        # 使用 enumerate 生成临时 ID，方便前端统一处理
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
        # 未知的数据源类型，返回空列表
        return {"type": "unknown", "categories": []}


@router.get("/api/sources")
async def list_all_sources(
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all available sources for filtering.

    返回所有可用的数据源信息。

    Args:
        session: Async database session.

    Returns:
        Dict[str, Any]: Source list payload.
    """
    # 查询所有活跃的 ArXiv 分类
    arxiv_result = await session.execute(
        select(ArxivCategory)
        .where(ArxivCategory.is_active == True)
        .order_by(ArxivCategory.code)
    )
    arxiv_cats = arxiv_result.scalars().all()

    # 查询所有活跃的 RSS 订阅源，按分类和标题排序
    rss_result = await session.execute(
        select(RssFeed)
        .where(RssFeed.is_active == True)
        .order_by(RssFeed.category, RssFeed.title)
    )
    rss_feeds = rss_result.scalars().all()

    # 返回统一的数据源结构，前端可据此构建筛选 UI
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
    """List available RSS feeds.

    返回可用的 RSS 订阅源列表。

    Args:
        session: Async database session.

    Returns:
        Dict[str, Any]: RSS feed list payload.
    """
    # 查询所有活跃的 RSS 订阅源
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
                "title": feed.title,         # 订阅源标题
                "category": feed.category,   # 所属分类
                "site_url": feed.site_url,   # 订阅源网站 URL
            }
            for feed in feeds
        ]
    }


@router.get("/api/sources/search")
async def search_sources(
    q: str = Query(..., min_length=1, description="Search keyword"),
    limit: int = Query(20, ge=1, le=100, description="Max results per source type"),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Search across all subscribable sources.

    模糊搜索所有可订阅的数据源（ArXiv 类目、RSS 源、微信公众号）。

    Args:
        q: Search keyword (fuzzy match).
        limit: Max results per source type.
        session: Async database session.

    Returns:
        Dict[str, Any]: Search results grouped by source type.
    """
    # 构建模糊搜索模式
    search_pattern = f"%{q}%"

    results = {
        "keyword": q,
        "arxiv": [],
        "rss": [],
        "wechat": [],
    }

    try:
        # 搜索 ArXiv 类目：匹配 code、name
        # 注意：description 可能为 null，使用 func.coalesce 处理
        from sqlalchemy import func

        arxiv_result = await session.execute(
            select(ArxivCategory)
            .where(
                or_(
                    ArxivCategory.code.ilike(search_pattern),
                    ArxivCategory.name.ilike(search_pattern),
                    func.coalesce(ArxivCategory.description, "").ilike(search_pattern),
                ),
            )
            .order_by(ArxivCategory.is_active.desc(), ArxivCategory.code)
            .limit(limit)
        )
        arxiv_cats = arxiv_result.scalars().all()
        results["arxiv"] = [
            {
                "id": cat.id,
                "type": "arxiv",
                "code": cat.code,
                "name": cat.name,
                "description": cat.description or "",
                "is_active": cat.is_active,
            }
            for cat in arxiv_cats
        ]
    except Exception as e:
        logger.error(f"ArXiv search error: {e}")

    try:
        # 搜索 RSS 源：匹配 title、category
        from sqlalchemy import func

        rss_result = await session.execute(
            select(RssFeed)
            .where(
                or_(
                    RssFeed.title.ilike(search_pattern),
                    func.coalesce(RssFeed.category, "").ilike(search_pattern),
                ),
            )
            .order_by(RssFeed.is_active.desc(), RssFeed.title)
            .limit(limit)
        )
        rss_feeds = rss_result.scalars().all()
        results["rss"] = [
            {
                "id": feed.id,
                "type": "rss",
                "code": str(feed.id),
                "name": feed.title,
                "description": feed.category or "",
                "site_url": feed.site_url or "",
                "is_active": feed.is_active,
            }
            for feed in rss_feeds
        ]
    except Exception as e:
        logger.error(f"RSS search error: {e}")

    try:
        # 搜索微信公众号：匹配 display_name、description
        # 注意：wechat_accounts 表结构可能与模型不同，使用 try-except 兜底
        from sqlalchemy import func

        wechat_result = await session.execute(
            select(WechatAccount)
            .where(
                or_(
                    WechatAccount.display_name.ilike(search_pattern),
                    func.coalesce(WechatAccount.description, "").ilike(search_pattern),
                ),
            )
            .order_by(WechatAccount.is_active.desc(), WechatAccount.display_name)
            .limit(limit)
        )
        wechat_accounts = wechat_result.scalars().all()
        results["wechat"] = [
            {
                "id": acc.id,
                "type": "wechat",
                "code": getattr(acc, 'account_name', str(acc.id)),
                "name": acc.display_name,
                "description": acc.description or "",
                "is_active": acc.is_active,
            }
            for acc in wechat_accounts
        ]
    except Exception as e:
        logger.warning(f"WeChat search skipped: {e}")
        # 微信搜索失败不影响其他搜索结果

    return results


# ============================================================================
# Subscription API Endpoints
# ============================================================================
# 用户订阅管理 API —— 管理用户对数据源的订阅关系
# 所有端点要求用户登录（CurrentUser 依赖项）

@router.get("/api/subscriptions")
async def list_subscriptions(
    user: CurrentUser,        # 依赖注入：当前已认证用户
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List user's subscriptions.

    返回当前用户的订阅列表。

    Args:
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Subscription list payload.
    """
    # 查询当前用户的所有活跃订阅记录，按数据源类型和 ID 排序
    result = await session.execute(
        select(UserSubscription)
        .where(
            UserSubscription.user_id == user.id,
            UserSubscription.is_active == True,
        )
        .order_by(UserSubscription.source_type, UserSubscription.source_id)
    )
    subscriptions = result.scalars().all()

    return {
        "subscriptions": [
            {
                "id": sub.id,
                "source_type": sub.source_type,  # 数据源类型（如 "arxiv"、"rss"）
                "source_id": sub.source_id,      # 数据源 ID
                "is_active": sub.is_active,      # 订阅是否活跃
            }
            for sub in subscriptions
        ]
    }


@router.post("/api/subscriptions")
async def create_subscription(
    source_type: str,         # 要订阅的数据源类型
    source_id: int,           # 要订阅的数据源 ID
    user: CurrentUser,        # 依赖注入：当前已认证用户
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Create a new subscription.

    创建用户订阅，若已存在则保持幂等。

    Args:
        source_type: Source type.
        source_id: Source ID.
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status payload.
    """
    # 检查是否已存在相同的订阅记录
    result = await session.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.source_type == source_type,
            UserSubscription.source_id == source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 如果订阅已存在且活跃，直接返回成功（幂等操作）
        if existing.is_active:
            return {"status": "ok", "message": "Already subscribed"}
        # 如果订阅已存在但被取消，重新激活（软删除恢复）
        existing.is_active = True
    else:
        # 创建新的订阅记录
        subscription = UserSubscription(
            user_id=user.id,
            source_type=source_type,
            source_id=source_id,
        )
        session.add(subscription)

    return {"status": "ok"}


@router.delete("/api/subscriptions/{source_type}/{source_id}")
async def delete_subscription(
    source_type: str,         # 路径参数：数据源类型
    source_id: int,           # 路径参数：数据源 ID
    user: CurrentUser,        # 依赖注入：当前已认证用户
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Delete a subscription by source type and id.

    取消用户订阅（软删除）。

    Args:
        source_type: Source type.
        source_id: Source ID.
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status payload.
    """
    # 查找匹配的订阅记录
    result = await session.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.source_type == source_type,
            UserSubscription.source_id == source_id,
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        # 采用软删除策略：将 is_active 标记为 False，而非物理删除
        # 这样用户重新订阅时可以恢复历史记录
        subscription.is_active = False

    return {"status": "ok"}


# ============================================================================
# Helpers
# ============================================================================
# 辅助函数 —— Article ORM 模型到字典的转换

def _article_to_dict(article: Article) -> Dict[str, Any]:
    """Convert an Article model to a dictionary.

    将 Article ORM 对象转换为前端友好的字典格式。

    Args:
        article: Article ORM instance.

    Returns:
        Dict[str, Any]: Article dictionary.
    """
    # 将 Article ORM 对象转换为前端友好的字典格式
    # 处理 datetime 到 ISO 格式字符串的转换，None 值安全处理
    return {
        "id": article.id,
        "source_type": article.source_type,   # 数据源类型
        "title": article.title,               # 文章标题
        "url": article.url,                   # 原文链接
        "author": article.author,             # 作者
        "summary": article.summary or "",     # 摘要，None 时返回空字符串
        "content_summary": article.content_summary,  # AI 生成的内容摘要或翻译
        "category": article.category,         # 所属分类
        "tags": article.tags or [],           # 标签列表，None 时返回空列表
        "publish_time": article.publish_time.isoformat() if article.publish_time else None,
        "crawl_time": article.crawl_time.isoformat() if article.crawl_time else None,
        "cover_image_url": article.cover_image_url,  # 封面图 URL
        "is_archived": article.is_archived,   # 是否已归档
        # ArXiv 特有字段
        "arxiv_id": article.arxiv_id,                          # ArXiv 论文 ID
        "arxiv_primary_category": article.arxiv_primary_category,  # ArXiv 主分类
        "arxiv_updated_time": article.arxiv_updated_time.isoformat() if article.arxiv_updated_time else None,
        # 微信公众号特有字段
        "wechat_account_name": article.wechat_account_name,    # 微信公众号名称
    }


# ============================================================================
# Export API Endpoints
# ============================================================================
# 文章导出 API —— 支持将文章导出为 Markdown 格式，便于离线阅读和分享

@router.get("/api/export/markdown")
async def export_markdown(
    source_type: Optional[str] = None,    # 筛选条件：数据源类型
    category: Optional[str] = None,       # 筛选条件：分类
    from_date: Optional[str] = None,      # 筛选条件：起始日期
    to_date: Optional[str] = None,        # 筛选条件：结束日期
    page: int = 1,                        # 页码
    page_size: int = 100,                 # 每页条数（导出时默认 100 条）
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export articles as Markdown.

    根据筛选条件导出文章为 Markdown 文件。

    Args:
        source_type: Source type filter.
        category: Category filter.
        from_date: Start date (ISO).
        to_date: End date (ISO).
        page: Page number.
        page_size: Items per page.
        session: Async database session.

    Returns:
        Response: Markdown download response.
    """
    from datetime import datetime
    from fastapi.responses import Response
    from common.markdown import render_articles_by_source

    # 构建查询：默认排除已归档文章
    query = select(Article).where(Article.is_archived == False)

    # 应用可选的筛选条件
    if source_type:
        query = query.where(Article.source_type == source_type)
    if category:
        query = query.where(Article.category == category)
    if from_date:
        try:
            dt = datetime.fromisoformat(from_date)
            query = query.where(Article.crawl_time >= dt)
        except ValueError:
            pass  # 日期格式无效时忽略
    if to_date:
        try:
            dt = datetime.fromisoformat(to_date)
            query = query.where(Article.crawl_time <= dt)
        except ValueError:
            pass  # 日期格式无效时忽略

    # 按爬取时间倒序排列，并应用分页
    query = query.order_by(Article.crawl_time.desc()).offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    articles = result.scalars().all()

    # 将 ORM 对象批量转换为字典
    article_dicts = [_article_to_dict(a) for a in articles]

    # 使用 Markdown 渲染工具生成格式化的 Markdown 文档
    # render_articles_by_source 会按数据源类型分组展示文章
    date_str = from_date or datetime.now().strftime("%Y-%m-%d")
    markdown = render_articles_by_source(
        article_dicts,
        date=date_str,
        include_abstract=True,    # 包含文章摘要
        abstract_max_len=500,     # 摘要最大长度限制为 500 字符
    )

    # 以文件下载方式返回 Markdown 内容
    # Content-Disposition 头部指示浏览器将响应作为文件下载
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
    from_date: Optional[str] = None,  # 可选的起始日期，默认获取最近 24 小时
    user: CurrentUser = None,         # 当前已认证用户（必须登录）
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export user's subscribed articles as Markdown.

    导出当前用户订阅文章为 Markdown 文件。

    Args:
        from_date: Optional start date (ISO).
        user: Authenticated user.
        session: Async database session.

    Returns:
        Response: Markdown download response.

    Raises:
        HTTPException: If the user is not authenticated.
    """
    from datetime import datetime, timezone, timedelta
    from fastapi.responses import Response
    from common.markdown import render_articles_by_source

    # 用户未登录时返回 401 错误
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 获取当前用户的所有活跃订阅
    sub_result = await session.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.is_active == True,
        )
    )
    subscriptions = sub_result.scalars().all()

    # 如果用户没有任何订阅，返回提示信息
    if not subscriptions:
        return Response(
            content="# 无订阅\n\n您还没有订阅任何内容。",
            media_type="text/markdown",
        )

    # 构建日期过滤条件
    # 如果未指定起始日期，默认获取最近 24 小时的文章
    if from_date:
        try:
            since = datetime.fromisoformat(from_date)
        except ValueError:
            since = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=1)

    # 查询符合时间条件的文章
    # 限制最多返回 100 篇，防止数据量过大
    query = select(Article).where(
        Article.is_archived == False,
        Article.crawl_time >= since,
    ).order_by(Article.crawl_time.desc()).limit(100)

    result = await session.execute(query)
    all_articles = result.scalars().all()

    # 按用户订阅过滤文章（简化实现）
    # TODO: 生产环境中应实现更精确的订阅匹配逻辑
    # 当前实现直接取前 50 篇文章，作为 MVP 版本的临时方案
    matched = []
    for article in all_articles[:50]:
        matched.append(_article_to_dict(article))

    # 使用 Markdown 渲染工具生成文档
    date_str = since.strftime("%Y-%m-%d")
    markdown = render_articles_by_source(
        matched,
        date=date_str,
        include_abstract=True,
        abstract_max_len=500,
    )

    # 以文件下载方式返回
    filename = f"my_subscriptions_{date_str}.md"
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ============================================================================
# RSS Feed Management API Endpoints
# ============================================================================
# RSS 源管理 API —— 允许用户添加自定义 RSS 源，需要验证有效性

class UserRssFeedCreate(BaseModel):
    """User RSS feed create request.

    用户添加 RSS 源请求体。

    Attributes:
        feed_url: RSS feed URL.
        title: Optional feed title.
        category: Optional category name.
    """
    feed_url: str
    title: Optional[str] = None  # 可选，如果不提供则从 feed 中提取
    category: Optional[str] = "用户添加"


class RssFeedValidationResult(BaseModel):
    """RSS feed validation result.

    RSS 源验证结果。

    Attributes:
        valid: Whether the feed is valid.
        title: Feed title.
        description: Feed description.
        site_url: Feed site URL.
        error: Validation error message.
    """
    valid: bool
    title: Optional[str] = None
    description: Optional[str] = None
    site_url: Optional[str] = None
    error: Optional[str] = None


async def validate_rss_feed(feed_url: str) -> RssFeedValidationResult:
    """Validate an RSS feed and extract metadata.

    使用 feedparser 解析 RSS 源，验证其有效性并提取标题等信息。

    Args:
        feed_url: RSS feed URL.

    Returns:
        RssFeedValidationResult: Validation result and metadata.
    """
    import feedparser
    from urllib.parse import urlparse

    try:
        # 解析 RSS 源
        feed = feedparser.parse(feed_url)

        # 检查解析是否成功
        if feed.bozo and not feed.entries:
            # bozo 表示解析过程中遇到问题，如果没有条目则认为无效
            error_msg = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else "Invalid feed format"
            return RssFeedValidationResult(
                valid=False,
                error=f"RSS 解析失败: {error_msg}"
            )

        # 检查是否有条目
        if not feed.entries:
            return RssFeedValidationResult(
                valid=False,
                error="RSS 源中没有找到任何文章"
            )

        # 提取元数据
        feed_info = feed.feed
        title = feed_info.get('title', '')
        description = feed_info.get('description', '')
        site_url = feed_info.get('link', '')

        # 如果没有标题，尝试从 URL 提取
        if not title:
            parsed = urlparse(feed_url)
            title = parsed.netloc or "Unknown Feed"

        return RssFeedValidationResult(
            valid=True,
            title=title,
            description=description,
            site_url=site_url,
        )

    except Exception as e:
        return RssFeedValidationResult(
            valid=False,
            error=f"验证失败: {str(e)}"
        )


@router.post("/api/feeds/validate")
async def validate_feed(
    feed_data: UserRssFeedCreate,
    user: CurrentUser,  # 需要登录
) -> RssFeedValidationResult:
    """Validate an RSS feed before submission.

    此接口供前端在用户提交前预览验证结果。

    Args:
        feed_data: Feed submission payload.
        user: Authenticated user.

    Returns:
        RssFeedValidationResult: Validation result.
    """
    return await validate_rss_feed(feed_data.feed_url)


@router.post("/api/feeds/add")
async def add_rss_feed(
    feed_data: UserRssFeedCreate,
    user: CurrentUser,  # 需要登录
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Add a user-submitted RSS feed.

    验证 RSS 源有效性后，将其添加到候选列表（is_active=False），
    等待管理员审批后激活。

    Args:
        feed_data: Feed submission payload.
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Status payload for submission.

    Raises:
        HTTPException: If feed is invalid or already exists.
    """
    # 验证 RSS 源
    validation = await validate_rss_feed(feed_data.feed_url)

    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.error)

    # 检查是否已存在
    existing = await session.execute(
        select(RssFeed).where(RssFeed.feed_url == feed_data.feed_url)
    )
    existing_feed = existing.scalar_one_or_none()

    if existing_feed:
        if existing_feed.is_active:
            raise HTTPException(status_code=400, detail="此 RSS 源已存在于系统中")
        else:
            # 如果存在但未激活，返回提示
            return {
                "status": "pending",
                "message": "此 RSS 源已提交，等待管理员审批",
                "feed_id": existing_feed.id,
            }

    # 创建新的 RSS 源（默认不激活，等待审批）
    title = feed_data.title or validation.title or "Unknown Feed"
    feed = RssFeed(
        title=title,
        feed_url=feed_data.feed_url,
        site_url=validation.site_url or "",
        category=feed_data.category or "用户添加",
        description=validation.description or "",
        is_active=False,  # 默认不激活，等待管理员审批
    )
    session.add(feed)
    await session.flush()

    return {
        "status": "pending",
        "message": "RSS 源已提交，等待管理员审批",
        "feed_id": feed.id,
        "title": feed.title,
    }


@router.get("/api/feeds/pending")
async def list_pending_feeds(
    user: CurrentUser,  # 需要登录
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List pending RSS feeds.

    获取待审批的 RSS 源列表（用户可查看自己提交的）。

    Args:
        user: Authenticated user.
        session: Async database session.

    Returns:
        Dict[str, Any]: Pending feed list payload.
    """
    # 查询所有待审批的 RSS 源
    result = await session.execute(
        select(RssFeed)
        .where(RssFeed.is_active == False)
        .where(RssFeed.category == "用户添加")
        .order_by(desc(RssFeed.created_at))
    )
    feeds = result.scalars().all()

    return {
        "feeds": [
            {
                "id": feed.id,
                "title": feed.title,
                "feed_url": feed.feed_url,
                "site_url": feed.site_url,
                "description": feed.description,
                "created_at": feed.created_at.isoformat() if feed.created_at else None,
            }
            for feed in feeds
        ]
    }


@router.get("/api/feeds/all")
async def list_all_feeds_for_subscription(
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all RSS feeds for subscription.

    获取所有 RSS 源（包括活跃的和待审批的），供用户订阅选择。

    Args:
        session: Async database session.

    Returns:
        Dict[str, Any]: Feed list payload.
    """
    # 查询所有 RSS 源
    result = await session.execute(
        select(RssFeed)
        .order_by(desc(RssFeed.is_active), RssFeed.category, RssFeed.title)
    )
    feeds = result.scalars().all()

    return {
        "feeds": [
            {
                "id": feed.id,
                "title": feed.title,
                "feed_url": feed.feed_url,
                "category": feed.category,
                "is_active": feed.is_active,
                "last_fetched_at": feed.last_fetched_at.isoformat() if feed.last_fetched_at else None,
            }
            for feed in feeds
        ]
    }
