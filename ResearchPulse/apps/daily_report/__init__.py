# =============================================================================
# 模块: apps/daily_report
# 功能: 每日 arXiv 报告生成模块
# 架构角色: 负责每日从爬取的文章中生成格式化的报告，支持微信公众号发布格式
# =============================================================================

"""Daily arXiv report generation module."""

from apps.daily_report.service import DailyReportService
from apps.daily_report.generator import ReportGenerator
from apps.daily_report.formatters.wechat import WeChatFormatter

__all__ = [
    "DailyReportService",
    "ReportGenerator",
    "WeChatFormatter",
]
