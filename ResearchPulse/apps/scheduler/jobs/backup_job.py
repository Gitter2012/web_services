"""Backup job for ResearchPulse v2."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from core.database import get_session
from apps.crawler.models import Article, BackupRecord
from settings import settings

logger = logging.getLogger(__name__)


async def run_backup_job() -> dict:
    """Run backup for articles to be deleted.

    This job:
    1. Finds articles older than archive_days
    2. Exports them to JSON
    3. Records the backup
    4. Deletes the articles
    """
    if not settings.backup_enabled:
        logger.info("Backup is disabled, skipping")
        return {"status": "skipped", "reason": "backup_disabled"}

    logger.info("Starting backup job")
    start_time = datetime.now(timezone.utc)

    delete_threshold = datetime.now(timezone.utc) - timedelta(days=settings.data_archive_days)

    results = {
        "backed_up": 0,
        "deleted": 0,
        "backup_file": None,
        "errors": [],
    }

    async with get_session() as session:
        # Find articles to delete
        result = await session.execute(
            select(Article).where(Article.crawl_time < delete_threshold)
        )
        articles = result.scalars().all()

        if not articles:
            logger.info("No articles to backup")
            return {
                "status": "completed",
                "backed_up": 0,
                "deleted": 0,
            }

        # Create backup directory
        backup_dir = settings.backup_dir
        if not backup_dir.is_absolute():
            backup_dir = settings.data_dir / backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create backup file
        backup_date = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"articles_{backup_date}.json"

        # Export articles
        articles_data = []
        for article in articles:
            articles_data.append({
                "id": article.id,
                "source_type": article.source_type,
                "source_id": article.source_id,
                "external_id": article.external_id,
                "title": article.title,
                "url": article.url,
                "author": article.author,
                "summary": article.summary,
                "content": article.content,
                "category": article.category,
                "tags": article.tags,
                "publish_time": article.publish_time.isoformat() if article.publish_time else None,
                "crawl_time": article.crawl_time.isoformat() if article.crawl_time else None,
            })

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump({
                "backup_date": backup_date,
                "article_count": len(articles_data),
                "articles": articles_data,
            }, f, ensure_ascii=False, indent=2)

        results["backed_up"] = len(articles_data)
        results["backup_file"] = str(backup_file)
        backup_size = backup_file.stat().st_size

        # Record backup
        backup_record = BackupRecord(
            backup_date=datetime.now(timezone.utc),
            backup_file=str(backup_file),
            backup_size=backup_size,
            article_count=len(articles_data),
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        session.add(backup_record)

        # Delete articles
        for article in articles:
            await session.delete(article)

        results["deleted"] = len(articles)

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "articles_backed_up": results["backed_up"],
        "articles_deleted": results["deleted"],
        "backup_file": results["backup_file"],
        "backup_size_bytes": backup_size,
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Backup job completed: {summary}")
    return summary
