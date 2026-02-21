"""AIGC article writer — saves AI-generated summary articles to the articles table.

Each AI analysis module (event clustering, topic discovery, action extraction,
report generation) can call ``save_aigc_article`` after completing its work.
The function uses the existing ``(source_type, source_id, external_id)`` unique
constraint for idempotency so that repeated runs never create duplicate records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article

logger = logging.getLogger(__name__)

# Mapping from internal source_id to human-readable names
SOURCE_NAMES = {
    "event_clustering": "事件聚类日报",
    "topic_radar": "话题趋势日报",
    "action_items": "行动建议日报",
    "report": "报告中心摘要",
}


async def save_aigc_article(
    session: AsyncSession,
    *,
    source_id: str,
    external_id: str,
    title: str,
    content: str,
    summary: Optional[str] = None,
    category: str = "AIGC",
    tags: Optional[list] = None,
) -> Optional[Article]:
    """Save an AI-generated summary as an Article with source_type='aigc'.

    Args:
        session: Active async DB session (caller manages commit).
        source_id: Module identifier, e.g. "event_clustering", "topic_radar",
                   "action_items", "report".
        external_id: Idempotency key, e.g. "event_2026-02-21",
                     "report_weekly_2026-02-17".
        title: Article title.
        content: Markdown-formatted article body.
        summary: Short summary (defaults to first 200 chars of content).
        category: Article category (default "AIGC").
        tags: Optional list of tags.

    Returns:
        The created Article, or None if a duplicate already exists.
    """
    # Idempotency check — skip if an article with the same key already exists
    existing = await session.execute(
        select(Article.id).where(
            Article.source_type == "aigc",
            Article.source_id == source_id,
            Article.external_id == external_id,
        ).limit(1)
    )
    if existing.scalar():
        logger.debug(
            "AIGC article already exists: source_id=%s external_id=%s, skipping",
            source_id,
            external_id,
        )
        return None

    now = datetime.now(timezone.utc)
    article = Article(
        source_type="aigc",
        source_id=source_id,
        external_id=external_id,
        title=title,
        url="",
        author="ResearchPulse AI",
        summary=summary or content[:200],
        content=content,
        category=category,
        tags=tags or [],
        publish_time=now,
        crawl_time=now,
        is_archived=False,
        # Mark as AI-processed to prevent the AI pipeline from re-processing
        ai_processed_at=now,
        processing_method="aigc",
    )
    session.add(article)
    logger.info(
        "Saved AIGC article: source_id=%s external_id=%s title=%s",
        source_id,
        external_id,
        title,
    )
    return article
