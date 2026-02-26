# =============================================================================
# 模块: apps/daily_report/formatters
# 功能: 报告格式化器
# =============================================================================

"""Report formatters."""

from apps.daily_report.formatters.base import BaseFormatter
from apps.daily_report.formatters.wechat import WeChatFormatter

__all__ = [
    "BaseFormatter",
    "WeChatFormatter",
]
