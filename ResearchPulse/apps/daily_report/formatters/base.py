# =============================================================================
# 模块: apps/daily_report/formatters/base.py
# 功能: 报告格式化器基类
# =============================================================================

"""Base formatter for daily reports."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseFormatter(ABC):
    """Abstract base class for report formatters.

    报告格式化器抽象基类。
    """

    @abstractmethod
    def format(self, content: str) -> str:
        """Format the content.

        格式化内容。

        Args:
            content: Input content (usually Markdown).

        Returns:
            Formatted content string.
        """
        ...
