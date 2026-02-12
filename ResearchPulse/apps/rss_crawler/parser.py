from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Dict, List, Optional

import feedparser

from common.http import get_text

logger = logging.getLogger(__name__)


def _fix_escaped_cdata(xml_text: str) -> str:
    """Fix RSS feeds where CDATA markers are HTML-entity-escaped.

    Some feeds emit:
      <description>&lt;![CDATA[...]]&gt;</description>
    instead of:
      <description><![CDATA[...]]></description>

    This function decodes such escaped CDATA blocks so that feedparser
    can correctly extract the content.
    """
    if "&lt;![CDATA[" not in xml_text:
        return xml_text

    def _replace_cdata(m: re.Match) -> str:
        tag = m.group(1)
        inner = m.group(2)
        inner_unescaped = unescape(inner)
        return f"<{tag}><![CDATA[{inner_unescaped}]]></{tag}>"

    pattern = r"<(description|content:encoded)>\s*&lt;!\[CDATA\[(.*?)\]\]&gt;\s*</\1>"
    return re.sub(pattern, _replace_cdata, xml_text, flags=re.DOTALL)


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_content_html(entry: feedparser.FeedParserDict) -> str:
    """Extract full HTML content from content:encoded or content field."""
    if entry.get("content"):
        for c in entry.content:
            if c.get("value", "").strip():
                return c["value"].strip()
    return ""


def _extract_first_image(html: str) -> str:
    """Extract the first <img src="..."> URL from HTML content."""
    if not html:
        return ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    return match.group(1) if match else ""


def _parse_pub_date(value: str) -> Optional[datetime]:
    """Parse RSS pubDate or atom published to datetime."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_rss_feed(feed_text: str, feed_url: str) -> List[Dict]:
    """Parse RSS feed text and return list of article dicts.

    Returns list of dicts with keys:
        title, url, author, summary, content_html,
        cover_image_url, publish_time
    """
    feed_text = _fix_escaped_cdata(feed_text)
    feed = feedparser.parse(feed_text)
    articles: List[Dict] = []

    for entry in feed.entries:
        url = entry.get("link", "").strip()
        if not url:
            continue

        title = entry.get("title", "").strip()
        author = entry.get("author", "").strip()

        # --- Summary extraction ---
        summary = entry.get("summary", "").strip()
        if summary:
            summary = _strip_html(summary)

        content_html = _extract_content_html(entry)
        if not summary and content_html:
            plain_text = _strip_html(content_html)
            summary = plain_text[:300].rstrip()
            if len(plain_text) > 300:
                summary += "..."

        pub_date = _parse_pub_date(
            entry.get("published", "") or entry.get("updated", "")
        )

        # --- Cover image extraction ---
        cover_url = ""
        if entry.get("media_content"):
            for media in entry.media_content:
                if media.get("medium") == "image" or "image" in media.get("type", ""):
                    cover_url = media.get("url", "")
                    break
        if not cover_url and entry.get("media_thumbnail"):
            for thumb in entry.media_thumbnail:
                cover_url = thumb.get("url", "")
                if cover_url:
                    break
        if not cover_url:
            cover_url = _extract_first_image(content_html)

        articles.append(
            {
                "title": title,
                "url": url,
                "author": author,
                "summary": summary,
                "content_html": content_html,
                "cover_image_url": cover_url,
                "publish_time": pub_date,
            }
        )

    return articles


async def fetch_and_parse_feed(
    feed_url: str,
    timeout: float = 15.0,
    delay: float = 0.0,
    jitter: float = 0.0,
) -> List[Dict]:
    """Fetch RSS feed URL and parse articles."""
    import asyncio

    try:
        feed_text = await asyncio.to_thread(
            get_text,
            feed_url,
            timeout=timeout,
            retries=2,
            backoff=1.0,
            delay=delay,
            jitter=jitter,
        )
    except Exception as exc:
        logger.warning(
            "RSS feed fetch failed: %s – %s (url=%s)",
            type(exc).__name__,
            exc,
            feed_url,
        )
        return []
    return parse_rss_feed(feed_text, feed_url)
