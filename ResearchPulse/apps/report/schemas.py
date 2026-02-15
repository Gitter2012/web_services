# ==============================================================================
# 模块: report/schemas.py
# 功能: 报告模块的 Pydantic 数据验证与序列化模型 (Schema 层)
# 架构角色: 定义 API 层的请求体和响应体结构, 负责:
#   1. 请求参数验证 (GenerateReportRequest)
#   2. 响应数据序列化 (ReportSchema)
#   3. 列表响应封装 (ReportListResponse)
# 设计说明: 报告模块的 Schema 相对简单, 因为报告的内容主要由后端生成,
#           前端只需要指定时间范围参数
# ==============================================================================
"""Report schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# GenerateReportRequest - 生成报告的请求模型
# 用途: 生成周报时指定回溯的周数
# 字段:
#   - weeks_ago: 回溯周数, 0 表示本周, 1 表示上周, 以此类推
#              最小值 0, 最大值 52 (最多回溯一年)
# --------------------------------------------------------------------------
class GenerateReportRequest(BaseModel):
    weeks_ago: int = Field(default=0, ge=0, le=52)


# --------------------------------------------------------------------------
# ReportSchema - 报告的完整响应模型
# 用途: 返回报告详情时使用的序列化格式
# 字段说明:
#   - id: 报告唯一标识
#   - user_id: 所属用户 ID
#   - type: 报告类型 (weekly/monthly)
#   - period_start: 覆盖的起始日期 (YYYY-MM-DD)
#   - period_end: 覆盖的结束日期 (YYYY-MM-DD)
#   - title: 报告标题 (自动生成)
#   - content: 报告正文 (Markdown 格式)
#   - stats: 结构化统计数据 (JSON 字典)
#   - generated_at: 报告生成时间
#   - created_at: 数据库记录创建时间
# 设计说明: from_attributes=True 允许直接从 SQLAlchemy ORM 对象转换
# --------------------------------------------------------------------------
class ReportSchema(BaseModel):
    id: int
    user_id: int
    type: str = ""
    period_start: str = ""
    period_end: str = ""
    title: str = ""
    content: str = ""
    stats: Optional[dict] = None  # 结构化统计数据, 包含各类聚合指标
    generated_at: Optional[datetime] = None  # 报告生成时间
    created_at: Optional[datetime] = None  # 数据库记录创建时间
    model_config = {"from_attributes": True}  # 启用 ORM 模型属性映射


# --------------------------------------------------------------------------
# ReportListResponse - 报告列表的分页响应模型
# 用途: 列表查询接口的响应格式, 包含总数和报告列表
# --------------------------------------------------------------------------
class ReportListResponse(BaseModel):
    total: int = 0  # 报告总数
    reports: list[ReportSchema] = Field(default_factory=list)  # 报告列表
