from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def today_str(timezone_name: str | None = None) -> str:
    tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    return datetime.now(tz).date().isoformat()


def utc_today_str() -> str:
    return today_str("UTC")


def window_dates(base_date: str, days: int) -> set[str]:
    if not base_date:
        return set()
    try:
        parsed = datetime.strptime(base_date, "%Y-%m-%d").date()
    except ValueError:
        return {base_date}
    window_days = max(int(days), 1)
    return {(parsed - timedelta(days=offset)).isoformat() for offset in range(window_days)}
