# =============================================================================
# Event 事件聚类 API 端点模块
# =============================================================================
# 本模块定义了事件聚类相关的 RESTful API 接口。
# 在架构中，它是 Event 子系统对外暴露的 HTTP 层，负责：
#   1. 列出事件聚类列表（支持筛选活跃/全部、分页）
#   2. 查看单个事件聚类的详细信息
#   3. 手动触发事件聚类任务
#   4. 获取事件的时间线（按时间排列的关联文章）
# 所有端点均需启用 "feature.event_clustering" 功能开关才可访问。
# =============================================================================

"""Event API endpoints."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.dependencies import get_current_user, require_permissions
from common.feature_config import require_feature
from .schemas import (EventClusterDetailSchema, EventClusterSchema, EventListResponse, EventTimelineEntry, TriggerClusterRequest, TriggerClusterResponse)
from .service import EventService

logger = logging.getLogger(__name__)

# 创建路由器，所有端点归属于 "Events" 标签组
# 通过 require_feature 确保只有启用了 event_clustering 功能时才可访问
router = APIRouter(tags=["Events"], dependencies=[require_feature("feature.event_clustering")])

# -----------------------------------------------------------------------------
# 事件列表查询接口
# 支持按活跃状态筛选和分页
# -----------------------------------------------------------------------------
@router.get("", response_model=EventListResponse)
async def list_events(active_only: bool = True, limit: int = 50, offset: int = 0, user=Depends(require_permissions("event:read")), db: AsyncSession = Depends(get_session)):
    """List event clusters."""
    service = EventService()
    # active_only: 默认只返回活跃的事件聚类
    events, total = await service.get_events(db, active_only=active_only, limit=limit, offset=offset)
    # 使用 model_validate 将 ORM 对象转换为 Pydantic Schema
    return EventListResponse(total=total, events=[EventClusterSchema.model_validate(e) for e in events])

# -----------------------------------------------------------------------------
# 事件详情查询接口
# 返回事件聚类的完整信息，包括关联的成员文章列表
# -----------------------------------------------------------------------------
@router.get("/{event_id}", response_model=EventClusterDetailSchema)
async def get_event(event_id: int, user=Depends(require_permissions("event:read")), db: AsyncSession = Depends(get_session)):
    """Get event detail."""
    service = EventService()
    event = await service.get_event(event_id, db)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventClusterDetailSchema.model_validate(event)

# -----------------------------------------------------------------------------
# 手动触发事件聚类接口
# 将未聚类的文章与现有事件聚类进行匹配，或创建新的事件聚类
# 需要用户认证（管理员操作）
# -----------------------------------------------------------------------------
@router.post("/cluster", response_model=TriggerClusterResponse)
async def trigger_clustering(request: TriggerClusterRequest, user=Depends(require_permissions("event:cluster")), db: AsyncSession = Depends(get_session)):
    """Trigger event clustering."""
    service = EventService()
    # limit: 本次处理的文章上限
    # min_importance: 最低重要性阈值，低于此值的文章不参与聚类
    result = await service.cluster_articles(db, limit=request.limit, min_importance=request.min_importance)
    return TriggerClusterResponse(**result)

# -----------------------------------------------------------------------------
# 事件时间线查询接口
# 按时间倒序返回事件关联的文章列表，形成事件发展的时间线
# -----------------------------------------------------------------------------
@router.get("/{event_id}/timeline", response_model=list[EventTimelineEntry])
async def get_timeline(event_id: int, user=Depends(require_permissions("event:read")), db: AsyncSession = Depends(get_session)):
    """Get event timeline."""
    service = EventService()
    event = await service.get_event(event_id, db)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    entries = await service.get_event_timeline(event_id, db)
    # 将时间线数据转换为 Schema 格式
    return [EventTimelineEntry(date=e["date"], summary=e.get("summary", ""), article_count=1) for e in entries]
