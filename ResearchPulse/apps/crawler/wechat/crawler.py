"""WeChat crawler for ResearchPulse v2.

This module implements a WeChat official account article crawler.
It fetches articles from RSS feeds that aggregate WeChat public account content.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import feedparser

from apps.crawler.base import BaseCrawler
from common.http import get_text, _get_user_agent, _build_headers

logger = logging.getLogger(__name__)

# Image cache directory for downloaded images
_IMAGE_CACHE_DIR = Path("./data/wechat/images")


def _ensure_image_dir() -> Path:
    """Ensure image cache directory exists."""
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _IMAGE_CACHE_DIR


def _url_to_cache_filename(url: str) -> str:
    """Generate a deterministic filename from a URL."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    parsed = urlparse(url)
    path = parsed.path
    ext = Path(path).suffix.lower() if path else ""
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"):
        ext = ".jpg"
    return f"{url_hash}{ext}"


def _download_image(url: str, referer: str = "", timeout: float = 15.0) -> Optional[str]:
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
        # Derive a plausible site Referer
        _CDN_PREFIXES = ("image.", "img.", "static.", "assets.", "cdn.", "media.", "res.", "pic.", "mmbiz.")
        site_host = host
        for pfx in _CDN_PREFIXES:
            if host.startswith(pfx):
                site_host = "www." + host[len(pfx):]
                break
        referer = f"{parsed.scheme}://{site_host}/"

    try:
        import requests
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(
                url,
                headers={
                    "User-Agent": _get_user_agent(),
                    "Referer": referer,
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
                timeout=timeout,
                verify=False,
                allow_redirects=True,
            )

        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ("image" in ct or len(resp.content) > 1000):
            local_path.write_bytes(resp.content)
            return filename
        else:
            logger.debug(f"Image download failed: {url[:80]} -> HTTP {resp.status_code}")
            return None
    except Exception as e:
        logger.debug(f"Image download error: {url[:80]}: {e}")
        return None


def _parse_wechat_rss_entry(entry: feedparser.FeedParserDict, account_name: str) -> Dict[str, Any]:
    """Parse a single RSS entry into article dict."""
    # Extract title
    title = entry.get("title", "")
    if not title:
        return {}

    # Clean title (remove HTML)
    title = re.sub(r"<[^>]+>", "", title)
    title = unescape(title).strip()

    # Extract URL
    url = entry.get("link", "")
    
    # Extract WeChat specific URL if available
    content = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
    
    # Extract cover image from content
    cover_url = ""
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if img_match:
        cover_url = img_match.group(1)
        # Download and cache image
        local_img = _download_image(cover_url)
        if local_img:
            cover_url = f"/data/wechat/images/{local_img}"

    # Extract digest/summary
    digest = entry.get("summary", "")
    digest = re.sub(r"<[^>]+>", " ", digest)
    digest = unescape(digest)
    digest = " ".join(digest.split()).strip()
    if len(digest) > 300:
        digest = digest[:297] + "..."

    # Extract author
    author = ""
    if entry.get("author"):
        author = entry.get("author", "")
    elif "author" in entry:
        author = entry.get("author", "")

    # Parse publish time
    publish_time = None
    for time_field in ["published", "pubDate", "updated"]:
        if entry.get(time_field):
            try:
                if isinstance(entry[time_field], str):
                    publish_time = parsedate_to_datetime(entry[time_field])
                else:
                    publish_time = datetime.fromtimestamp(
                        time.mktime(entry[time_field]),
                        tz=timezone.utc
                    )
                break
            except Exception:
                pass

    # Generate external ID from URL
    external_id = ""
    if url:
        # Try to extract sn parameter from WeChat URL
        sn_match = re.search(r'sn=([a-zA-Z0-9]+)', url)
        if sn_match:
            external_id = sn_match.group(1)
        else:
            external_id = hashlib.md5(url.encode()).hexdigest()[:16]

    return {
        "external_id": external_id,
        "title": title,
        "url": url,
        "author": author,
        "summary": digest,
        "content": content,
        "cover_image_url": cover_url,
        "wechat_account_name": account_name,
        "wechat_digest": digest,
        "publish_time": publish_time,
    }


class WechatCrawler(BaseCrawler):
    """Crawler for WeChat official account articles via RSS feeds."""

    source_type = "wechat"

    # Default WeChat RSS feed services
    DEFAULT_RSS_SERVICES = [
        # RSSHub-based services (commonly used)
        "https://rsshub.app/wechat/mp/msgalbum/{account}",
        # Alternative services can be added here
    ]

    def __init__(
        self,
        account_name: str,
        account_id: str = "",
        rss_url: Optional[str] = None,
        timeout: float = 30.0,
        max_articles: int = 50,
        download_images: bool = True,
    ):
        super().__init__(account_name)
        self.account_name = account_name
        self.account_id = account_id or account_name
        self.rss_url = rss_url
        self.timeout = timeout
        self.max_articles = max_articles
        self.download_images = download_images

    async def fetch(self) -> str:
        """Fetch RSS feed content."""
        if not self.rss_url:
            # Try to construct RSS URL from account name
            self.rss_url = f"https://rsshub.app/wechat/mp/msgalbum/{self.account_id}"

        try:
            self.logger.info(f"Fetching WeChat RSS: {self.rss_url}")
            feed_text = get_text(
                self.rss_url,
                timeout=self.timeout,
                retries=3,
                backoff=2.0,
                delay=1.0,
                jitter=0.5,
            )
            return feed_text
        except Exception as e:
            self.logger.error(f"WeChat RSS fetch failed: {e}")
            raise

    async def parse(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse RSS feed into article dictionaries."""
        feed = feedparser.parse(raw_data)
        
        if feed.bozo and not feed.entries:
            self.logger.warning(f"RSS parse error: {feed.bozo_exception}")
            return []

        articles = []
        seen_ids = set()

        for entry in feed.entries[:self.max_articles]:
            article = _parse_wechat_rss_entry(entry, self.account_name)
            if not article or not article.get("title"):
                continue

            # Skip duplicates
            ext_id = article.get("external_id", "")
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            articles.append(article)

        self.logger.info(f"Parsed {len(articles)} WeChat articles from {self.account_name}")
        return articles

    async def run(self) -> Dict[str, Any]:
        """Run the crawler and return results."""
        try:
            raw_data = await self.fetch()
            articles = await self.parse(raw_data)
            
            return {
                "account": self.account_name,
                "articles": articles,
                "count": len(articles),
                "saved_count": 0,  # Will be filled by caller
            }
        except Exception as e:
            self.logger.error(f"WeChat crawler failed: {e}")
            return {
                "account": self.account_name,
                "articles": [],
                "count": 0,
                "saved_count": 0,
                "error": str(e),
            }


class WechatMultiCrawler:
    """Crawler for multiple WeChat accounts."""

    def __init__(
        self,
        accounts: List[Dict[str, str]],
        timeout: float = 30.0,
        delay_between_accounts: float = 3.0,
    ):
        """
        Args:
            accounts: List of dicts with 'name', 'id', and optional 'rss_url'
            timeout: Request timeout
            delay_between_accounts: Delay between crawling different accounts
        """
        self.accounts = accounts
        self.timeout = timeout
        self.delay = delay_between_accounts

    async def crawl_all(self) -> Dict[str, Any]:
        """Crawl all configured accounts."""
        import asyncio

        results = {
            "total_accounts": len(self.accounts),
            "successful": 0,
            "failed": 0,
            "total_articles": 0,
            "accounts": [],
        }

        for i, account in enumerate(self.accounts):
            name = account.get("name", "")
            account_id = account.get("id", name)
            rss_url = account.get("rss_url")

            self.logger.info(f"Crawling WeChat account [{i+1}/{len(self.accounts)}]: {name}")

            crawler = WechatCrawler(
                account_name=name,
                account_id=account_id,
                rss_url=rss_url,
                timeout=self.timeout,
            )

            try:
                result = await crawler.run()
                results["accounts"].append(result)
                results["total_articles"] += result.get("count", 0)
                results["successful"] += 1
            except Exception as e:
                self.logger.error(f"Failed to crawl {name}: {e}")
                results["accounts"].append({
                    "account": name,
                    "error": str(e),
                    "count": 0,
                })
                results["failed"] += 1

            # Delay between accounts
            if i < len(self.accounts) - 1:
                await asyncio.sleep(self.delay)

        return results
