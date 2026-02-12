from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from html import unescape

import feedparser

from common.http import get_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Image caching – download images during crawl to local storage
# ---------------------------------------------------------------------------

_IMAGE_CACHE_DIR = Path(os.environ.get(
    "WECHAT_IMAGE_CACHE_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "wechat" / "images"),
))


def _ensure_image_dir() -> Path:
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _IMAGE_CACHE_DIR


def _url_to_cache_filename(url: str) -> str:
    """Generate a deterministic filename from a URL."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    parsed = urlparse(url)
    path = parsed.path
    ext = Path(path).suffix.lower() if path else ""
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"):
        ext = ".jpg"  # default extension
    return f"{url_hash}{ext}"


def _download_image_sync(url: str, referer: str = "") -> Optional[str]:
    """Download image and return local filename, or None on failure."""
    if not url or not url.startswith(("http://", "https://")):
        return None

    filename = _url_to_cache_filename(url)
    cache_dir = _ensure_image_dir()
    local_path = cache_dir / filename

    # Already cached
    if local_path.exists() and local_path.stat().st_size > 0:
        return filename

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not referer:
        # Derive a plausible site Referer – CDN hosts like image.example.com
        # often require Referer from the main site (www.example.com).
        _CDN_PREFIXES = ("image.", "img.", "static.", "assets.", "cdn.", "media.", "res.", "pic.")
        site_host = host
        for pfx in _CDN_PREFIXES:
            if host.startswith(pfx):
                site_host = "www." + host[len(pfx):]
                break
        referer = f"{parsed.scheme}://{site_host}/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    try:
        import requests as _req
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = _req.get(url, headers=headers, timeout=15, verify=False,
                            allow_redirects=True)
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ("image" in ct or len(resp.content) > 1000):
            local_path.write_bytes(resp.content)
            return filename
        else:
            logger.debug("Image download failed: %s -> HTTP %d (%s)", url[:80], resp.status_code, ct)
            return None
    except Exception:
        logger.debug("Image download error: %s", url[:80], exc_info=True)
        return None


def _cache_images_in_html(html: str, referer: str = "") -> str:
    """Rewrite img src URLs in HTML to use locally cached files."""
    if not html:
        return html

    def _replace_img(m: re.Match) -> str:
        src = m.group(1)
        if not src.startswith(("http://", "https://")):
            return m.group(0)
        filename = _download_image_sync(src, referer=referer)
        if filename:
            new_src = f"/wechat/ui/api/imgcache/{filename}"
            return m.group(0).replace(src, new_src)
        return m.group(0)

    return re.sub(r'<img[^>]+src=["\']([^"\'>]+)["\']', _replace_img, html)


def _cache_cover_image(url: str, referer: str = "") -> str:
    """Download cover image and return cached URL path, or original URL."""
    if not url:
        return url
    filename = _download_image_sync(url, referer=referer)
    if filename:
        return f"/wechat/ui/api/imgcache/{filename}"
    return url


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


def _extract_account_name(feed: feedparser.FeedParserDict) -> str:
    """Extract WeChat account name from feed title or channel info."""
    title = feed.feed.get("title", "")
    # Common patterns: "AccountName - WeChat" or just account name
    if " - " in title:
        return title.split(" - ")[0].strip()
    return title.strip()


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_content_html(entry: feedparser.FeedParserDict) -> str:
    """Extract full HTML content from content:encoded or content field."""
    # feedparser stores <content:encoded> in entry.content list
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


def _fix_escaped_cdata(xml_text: str) -> str:
    """Fix RSS feeds where CDATA markers are HTML-entity-escaped.

    Some feeds (e.g. jiqizhixin.com) emit:
      <description>&lt;![CDATA[...]]&gt;</description>
    instead of:
      <description><![CDATA[...]]></description>

    This function decodes such escaped CDATA blocks so that feedparser
    can correctly extract the content.
    """
    # Pattern: &lt;![CDATA[ ... ]]&gt;  within XML tags
    if "&lt;![CDATA[" not in xml_text:
        return xml_text

    def _replace_cdata(m: re.Match) -> str:
        tag = m.group(1)  # e.g. "description" or "content:encoded"
        inner = m.group(2)
        # The inner part has HTML-escaped content, unescape it once
        inner_unescaped = unescape(inner)
        return f"<{tag}><![CDATA[{inner_unescaped}]]></{tag}>"

    # Match tags containing escaped CDATA
    pattern = r"<(description|content:encoded)>\s*&lt;!\[CDATA\[(.*?)\]\]&gt;\s*</\1>"
    return re.sub(pattern, _replace_cdata, xml_text, flags=re.DOTALL)


def parse_rss_feed(
    feed_text: str,
    rss_url: str,
    override_account_name: str = "",
) -> List[Dict]:
    """Parse RSS feed text and return list of article dicts.

    Returns list of dicts with keys matching Article model fields.
    Handles both standard RSS and feeds with <content:encoded>.
    """
    # Fix feeds with double-escaped CDATA blocks
    feed_text = _fix_escaped_cdata(feed_text)

    feed = feedparser.parse(feed_text)
    account_name = override_account_name or _extract_account_name(feed)
    articles = []

    for entry in feed.entries:
        content_url = entry.get("link", "").strip()
        if not content_url:
            continue

        title = entry.get("title", "").strip()
        author = entry.get("author", "").strip()

        # --- Digest extraction ---
        # 1. Try <description> / summary first
        digest = entry.get("summary", "").strip()
        if digest:
            digest = _strip_html(digest)

        # 2. If empty, extract leading text from <content:encoded>
        content_html = _extract_content_html(entry)
        if not digest and content_html:
            plain_text = _strip_html(content_html)
            # Take first 300 chars as digest
            digest = plain_text[:300].rstrip()
            if len(plain_text) > 300:
                digest += "..."

        pub_date = _parse_pub_date(
            entry.get("published", "") or entry.get("updated", "")
        )

        # --- Cover image extraction ---
        cover_url = ""
        # 1. Try media:content / media:thumbnail
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
        # 2. Fallback: extract first image from content HTML
        if not cover_url:
            cover_url = _extract_first_image(content_html)

        # --- Store raw content HTML for detail view ---
        raw_html = content_html if content_html else ""

        # --- Cache images locally during crawl ---
        feed_site = feed.feed.get("link", rss_url)
        cover_url = _cache_cover_image(cover_url, referer=feed_site)
        raw_html = _cache_images_in_html(raw_html, referer=feed_site) if raw_html else ""

        articles.append(
            {
                "title": title,
                "author": author or account_name,
                "account_name": account_name,
                "account_id": "",
                "digest": digest,
                "content_url": content_url,
                "cover_image_url": cover_url,
                "publish_time": pub_date,
                "source_type": "rss",
                "raw_content_html": raw_html,
            }
        )

    return articles


async def fetch_and_parse_feed(
    rss_url: str,
    account_name: str = "",
    delay: float = 0.0,
    jitter: float = 0.0,
    timeout: float = 15.0,
) -> List[Dict]:
    """Fetch RSS feed URL and parse articles."""
    import asyncio

    try:
        feed_text = await asyncio.to_thread(
            get_text,
            rss_url,
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
            rss_url,
        )
        return []
    return parse_rss_feed(feed_text, rss_url, override_account_name=account_name)
