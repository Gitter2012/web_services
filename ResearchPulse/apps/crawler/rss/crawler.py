"""RSS crawler for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import feedparser

from apps.crawler.base import BaseCrawler
from common.http import get_text

logger = logging.getLogger(__name__)


class RssCrawler(BaseCrawler):
    """Crawler for RSS/Atom feeds."""

    source_type = "rss"

    def __init__(
        self,
        feed_id: str,
        feed_url: str,
        timeout: float = 30.0,
    ):
        super().__init__(feed_id)
        self.feed_id = feed_id
        self.feed_url = feed_url
        self.timeout = timeout

    async def fetch(self) -> str:
        """Fetch RSS feed content."""
        try:
            feed_text = get_text(
                self.feed_url,
                timeout=self.timeout,
                retries=3,
                backoff=1.0,
            )
            return feed_text
        except Exception as e:
            self.logger.warning(f"RSS fetch failed for {self.feed_url}: {e}")
            raise

    async def parse(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse RSS feed into article dictionaries."""
        feed = feedparser.parse(raw_data)

        articles = []
        for entry in feed.entries:
            article = self._parse_entry(entry)
            if article:
                articles.append(article)

        return articles

    def _parse_entry(self, entry: feedparser.FeedParserDict) -> Dict[str, Any] | None:
        """Parse a single RSS entry into an article dictionary."""
        # Extract title
        title = entry.get("title", "")
        if not title:
            return None

        # Extract URL
        url = ""
        if entry.get("link"):
            url = entry.link
        elif entry.get("links"):
            for link in entry.links:
                if link.get("type", "").startswith("text/html"):
                    url = link.get("href", "")
                    break
            if not url and entry.links:
                url = entry.links[0].get("href", "")

        # Extract author
        author = ""
        if entry.get("author"):
            author = entry.author
        elif entry.get("authors"):
            author = ", ".join(a.get("name", "") for a in entry.authors)

        # Extract summary/content
        summary = entry.get("summary", "") or entry.get("description", "")
        content = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else summary

        # Extract publish time
        publish_time = None
        if entry.get("published_parsed"):
            try:
                publish_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
        elif entry.get("published"):
            try:
                from email.utils import parsedate_to_datetime
                publish_time = parsedate_to_datetime(entry.published)
            except (ValueError, TypeError):
                pass

        # Extract cover image
        cover_image_url = ""
        if entry.get("media_content"):
            for media in entry.media_content:
                if media.get("type", "").startswith("image/"):
                    cover_image_url = media.get("url", "")
                    break
        elif entry.get("enclosures"):
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image/"):
                    cover_image_url = enc.get("href", "")
                    break

        # Extract tags
        tags = []
        if entry.get("tags"):
            tags = [tag.get("term", "") for tag in entry.tags if tag.get("term")]

        # Generate external_id (use link or guid)
        external_id = entry.get("id", "") or entry.get("guid", "") or url

        return {
            "external_id": external_id,
            "title": title,
            "url": url,
            "author": author,
            "summary": summary,
            "content": content,
            "cover_image_url": cover_image_url,
            "tags": tags,
            "publish_time": publish_time,
        }
