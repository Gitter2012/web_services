from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, select

from .config import settings as crawler_settings
from .database import close_db, get_session, init_db
from .models import Article, Subscription
from .parser import fetch_and_parse_feed

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_last_run_at: Optional[str] = None
_last_error: Optional[str] = None


def get_status() -> dict:
    return {
        "last_run_at": _last_run_at,
        "last_error": _last_error,
    }


async def _crawl_all_feeds() -> dict:
    """Fetch all active RSS subscriptions and store new articles."""
    global _last_run_at, _last_error

    try:
        async with get_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.is_active == True)  # noqa: E712
            )
            subs = result.scalars().all()

        new_count = 0
        for sub in subs:
            articles = await fetch_and_parse_feed(
                rss_url=sub.rss_url,
                account_name=sub.account_name,
                delay=crawler_settings.http_delay_base,
                jitter=crawler_settings.http_delay_jitter,
                timeout=crawler_settings.http_timeout,
            )
            async with get_session() as session:
                for article_data in articles:
                    # Deduplication by content_url
                    existing = await session.execute(
                        select(Article.id).where(
                            Article.content_url == article_data["content_url"]
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue
                    article = Article(**article_data)
                    session.add(article)
                    new_count += 1

        _last_run_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        logger.info("WeChat crawl finished", extra={"new_articles": new_count})

    except Exception as exc:
        _last_error = str(exc)
        logger.exception("WeChat crawl failed")

    return get_status()


async def _cleanup_old_articles() -> None:
    """Remove articles older than retention_days."""
    if crawler_settings.retention_days <= 0:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=crawler_settings.retention_days)
    async with get_session() as session:
        result = await session.execute(
            delete(Article).where(Article.crawl_time < cutoff)
        )
        deleted = result.rowcount
        if deleted:
            logger.info("Cleaned up old articles", extra={"deleted": deleted})


def _run_crawl_sync() -> None:
    """Synchronous wrapper for scheduler."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_crawl_all_feeds())
        loop.run_until_complete(_cleanup_old_articles())
    finally:
        loop.close()


async def run_crawl() -> dict:
    """Public async entry point for manual trigger."""
    result = await _crawl_all_feeds()
    await _cleanup_old_articles()
    return result


def _build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=crawler_settings.schedule_timezone)
    # Parse cron expression: "minute hour day month day_of_week"
    parts = crawler_settings.schedule_cron.split()
    if len(parts) == 5:
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=crawler_settings.schedule_timezone,
        )
    else:
        trigger = CronTrigger(hour="*/2", timezone=crawler_settings.schedule_timezone)
    scheduler.add_job(_run_crawl_sync, trigger, id="wechat_crawl", replace_existing=True)
    return scheduler


async def start_scheduler() -> None:
    global _scheduler
    await init_db()
    if _scheduler and _scheduler.running:
        return
    _scheduler = _build_scheduler()
    _scheduler.start()
    logger.info("WeChat crawler scheduler started")


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    await close_db()
    logger.info("WeChat crawler scheduler stopped")


async def run_crawl_on_startup() -> None:
    if not crawler_settings.run_on_startup:
        return
    logger.info("WeChat startup crawl triggered")

    def _startup():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_crawl_all_feeds())
        finally:
            loop.close()

    thread = threading.Thread(target=_startup, name="wechat-startup-crawl", daemon=True)
    thread.start()
