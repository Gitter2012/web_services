# =============================================================================
# 模块: apps/daily_report/schemas
# 功能: 每日报告请求/响应模型
# =============================================================================

"""Daily report schemas."""

from apps.daily_report.schemas.report import (
    DailyReportResponse,
    DailyReportListResponse,
    DailyReportDetail,
    GenerateReportRequest,
    GenerateReportResponse,
    ExportResponse,
    DailyExportResponse,
)

__all__ = [
    "DailyReportResponse",
    "DailyReportListResponse",
    "DailyReportDetail",
    "GenerateReportRequest",
    "GenerateReportResponse",
    "ExportResponse",
    "DailyExportResponse",
]
