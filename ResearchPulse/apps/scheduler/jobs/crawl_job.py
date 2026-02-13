"""Crawl job for ResearchPulse v2."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from core.database import get_session
from apps.crawler.models import ArxivCategory, RssFeed, WechatAccount
from apps.crawler.arxiv import ArxivCrawler
from apps.crawler.rss import RssCrawler
from settings import settings

logger = logging.getLogger(__name__)


async def run_crawl_job() -> dict:
    """Run crawl for all active sources."""
    logger.info("Starting crawl job")
    start_time = datetime.now(timezone.utc)
    results = {
        "arxiv": [],
        "rss": [],
        "wechat": [],
        "errors": [],
        "total_articles": 0,
    }

    async with get_session() as session:
        # Crawl arxiv categories
        arxiv_result = await session.execute(
            select(ArxivCategory).where(ArxivCategory.is_active == True)
        )
        arxiv_categories = arxiv_result.scalars().all()

        for category in arxiv_categories:
            try:
                crawler = ArxivCrawler(
                    category=category.code,
                    max_results=50,
                    delay_base=settings.arxiv_delay_base,
                )
                result = await crawler.run()
                results["arxiv"].append(result)
                results["total_articles"] += result.get("saved_count", 0)
                await asyncio.sleep(2)  # Delay between categories
            except Exception as e:
                logger.error(f"Arxiv crawl failed for {category.code}: {e}")
                results["errors"].append(f"arxiv:{category.code}: {str(e)}")

        # Crawl RSS feeds
        rss_result = await session.execute(
            select(RssFeed).where(RssFeed.is_active == True)
        )
        rss_feeds = rss_result.scalars().all()

        for feed in rss_feeds:
            try:
                crawler = RssCrawler(
                    feed_id=str(feed.id),
                    feed_url=feed.feed_url,
                )
                result = await crawler.run()
                results["rss"].append(result)
                results["total_articles"] += result.get("saved_count", 0)
                await asyncio.sleep(1)  # Delay between feeds
            except Exception as e:
                logger.error(f"RSS crawl failed for {feed.title}: {e}")
                results["errors"].append(f"rss:{feed.id}: {str(e)}")

        # Update last fetched time for successful feeds
        for feed in rss_feeds:
            feed.last_fetched_at = datetime.now(timezone.utc)

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "arxiv_count": len(results["arxiv"]),
        "rss_count": len(results["rss"]),
        "error_count": len(results["errors"]),
        "total_articles": results["total_articles"],
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Crawl job completed: {summary}")

    # Send notifications after successful crawl
    if settings.email_enabled and results["total_articles"] > 0:
        try:
            from apps.scheduler.jobs.notification_job import (
                send_crawl_completion_notification,
                send_all_user_notifications,
            )

            # Send admin notification
            await send_crawl_completion_notification(summary)

            # Send user notifications (articles from today)
            notification_results = await send_all_user_notifications(
                since=start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            )
            summary["notifications"] = notification_results

        except Exception as e:
            logger.error(f"Failed to send notifications: {e}")
            results["errors"].append(f"notification: {str(e)}")

    return summary
