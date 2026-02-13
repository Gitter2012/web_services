"""Base crawler class for ResearchPulse v2."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from apps.crawler.models import Article

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """Abstract base class for all crawlers.

    Subclasses must implement:
    - fetch(): Fetch raw data from source
    - parse(): Parse raw data into article dictionaries
    """

    source_type: str  # 'arxiv', 'rss', 'wechat'
    source_id: str  # Category code, feed ID, or account name

    def __init__(self, source_id: str):
        self.source_id = source_id
        self.logger = logging.getLogger(f"{__name__}.{self.source_type}.{source_id}")

    @abstractmethod
    async def fetch(self) -> Any:
        """Fetch raw data from the source.

        Returns:
            Raw data from the source (could be str, dict, list, etc.)
        """
        pass

    @abstractmethod
    async def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Parse raw data into article dictionaries.

        Args:
            raw_data: Raw data from fetch()

        Returns:
            List of article dictionaries with keys matching Article model
        """
        pass

    async def save(self, articles: List[Dict[str, Any]], session: AsyncSession) -> int:
        """Save articles to database with deduplication.

        Args:
            articles: List of article dictionaries
            session: Database session

        Returns:
            Number of new articles saved
        """
        if not articles:
            return 0

        saved_count = 0
        for article_data in articles:
            try:
                # Use insert ... on duplicate key update for deduplication
                external_id = article_data.get("external_id", "")
                url = article_data.get("url", "")

                # Check if article already exists
                stmt = select(Article).where(
                    Article.source_type == self.source_type,
                    Article.source_id == self.source_id,
                    Article.external_id == external_id,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing article
                    for key, value in article_data.items():
                        if hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new article
                    article = Article(
                        source_type=self.source_type,
                        source_id=self.source_id,
                        crawl_time=datetime.now(timezone.utc),
                        **article_data,
                    )
                    session.add(article)
                    saved_count += 1

            except Exception as e:
                self.logger.error(f"Failed to save article: {e}")
                continue

        await session.flush()
        return saved_count

    async def run(self) -> Dict[str, Any]:
        """Execute the complete crawl process.

        Returns:
            Dictionary with crawl results
        """
        start_time = datetime.now(timezone.utc)
        self.logger.info(f"Starting crawl for {self.source_type}:{self.source_id}")

        try:
            # Fetch raw data
            raw_data = await self.fetch()

            # Parse into articles
            articles = await self.parse(raw_data)

            # Save to database
            from core.database import get_session_factory
            factory = get_session_factory()
            async with factory() as session:
                saved_count = await self.save(articles, session)
                await session.commit()

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            result = {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "fetched_count": len(articles),
                "saved_count": saved_count,
                "duration_seconds": duration,
                "status": "success",
                "timestamp": end_time.isoformat(),
            }

            self.logger.info(f"Crawl completed: {saved_count} new articles in {duration:.2f}s")
            return result

        except Exception as e:
            self.logger.exception(f"Crawl failed: {e}")
            return {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def delay(self, base: float = 3.0, jitter: float = 1.0) -> None:
        """Add a delay with jitter to avoid rate limiting."""
        import random

        delay_time = base + random.uniform(0, jitter)
        await asyncio.sleep(delay_time)
