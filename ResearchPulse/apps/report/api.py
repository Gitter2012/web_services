# ==============================================================================
# 模块: report/api.py
# 功能: 报告(Report)模块的 RESTful API 端点定义
# 架构角色: 作为报告模块的对外接口层(Controller层), 提供报告的生成、
#           查询和删除功能。支持周报和月报两种类型的自动生成。
#           所有端点均受 feature.report_generation 功能开关保护,
#           确保报告生成功能未启用时所有接口不可访问。
# 设计说明: 报告是对一段时间内信息摘要的自动化汇总,
#           包含文章统计、事件分析、关键词趋势和行动项回顾等内容。
#           报告绑定到特定用户, 支持历史报告回溯。
# ==============================================================================
"""Report API endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import get_current_user
from common.feature_config import require_feature
from .schemas import GenerateReportRequest, ReportListResponse, ReportSchema
from .service import ReportService

# 初始化模块级别的日志记录器
logger = logging.getLogger(__name__)

# 创建 API 路由器, 标签为 "Reports", 所有端点都需要 report_generation 功能开关开启
router = APIRouter(tags=["Reports"], dependencies=[require_feature("feature.report_generation")])


# --------------------------------------------------------------------------
# GET /reports - 获取当前用户的报告列表
# 功能: 查询当前登录用户的历史报告, 按生成时间倒序排列
# 参数:
#   - limit: 返回数量上限, 默认 20
#   - user: 当前登录用户(通过依赖注入获取)
#   - db: 异步数据库会话
# 返回: ReportListResponse, 包含报告总数和报告列表
# --------------------------------------------------------------------------
@router.get("", response_model=ReportListResponse)
async def list_reports(
    limit: int = 20,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ReportService()
    reports, total = await service.list_reports(user.id, db, limit=limit)
    return ReportListResponse(
        total=total,
        reports=[ReportSchema.model_validate(r) for r in reports],
    )


# --------------------------------------------------------------------------
# POST /reports/weekly - 生成周报
# 功能: 为当前用户生成指定周的周报
# 参数:
#   - request: 生成请求体, 包含 weeks_ago (0 = 本周, 1 = 上周, 以此类推)
#   - user: 当前登录用户
#   - db: 异步数据库会话
# 返回: 新生成的报告数据 (ReportSchema)
# 设计说明: 周报覆盖周一到周日的完整一周, weeks_ago 允许回溯生成历史周报
# --------------------------------------------------------------------------
@router.post("/weekly", response_model=ReportSchema)
async def generate_weekly(
    request: GenerateReportRequest = GenerateReportRequest(),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ReportService()
    report = await service.generate_weekly(
        user.id, db, weeks_ago=request.weeks_ago
    )
    return ReportSchema.model_validate(report)


# --------------------------------------------------------------------------
# POST /reports/monthly - 生成月报
# 功能: 为当前用户生成指定月的月报
# 参数:
#   - months_ago: 回溯月数 (0 = 本月, 1 = 上月, 以此类推)
#   - user: 当前登录用户
#   - db: 异步数据库会话
# 返回: 新生成的报告数据 (ReportSchema)
# 设计说明: 月报覆盖指定月份的第一天到最后一天
# --------------------------------------------------------------------------
@router.post("/monthly", response_model=ReportSchema)
async def generate_monthly(
    months_ago: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ReportService()
    report = await service.generate_monthly(
        user.id, db, months_ago=months_ago
    )
    return ReportSchema.model_validate(report)


# --------------------------------------------------------------------------
# GET /reports/{report_id} - 获取单个报告详情
# 功能: 根据报告 ID 查询报告的完整内容
# 参数:
#   - report_id: 报告的唯一标识符
#   - db: 异步数据库会话
# 返回: 报告详情 (ReportSchema), 若不存在则返回 404 错误
# 设计说明: 此端点不要求用户认证, 可以通过报告 ID 直接访问
#           (适用于报告分享场景)
# --------------------------------------------------------------------------
@router.get("/{report_id}", response_model=ReportSchema)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_session),
):
    service = ReportService()
    report = await service.get_report(report_id, db)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportSchema.model_validate(report)


# --------------------------------------------------------------------------
# DELETE /reports/{report_id} - 删除报告
# 功能: 删除指定的报告
# 参数:
#   - report_id: 报告的唯一标识符
#   - user: 当前登录用户(需要认证)
#   - db: 异步数据库会话
# 返回: 成功时返回 {"status": "ok"}, 若不存在则返回 404 错误
# --------------------------------------------------------------------------
@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    service = ReportService()
    if not await service.delete_report(report_id, db):
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "ok"}
