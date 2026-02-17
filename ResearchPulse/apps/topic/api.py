# ==============================================================================
# 模块: topic/api.py
# 功能: 话题(Topic)模块的 RESTful API 端点定义
# 架构角色: 作为话题模块的对外接口层(Controller层), 负责接收 HTTP 请求,
#           调用 TopicService 进行业务处理, 并返回格式化的响应数据。
#           所有端点均受 feature.topic_radar 功能开关保护,
#           确保话题雷达功能未启用时所有接口不可访问。
# ==============================================================================
"""Topic API endpoints."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.dependencies import get_current_user, require_permissions
from common.feature_config import require_feature
from .schemas import (DiscoverResponse, TopicArticleSchema, TopicCreateRequest, TopicListResponse, TopicSchema, TopicSuggestionSchema, TopicTrendSchema, TopicUpdateRequest)
from .service import TopicService

# 初始化模块级别的日志记录器, 用于记录 API 层的请求处理信息
logger = logging.getLogger(__name__)

# 创建 API 路由器, 标签为 "Topics", 所有端点都需要 topic_radar 功能开关开启
router = APIRouter(tags=["Topics"], dependencies=[require_feature("feature.topic_radar")])

# --------------------------------------------------------------------------
# GET /topics - 获取话题列表
# 功能: 查询所有话题, 支持按活跃状态过滤
# 参数:
#   - active_only: 是否仅返回活跃话题, 默认 True
#   - db: 异步数据库会话(通过依赖注入获取)
# 返回: TopicListResponse, 包含话题总数和话题列表
# --------------------------------------------------------------------------
@router.get("", response_model=TopicListResponse)
async def list_topics(active_only: bool = True, db: AsyncSession = Depends(get_session)):
    service = TopicService()
    topics, total = await service.list_topics(db, active_only=active_only)
    return TopicListResponse(total=total, topics=[TopicSchema.model_validate(t) for t in topics])

# --------------------------------------------------------------------------
# POST /topics - 创建新话题
# 功能: 由当前登录用户手动创建一个新话题
# 参数:
#   - request: 话题创建请求体, 包含名称、描述和关键词
#   - user: 当前登录用户(通过依赖注入获取, 用于记录创建者)
#   - db: 异步数据库会话
# 返回: 新创建的话题数据 (TopicSchema), HTTP 状态码 201
# --------------------------------------------------------------------------
@router.post("", response_model=TopicSchema, status_code=201)
async def create_topic(request: TopicCreateRequest, user=Depends(require_permissions("topic:manage")), db: AsyncSession = Depends(get_session)):
    service = TopicService()
    topic = await service.create_topic(request.name, request.description, request.keywords, user.id, db)
    return TopicSchema.model_validate(topic)

# --------------------------------------------------------------------------
# GET /topics/{topic_id} - 获取单个话题详情
# 功能: 根据话题 ID 查询话题的完整信息
# 参数:
#   - topic_id: 话题的唯一标识符
#   - db: 异步数据库会话
# 返回: 话题详情 (TopicSchema), 若不存在则返回 404 错误
# --------------------------------------------------------------------------
@router.get("/{topic_id}", response_model=TopicSchema)
async def get_topic(topic_id: int, db: AsyncSession = Depends(get_session)):
    service = TopicService()
    topic = await service.get_topic(topic_id, db)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return TopicSchema.model_validate(topic)

# --------------------------------------------------------------------------
# PUT /topics/{topic_id} - 更新话题
# 功能: 更新指定话题的属性(名称、描述、关键词、激活状态等)
# 参数:
#   - topic_id: 话题的唯一标识符
#   - request: 话题更新请求体, 仅更新提供的字段(exclude_unset=True)
#   - user: 当前登录用户(需要认证)
#   - db: 异步数据库会话
# 返回: 更新后的话题数据 (TopicSchema), 若不存在则返回 404 错误
# 设计说明: 使用 model_dump(exclude_unset=True) 实现部分更新(PATCH语义),
#           只传递用户明确设置的字段, 避免将未传的字段置为 None
# --------------------------------------------------------------------------
@router.put("/{topic_id}", response_model=TopicSchema)
async def update_topic(topic_id: int, request: TopicUpdateRequest, user=Depends(require_permissions("topic:manage")), db: AsyncSession = Depends(get_session)):
    service = TopicService()
    topic = await service.get_topic(topic_id, db)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    # 所有权校验：创建者 or admin/superuser
    if (topic.created_by_user_id != user.id
            and not user.is_superuser
            and not user.has_role("admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to update this topic",
        )
    updated = await service.update_topic(topic_id, db, **request.model_dump(exclude_unset=True))
    return TopicSchema.model_validate(updated)

# --------------------------------------------------------------------------
# DELETE /topics/{topic_id} - 删除话题
# 功能: 删除指定的话题
# 参数:
#   - topic_id: 话题的唯一标识符
#   - user: 当前登录用户(需要认证)
#   - db: 异步数据库会话
# 返回: 成功时返回 {"status": "ok"}, 若不存在则返回 404 错误
# --------------------------------------------------------------------------
@router.delete("/{topic_id}")
async def delete_topic(topic_id: int, user=Depends(require_permissions("topic:manage")), db: AsyncSession = Depends(get_session)):
    service = TopicService()
    topic = await service.get_topic(topic_id, db)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    # 所有权校验：创建者 or admin/superuser
    if (topic.created_by_user_id != user.id
            and not user.is_superuser
            and not user.has_role("admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to delete this topic",
        )
    await service.delete_topic(topic_id, db)
    return {"status": "ok"}

# --------------------------------------------------------------------------
# GET /topics/{topic_id}/articles - 获取话题关联的文章列表
# 功能: 查询与指定话题关联的文章, 按匹配分数降序排列
# 参数:
#   - topic_id: 话题的唯一标识符
#   - limit: 返回数量上限, 默认 50
#   - db: 异步数据库会话
# 返回: 文章列表, 每条包含文章ID、标题、匹配分数和匹配到的关键词
# --------------------------------------------------------------------------
@router.get("/{topic_id}/articles", response_model=list[TopicArticleSchema])
async def get_topic_articles(topic_id: int, limit: int = 50, db: AsyncSession = Depends(get_session)):
    service = TopicService()
    articles = await service.get_topic_articles(topic_id, db, limit=limit)
    return [TopicArticleSchema(**a) for a in articles]

# --------------------------------------------------------------------------
# POST /topics/discover - 自动发现新话题
# 功能: 基于近期文章内容, 自动发现潜在的新话题候选
# 参数:
#   - user: 当前登录用户(需要认证)
#   - db: 异步数据库会话
# 返回: DiscoverResponse, 包含话题建议列表(名称、关键词、频率、置信度等)
# 设计说明: 该功能利用实体识别和词频分析从最近文章中提取潜在新话题,
#           帮助用户发现值得跟踪的新趋势
# --------------------------------------------------------------------------
@router.post("/discover", response_model=DiscoverResponse)
async def discover(user=Depends(require_permissions("topic:discover")), db: AsyncSession = Depends(get_session)):
    service = TopicService()
    suggestions = await service.discover(db)
    return DiscoverResponse(suggestions=[TopicSuggestionSchema(**s) for s in suggestions])

# --------------------------------------------------------------------------
# GET /topics/{topic_id}/trend - 获取话题趋势
# 功能: 检测指定话题在一段时间内的热度变化趋势
# 参数:
#   - topic_id: 话题的唯一标识符
#   - period_days: 统计周期天数, 默认 7 天
#   - db: 异步数据库会话
# 返回: TopicTrendSchema, 包含趋势方向(up/down/stable)、变化百分比、
#        当前周期和上一周期的文章数量
# --------------------------------------------------------------------------
@router.get("/{topic_id}/trend", response_model=TopicTrendSchema)
async def get_trend(topic_id: int, period_days: int = 7, db: AsyncSession = Depends(get_session)):
    service = TopicService()
    trend = await service.get_trend(topic_id, db, period_days=period_days)
    return TopicTrendSchema(**trend)
