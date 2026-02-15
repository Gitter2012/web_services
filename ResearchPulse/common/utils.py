# =============================================================================
# 模块: common/utils.py
# 功能: 通用日期时间工具函数集
# 架构角色: 作为基础工具层，提供日期和时间相关的通用工具函数。
#   被多个模块使用，包括爬虫（确定爬取日期范围）、调度器（时间计算）、
#   数据保留策略（计算过期日期）等。
#
# 设计决策:
#   - 所有时间操作默认使用 UTC 时区，避免时区混乱
#   - 支持通过时区名称字符串指定本地时区（使用 zoneinfo 标准库）
#   - 函数保持简洁无状态，便于测试和复用
# =============================================================================
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Return the current UTC time.

    返回带有 UTC 时区信息的 datetime 对象。
    建议使用该函数代替 ``datetime.utcnow()``。

    Returns:
        datetime: Current UTC datetime with timezone info.
    """
    return datetime.now(timezone.utc)


def today_str(timezone_name: str | None = None) -> str:
    """Return today's date string in ISO format.

    可指定时区名称获取该时区的当天日期。
    不指定时区时默认使用 UTC。

    Args:
        timezone_name: Optional timezone name (e.g. "Asia/Shanghai").

    Returns:
        str: ISO date string, e.g. "2024-01-15".
    """
    tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    return datetime.now(tz).date().isoformat()


def utc_today_str() -> str:
    """Return today's UTC date string.

    等价于 ``today_str("UTC")``。

    Returns:
        str: ISO UTC date string.
    """
    return today_str("UTC")


def window_dates(base_date: str, days: int) -> set[str]:
    """Generate a date window set from a base date.

    从 base_date 开始向前回溯 days 天，返回这些天的日期字符串集合。

    Args:
        base_date: Base date string in "YYYY-MM-DD".
        days: Window size in days (minimum 1).

    Returns:
        set[str]: Date strings in ISO format.
    """
    if not base_date:
        return set()
    try:
        parsed = datetime.strptime(base_date, "%Y-%m-%d").date()
    except ValueError:
        # 日期格式无法解析时，返回仅含原始字符串的集合（兼容性考虑）
        return {base_date}
    # 至少回溯 1 天
    window_days = max(int(days), 1)
    # 生成从 base_date 向前 window_days 天的日期集合
    return {(parsed - timedelta(days=offset)).isoformat() for offset in range(window_days)}
