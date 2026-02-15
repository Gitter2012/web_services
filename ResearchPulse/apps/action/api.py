# ==============================================================================
# 模块: action/api.py
# 功能: 行动项(Action Items)模块的 RESTful API 端点定义
# 架构角色: 作为行动项模块的对外接口层(Controller层), 提供行动项的完整
#           生命周期管理接口, 包括创建、查询、更新、完成和忽略操作。
#           所有端点均受 feature.action_items 功能开关保护,
#           确保行动项功能未启用时所有接口不可访问。
# 设计说明: 行动项是从 AI 处理后的文章中提取出的可执行任务,
#           帮助用户将信息转化为具体行动。每个行动项绑定到特定用户,
#           只有创建者本人才能操作自己的行动项。
# ==============================================================================
"""Action items API endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import get_current_user
from common.feature_config import require_feature
from .schemas import (
    ActionItemCreateRequest,
    ActionItemSchema,
    ActionItemUpdateRequest,
    ActionListResponse,
)
from .service import ActionService

# 初始化模块级别的日志记录器
logger = logging.getLogger(__name__)

# 创建 API 路由器, 标签为 "Actions", 所有端点都需要 action_items 功能开关开启
router = APIRouter(tags=["Actions"], dependencies=[require_feature("feature.action_items")])


# --------------------------------------------------------------------------
# GET /actions - 获取当前用户的行动项列表
# 功能: 查询当前登录用户的行动项, 支持按状态过滤和分页
# 参数:
#   - status: 按状态过滤 (pending/completed/dismissed), 为 None 时不过滤
#   - limit: 每页返回数量上限, 默认 50
#   - offset: 分页偏移量, 默认 0
#   - user: 当前登录用户(通过依赖注入获取)
#   - db: 异步数据库会话
# 返回: ActionListResponse, 包含行动项总数和行动项列表
# --------------------------------------------------------------------------
@router.get("", response_model=ActionListResponse)
async def list_actions(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ActionService()
    actions, total = await service.list_actions(
        user.id, db, status=status, limit=limit, offset=offset
    )
    return ActionListResponse(
        total=total,
        actions=[ActionItemSchema.model_validate(a) for a in actions],
    )


# --------------------------------------------------------------------------
# POST /actions - 创建新行动项
# 功能: 为当前用户创建一个与指定文章关联的行动项
# 参数:
#   - request: 行动项创建请求体, 包含关联文章ID、类型、描述和优先级
#   - user: 当前登录用户
#   - db: 异步数据库会话
# 返回: 新创建的行动项数据 (ActionItemSchema), HTTP 状态码 201
# --------------------------------------------------------------------------
@router.post("", response_model=ActionItemSchema, status_code=201)
async def create_action(
    request: ActionItemCreateRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ActionService()
    action = await service.create_action(
        user.id,
        request.article_id,
        request.type,
        request.description,
        request.priority,
        db,
    )
    return ActionItemSchema.model_validate(action)


# --------------------------------------------------------------------------
# GET /actions/{action_id} - 获取单个行动项详情
# 功能: 根据行动项 ID 查询详细信息, 仅限所属用户访问
# 参数:
#   - action_id: 行动项的唯一标识符
#   - user: 当前登录用户 (用于所有权校验)
#   - db: 异步数据库会话
# 返回: 行动项详情 (ActionItemSchema), 若不存在或不属于当前用户则返回 404
# --------------------------------------------------------------------------
@router.get("/{action_id}", response_model=ActionItemSchema)
async def get_action(
    action_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ActionService()
    action = await service.get_action(action_id, user.id, db)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return ActionItemSchema.model_validate(action)


# --------------------------------------------------------------------------
# PUT /actions/{action_id} - 更新行动项
# 功能: 更新指定行动项的属性 (类型、描述、优先级)
# 参数:
#   - action_id: 行动项的唯一标识符
#   - request: 更新请求体, 仅更新提供的字段 (exclude_unset=True)
#   - user: 当前登录用户 (用于所有权校验)
#   - db: 异步数据库会话
# 返回: 更新后的行动项数据, 若不存在则返回 404 错误
# --------------------------------------------------------------------------
@router.put("/{action_id}", response_model=ActionItemSchema)
async def update_action(
    action_id: int,
    request: ActionItemUpdateRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ActionService()
    action = await service.update_action(
        action_id, user.id, db, **request.model_dump(exclude_unset=True)
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return ActionItemSchema.model_validate(action)


# --------------------------------------------------------------------------
# POST /actions/{action_id}/complete - 标记行动项为已完成
# 功能: 将指定行动项的状态从 pending 更改为 completed, 并记录完成时间
# 参数:
#   - action_id: 行动项的唯一标识符
#   - user: 当前登录用户 (用于所有权校验)
#   - db: 异步数据库会话
# 返回: 更新后的行动项数据, 若不存在则返回 404 错误
# 副作用: 设置 status="completed" 和 completed_at 时间戳
# --------------------------------------------------------------------------
@router.post("/{action_id}/complete", response_model=ActionItemSchema)
async def complete_action(
    action_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ActionService()
    action = await service.complete_action(action_id, user.id, db)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return ActionItemSchema.model_validate(action)


# --------------------------------------------------------------------------
# POST /actions/{action_id}/dismiss - 忽略/驳回行动项
# 功能: 将指定行动项的状态从 pending 更改为 dismissed, 并记录忽略时间
# 参数:
#   - action_id: 行动项的唯一标识符
#   - user: 当前登录用户 (用于所有权校验)
#   - db: 异步数据库会话
# 返回: 更新后的行动项数据, 若不存在则返回 404 错误
# 副作用: 设置 status="dismissed" 和 dismissed_at 时间戳
# 设计说明: dismissed 表示用户认为该行动项不需要执行, 与 completed 区分
# --------------------------------------------------------------------------
@router.post("/{action_id}/dismiss", response_model=ActionItemSchema)
async def dismiss_action(
    action_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ActionService()
    action = await service.dismiss_action(action_id, user.id, db)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return ActionItemSchema.model_validate(action)
