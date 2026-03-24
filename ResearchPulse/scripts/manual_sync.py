#!/usr/bin/env python3
"""Manual sync script: push daily reports from Pipeline A to Display B.

Usage:
    python scripts/manual_sync.py --date 2026-03-24
    python scripts/manual_sync.py --date 2026-03-24 --source-types arxiv rss
    python scripts/manual_sync.py --pending
    python scripts/manual_sync.py --pending --limit 50
    python scripts/manual_sync.py --failed
    python scripts/manual_sync.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date as date_type
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, or_

from core.database import get_session_factory
from apps.daily_report.models.daily_report import DailyReport
from apps.sync.sender_service import SyncSenderService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def sync_by_date(
    report_date: date_type,
    source_types: list[str] | None = None,
) -> None:
    """Query reports for the given date and push to Display B."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(DailyReport).where(DailyReport.report_date == report_date)
        if source_types:
            stmt = stmt.where(DailyReport.source_type.in_(source_types))
        result = await db.execute(stmt)
        reports = list(result.scalars().all())

    if not reports:
        logger.warning("No reports found for %s (source_types=%s)", report_date, source_types)
        return

    logger.info("Found %d report(s) for %s, starting sync...", len(reports), report_date)
    for r in reports:
        logger.info("  - [%s] %s (%d articles)", r.source_type, r.title[:60], r.article_count)

    sync_service = SyncSenderService()
    await sync_service.sync_all(report_date, reports)
    logger.info("Sync completed for %s.", report_date)


async def list_pending(limit: int = 20) -> None:
    """List reports with sync_status = pending or failed."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(DailyReport)
            .where(or_(
                DailyReport.sync_status == "pending",
                DailyReport.sync_status == "failed",
            ))
            .order_by(DailyReport.report_date.desc())
            .limit(limit)
        )
        reports = list(result.scalars().all())

    if not reports:
        logger.info("No pending or failed reports found.")
        return

    logger.info("Found %d pending/failed report(s):", len(reports))
    for r in reports:
        attempted = r.sync_attempted_at.strftime("%Y-%m-%d %H:%M") if r.sync_attempted_at else "never"
        logger.info(
            "  [%s] %s | %s | %s | last attempt: %s%s",
            r.sync_status.upper(),
            r.report_date,
            r.source_type,
            r.title[:50],
            attempted,
            f" | error: {r.sync_error[:80]}" if r.sync_error else "",
        )


async def retry_failed() -> None:
    """Re-sync all reports with sync_status = failed, grouped by date."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(DailyReport)
            .where(DailyReport.sync_status == "failed")
            .order_by(DailyReport.report_date.desc())
        )
        reports = list(result.scalars().all())

    if not reports:
        logger.info("No failed reports found.")
        return

    logger.info("Found %d failed report(s), retrying...", len(reports))

    # Group by report_date and sync each date
    from itertools import groupby
    key = lambda r: r.report_date
    reports.sort(key=key)
    sync_service = SyncSenderService()

    for report_date, group in groupby(reports, key=key):
        date_reports = list(group)
        logger.info("Retrying %d report(s) for %s...", len(date_reports), report_date)
        try:
            await sync_service.sync_all(report_date, date_reports)
            logger.info("  Done for %s.", report_date)
        except Exception as e:
            logger.error("  Failed for %s: %s", report_date, e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual sync tool - push daily reports from Pipeline A to Display B",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--date",
        type=str,
        metavar="YYYY-MM-DD",
        help="同步指定日期的报告",
    )
    group.add_argument(
        "--pending",
        action="store_true",
        help="列出所有待同步（pending/failed）的报告",
    )
    group.add_argument(
        "--failed",
        action="store_true",
        help="重试所有同步失败（failed）的报告",
    )

    parser.add_argument(
        "--source-types",
        nargs="+",
        metavar="TYPE",
        help="过滤数据源类型（如: arxiv rss hackernews），配合 --date 使用",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="--pending 时显示的最大条数（默认 20）",
    )

    args = parser.parse_args()

    if args.date:
        try:
            report_date = date_type.fromisoformat(args.date)
        except ValueError:
            parser.error(f"Invalid date format: {args.date!r}, expected YYYY-MM-DD")
        asyncio.run(sync_by_date(report_date, args.source_types))

    elif args.pending:
        asyncio.run(list_pending(args.limit))

    elif args.failed:
        asyncio.run(retry_failed())


if __name__ == "__main__":
    main()
