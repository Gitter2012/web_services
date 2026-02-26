# =============================================================================
# 模块: apps/daily_report/schemas/report.py
# 功能: 每日报告请求/响应模型定义
# =============================================================================

"""Daily report Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# 响应模型
# -----------------------------------------------------------------------------

class DailyReportResponse(BaseModel):
    """Daily report basic response."""

    id: int
    report_date: date
    category: str
    category_name: str
    title: str
    article_count: int
    status: str
    created_at: datetime
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DailyReportDetail(DailyReportResponse):
    """Daily report detail with content."""

    content_markdown: str
    content_wechat: Optional[str] = None
    article_ids: Optional[list[int]] = None
    updated_at: datetime


class DailyReportListResponse(BaseModel):
    """Daily report list response with pagination."""

    total: int
    page: int
    page_size: int
    reports: list[DailyReportResponse]


# -----------------------------------------------------------------------------
# 请求模型
# -----------------------------------------------------------------------------

class GenerateReportRequest(BaseModel):
    """Request for generating daily reports."""

    report_date: Optional[date] = Field(
        default=None,
        description="报告日期，默认为昨天"
    )
    categories: Optional[list[str]] = Field(
        default=None,
        description="要生成的分类列表，默认使用配置中的所有分类"
    )


class GenerateReportResponse(BaseModel):
    """Response for generate report request."""

    success: bool
    message: str
    reports: list[DailyReportResponse] = []
    errors: list[str] = []


# -----------------------------------------------------------------------------
# 导出模型
# -----------------------------------------------------------------------------

class ExportResponse(BaseModel):
    """Response for exporting report."""

    id: int
    report_date: date
    category: str
    category_name: str
    title: str
    content: str
    format: str
    article_count: int


class DailyExportResponse(BaseModel):
    """Response for exporting all reports of a day."""

    report_date: date
    format: str
    total_articles: int
    categories: list[str]
    content: str
    reports: list[DailyReportResponse]
