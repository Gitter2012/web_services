# =============================================================================
# 模块: apps/daily_report/api.py
# 功能: 每日 arXiv 报告 API 端点
# 架构角色: 对外接口层，提供报告的生成、查询、导出功能
# =============================================================================

"""Daily report API endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import require_permissions
from common.feature_config import require_feature
from .schemas import (
    DailyReportResponse,
    DailyReportListResponse,
    DailyReportDetail,
    GenerateReportRequest,
    GenerateReportResponse,
    ExportResponse,
    DailyExportResponse,
)
from .service import DailyReportService

logger = logging.getLogger(__name__)

# 创建 API 路由器
router = APIRouter(
    prefix="/daily-reports",
    tags=["Daily Reports"],
    dependencies=[require_feature("daily_report.enabled")],
)


# --------------------------------------------------------------------------
# GET /daily-reports - 获取报告列表
# 功能: 查询每日报告列表，支持按日期、分类、状态筛选
# --------------------------------------------------------------------------
@router.get("", response_model=DailyReportListResponse)
async def list_reports(
    report_date: Optional[date] = Query(None, description="报告日期"),
    category: Optional[str] = Query(None, description="arXiv 分类代码"),
    status: Optional[str] = Query(None, description="报告状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user=Depends(require_permissions("daily_report:read")),
    db: AsyncSession = Depends(get_session),
):
    """获取每日报告列表"""
    service = DailyReportService()
    reports, total = await service.list_reports(
        db,
        report_date=report_date,
        category=category,
        status=status,
        page=page,
        page_size=page_size,
    )

    return DailyReportListResponse(
        total=total,
        page=page,
        page_size=page_size,
        reports=[DailyReportResponse.model_validate(r) for r in reports],
    )


# --------------------------------------------------------------------------
# GET /daily-reports/{report_id} - 获取单个报告详情
# 功能: 根据报告 ID 查询报告的完整内容
# --------------------------------------------------------------------------
@router.get("/{report_id}", response_model=DailyReportDetail)
async def get_report(
    report_id: int,
    user=Depends(require_permissions("daily_report:read")),
    db: AsyncSession = Depends(get_session),
):
    """获取报告详情"""
    service = DailyReportService()
    report = await service.get_report_by_id(db, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return DailyReportDetail.model_validate(report)


# --------------------------------------------------------------------------
# GET /daily-reports/{report_id}/export - 导出报告
# 功能: 导出报告为指定格式（markdown 或 wechat）
# --------------------------------------------------------------------------
@router.get("/{report_id}/export", response_model=ExportResponse)
async def export_report(
    report_id: int,
    format: str = Query("markdown", description="导出格式: markdown 或 wechat"),
    user=Depends(require_permissions("daily_report:export")),
    db: AsyncSession = Depends(get_session),
):
    """导出报告"""
    service = DailyReportService()
    result = await service.export_report(db, report_id, format)

    if not result:
        raise HTTPException(status_code=404, detail="Report not found")

    return ExportResponse(**result)


# --------------------------------------------------------------------------
# POST /daily-reports/generate - 手动触发报告生成
# 功能: 手动生成指定日期的报告
# --------------------------------------------------------------------------
@router.post("/generate", response_model=GenerateReportResponse)
async def generate_reports(
    request: GenerateReportRequest = GenerateReportRequest(),
    user=Depends(require_permissions("daily_report:generate")),
):
    """手动触发报告生成"""
    service = DailyReportService()

    try:
        reports = await service.generate_daily_reports(
            report_date=request.report_date,
            categories=request.categories,
        )

        return GenerateReportResponse(
            success=True,
            message=f"成功生成 {len(reports)} 份报告",
            reports=[DailyReportResponse.model_validate(r) for r in reports],
        )

    except Exception as e:
        logger.error(f"Failed to generate reports: {e}")
        return GenerateReportResponse(
            success=False,
            message=f"报告生成失败: {str(e)}",
            errors=[str(e)],
        )


# --------------------------------------------------------------------------
# GET /daily-reports/export-daily - 导出一天所有报告
# 功能: 导出指定日期所有分类的报告（合并版）
# --------------------------------------------------------------------------
@router.get("/export-daily", response_model=DailyExportResponse)
async def export_daily(
    report_date: date = Query(..., description="报告日期"),
    format: str = Query("wechat", description="导出格式: markdown 或 wechat"),
    user=Depends(require_permissions("daily_report:export")),
    db: AsyncSession = Depends(get_session),
):
    """导出一天所有分类的报告（合并版）"""
    service = DailyReportService()
    result = await service.export_daily(db, report_date, format)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No reports found for {report_date}",
        )

    return DailyExportResponse(
        report_date=result["report_date"],
        format=result["format"],
        total_articles=result["total_articles"],
        categories=result["categories"],
        content=result["content"],
        reports=[DailyReportResponse.model_validate(r) for r in result["reports"]],
    )
