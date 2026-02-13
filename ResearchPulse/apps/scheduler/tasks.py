"""Scheduler tasks for ResearchPulse v2."""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from settings import settings

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    return _scheduler


async def start_scheduler() -> None:
    """Start the scheduler."""
    scheduler = get_scheduler()

    # Add crawl job
    from apps.scheduler.jobs.crawl_job import run_crawl_job
    scheduler.add_job(
        run_crawl_job,
        IntervalTrigger(hours=settings.crawl_interval_hours),
        id="crawl_job",
        name="Crawl articles from all sources",
        replace_existing=True,
    )

    # Add cleanup job
    from apps.scheduler.jobs.cleanup_job import run_cleanup_job
    scheduler.add_job(
        run_cleanup_job,
        CronTrigger(hour=settings.cleanup_hour, minute=0),
        id="cleanup_job",
        name="Cleanup old articles",
        replace_existing=True,
    )

    # Add backup job
    from apps.scheduler.jobs.backup_job import run_backup_job
    scheduler.add_job(
        run_backup_job,
        CronTrigger(hour=settings.backup_hour, minute=0),
        id="backup_job",
        name="Backup articles before cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler() -> None:
    """Stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")
