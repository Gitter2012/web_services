"""Cleanup job for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from core.database import get_session
from apps.crawler.models import Article
from settings import settings

logger = logging.getLogger(__name__)


async def run_cleanup_job() -> dict:
    """Run cleanup for old articles.

    - Articles older than retention_days: mark as archived
    - Articles older than archive_days: delete (after backup)
    """
    logger.info("Starting cleanup job")
    start_time = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    archive_threshold = now - timedelta(days=settings.data_retention_days)
    delete_threshold = now - timedelta(days=settings.data_archive_days)

    results = {
        "archived": 0,
        "deleted": 0,
        "errors": [],
    }

    async with get_session() as session:
        # Archive old articles
        archive_result = await session.execute(
            update(Article)
            .where(
                Article.crawl_time < archive_threshold,
                Article.is_archived == False,
            )
            .values(is_archived=True, archived_at=now)
        )
        results["archived"] = archive_result.rowcount or 0

        # Note: Actual deletion is handled by backup job
        # Articles to delete are backed up first, then deleted

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "articles_archived": results["archived"],
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Cleanup job completed: {summary}")
    return summary
