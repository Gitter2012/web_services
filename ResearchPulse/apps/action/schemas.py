# ==============================================================================
# 模块: action/schemas.py
# 功能: 行动项模块的 Pydantic 数据验证与序列化模型 (Schema 层)
# 架构角色: 定义 API 层的请求体和响应体结构, 负责:
#   1. 请求参数验证 (ActionItemCreateRequest, ActionItemUpdateRequest)
#   2. 响应数据序列化 (ActionItemSchema)
#   3. 列表响应封装 (ActionListResponse)
# 设计说明: 行动项的类型和优先级使用中文字符串表示, 与用户界面保持一致
# ==============================================================================
"""Action item schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# ActionItemCreateRequest - 创建行动项的请求模型
# 用途: 用户手动创建行动项或系统从文章中提取行动项时使用
# 字段:
#   - article_id: 关联的文章 ID
#   - type: 行动项类型, 默认 "跟进", 可选值: 跟进/验证/决策/触发器
#   - description: 行动项的具体描述
#   - priority: 优先级, 默认 "中", 可选值: 高/中/低
# --------------------------------------------------------------------------
class ActionItemCreateRequest(BaseModel):
    article_id: int
    type: str = Field(default="跟进", description="跟进, 验证, 决策, 触发器")
    description: str
    priority: str = Field(default="中", description="高, 中, 低")


# --------------------------------------------------------------------------
# ActionItemUpdateRequest - 更新行动项的请求模型
# 用途: 修改已有行动项的属性
# 设计说明: 所有字段均为 Optional, 配合 model_dump(exclude_unset=True)
#           实现部分更新, 只修改用户明确传递的字段
#           注意: status 不在此模型中, 状态变更通过专用的 complete/dismiss 端点处理
# --------------------------------------------------------------------------
class ActionItemUpdateRequest(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None


# --------------------------------------------------------------------------
# ActionItemSchema - 行动项的完整响应模型
# 用途: 返回行动项详情时使用的序列化格式
# 字段说明:
#   - id: 行动项唯一标识
#   - article_id: 关联文章 ID
#   - user_id: 所属用户 ID
#   - type: 行动项类型
#   - description: 描述内容
#   - priority: 优先级
#   - status: 当前状态 (pending/completed/dismissed)
#   - completed_at: 完成时间 (仅 completed 状态有值)
#   - dismissed_at: 忽略时间 (仅 dismissed 状态有值)
#   - created_at: 创建时间
# 设计说明: from_attributes=True 允许直接从 SQLAlchemy ORM 对象转换
# --------------------------------------------------------------------------
class ActionItemSchema(BaseModel):
    id: int
    article_id: int
    user_id: int
    type: str = ""
    description: str = ""
    priority: str = "中"
    status: str = "pending"
    completed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}  # 启用 ORM 模型属性映射


# --------------------------------------------------------------------------
# ActionListResponse - 行动项列表的分页响应模型
# 用途: 列表查询接口的响应格式, 包含总数和行动项列表
# --------------------------------------------------------------------------
class ActionListResponse(BaseModel):
    total: int = 0  # 行动项总数
    actions: list[ActionItemSchema] = Field(default_factory=list)  # 行动项列表
