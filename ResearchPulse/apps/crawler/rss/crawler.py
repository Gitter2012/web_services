# =============================================================================
# 模块: apps/crawler/rss/crawler.py
# 功能: 通用 RSS/Atom 订阅源爬虫模块
# 架构角色: 爬虫子系统的具体实现之一，负责从任意 RSS/Atom 订阅源获取文章。
#           继承 BaseCrawler，实现 fetch() 和 parse() 抽象方法。
# 适用场景: 技术博客、新闻站点、学术期刊等提供 RSS/Atom Feed 的内容源。
# 设计理念: 通用性优先——尽可能兼容各种 RSS/Atom 格式的差异，
#           通过多重降级策略提取文章的各个字段（URL、作者、时间、封面图等），
#           确保在不同 Feed 格式下都能获取到尽可能完整的信息。
# =============================================================================

"""RSS crawler for ResearchPulse v2."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import feedparser

from apps.crawler.base import BaseCrawler
from common.http import get_text_async

# 模块级日志器
logger = logging.getLogger(__name__)


# =============================================================================
# URL 规范化工具函数
# =============================================================================
def normalize_url_for_dedup(url: str) -> str:
    """Normalize URLs for deduplication.

    移除追踪参数与动态参数，生成稳定的标识。

    Args:
        url: Original URL.

    Returns:
        str: Normalized URL.
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        # 常见的追踪参数列表（这些参数不影响文章内容）
        TRACKING_PARAMS = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'ref', 'source', 'from', 'share', 'channel',
            'mc_cid', 'mc_eid',  # Mailchimp
            '_ga', '_gl',  # Google Analytics
            'referral', 'affiliate', 'click_id', 'session_id', 'sid',
        }

        # 解析并过滤查询参数
        params = {}
        for key, values in parse_qs(parsed.query).items():
            if key.lower() not in TRACKING_PARAMS:
                params[key] = values

        # 重建 URL
        new_query = urlencode(params, doseq=True) if params else ""
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),  # 域名小写
            parsed.path,
            parsed.params,
            new_query,
            ''  # 移除 fragment
        ))

        return normalized
    except Exception:
        return url


def generate_stable_external_id(entry: feedparser.FeedParserDict, url: str) -> str:
    """Generate a stable external identifier for a feed entry.

    优先使用条目 id 或 guid，否则使用规范化 URL，最后回退到标题哈希。

    Args:
        entry: FeedParser entry.
        url: Extracted URL.

    Returns:
        str: Stable external identifier.
    """
    # 优先级 1: 使用条目的 id
    if entry.get("id"):
        return entry.id

    # 优先级 2: 使用 guid
    if entry.get("guid"):
        return entry.guid

    # 优先级 3: 使用规范化后的 URL
    if url:
        return normalize_url_for_dedup(url)

    # 优先级 4: 使用标题哈希（后备方案）
    title = entry.get("title", "")
    if title:
        import hashlib
        return f"title-{hashlib.md5(title.encode('utf-8')).hexdigest()}"

    return ""


# =============================================================================
# RssCrawler 类
# 职责: 从指定的 RSS/Atom 订阅源获取并解析文章
# 设计决策:
#   1. 使用 feedparser 库处理 RSS/Atom 格式解析，屏蔽不同 Feed 版本的差异
#   2. _parse_entry() 对每个字段都实现了多重降级逻辑，最大化信息提取
#   3. 无标题的条目会被直接跳过，因为标题是展示文章的最基本要求
# =============================================================================
class RssCrawler(BaseCrawler):
    """Crawler for RSS/Atom feeds.

    RSS/Atom 通用爬虫实现。
    """

    # 数据源类型标识
    source_type = "rss"

    def __init__(
        self,
        feed_id: str,
        feed_url: str,
        timeout: float = 30.0,
    ):
        """Initialize RSS crawler.

        初始化 RSS 爬虫。

        Args:
            feed_id: Feed identifier.
            feed_url: RSS/Atom feed URL.
            timeout: HTTP request timeout in seconds.
        """
        super().__init__(feed_id)
        self.feed_id = feed_id
        self.feed_url = feed_url
        self.timeout = timeout

    async def fetch(self) -> str:
        """Fetch RSS feed XML content.

        使用 HTTP 工具函数请求 Feed URL，带重试和指数退避。

        Returns:
            str: RSS/Atom XML text.

        Raises:
            Exception: Propagates fetch failures.
        """
        try:
            feed_text = await get_text_async(
                self.feed_url,
                timeout=self.timeout,
                retries=3,       # 最多重试 3 次
                backoff=1.0,     # 指数退避基数（秒）
            )
            return feed_text
        except Exception as e:
            self.logger.warning(f"RSS fetch failed for {self.feed_url}: {e}")
            raise

    async def parse(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse RSS XML into article dictionaries.

        使用 feedparser 解析 XML 并逐条处理条目。

        Args:
            raw_data: RSS/Atom XML text from fetch().

        Returns:
            List[Dict[str, Any]]: Article dictionaries.
        """
        feed = feedparser.parse(raw_data)

        articles = []
        for entry in feed.entries:
            # 逐条解析，跳过无法解析的条目
            article = self._parse_entry(entry)
            if article:
                articles.append(article)

        return articles

    def _parse_entry(self, entry: feedparser.FeedParserDict) -> Dict[str, Any] | None:
        """Parse a single feed entry into an article dictionary.

        对字段采用多重降级策略兼容不同 Feed 格式。

        Args:
            entry: FeedParser entry.

        Returns:
            Dict[str, Any] | None: Article dict or ``None`` when missing title.
        """
        # ---- 提取标题（必填字段，缺失则跳过此条目）----
        # Extract title
        title = entry.get("title", "")
        if not title:
            return None

        # ---- 提取文章 URL ----
        # 优先使用 entry.link，其次查找 links 列表中的 HTML 链接，最后降级到第一个链接
        # Extract URL
        url = ""
        if entry.get("link"):
            url = entry.link
        elif entry.get("links"):
            # 优先选择 HTML 类型的链接
            for link in entry.links:
                if link.get("type", "").startswith("text/html"):
                    url = link.get("href", "")
                    break
            # 没有 HTML 链接时，使用第一个链接
            if not url and entry.links:
                url = entry.links[0].get("href", "")

        # ---- 提取作者 ----
        # 支持单作者字符串和多作者列表两种格式
        # Extract author
        author = ""
        if entry.get("author"):
            author = entry.author
        elif entry.get("authors"):
            # 多作者列表用逗号连接
            author = ", ".join(a.get("name", "") for a in entry.authors)

        # ---- 提取摘要和正文 ----
        # summary 通常是摘要/描述，content 是完整正文
        # 部分 Feed 只提供 summary，此时 content 降级使用 summary
        # Extract summary/content
        summary = entry.get("summary", "") or entry.get("description", "")
        content = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else summary

        # ---- 提取发布时间 ----
        # 优先使用 feedparser 已解析的 published_parsed（time.struct_time）
        # 降级使用 published 字符串（RFC 2822 格式）手动解析
        # Extract publish time
        publish_time = None
        if entry.get("published_parsed"):
            try:
                # published_parsed 是 time.struct_time，取前 6 个元素构造 datetime
                publish_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
        elif entry.get("published"):
            try:
                # 使用 email.utils 解析 RFC 2822 格式的日期字符串
                from email.utils import parsedate_to_datetime
                publish_time = parsedate_to_datetime(entry.published)
            except (ValueError, TypeError):
                pass

        # ---- 提取封面图片 URL ----
        # 优先从 media_content 中查找图片类型的媒体
        # 降级从 enclosures（附件）中查找图片
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

        # ---- 提取标签 ----
        # Extract tags
        tags = []
        if entry.get("tags"):
            tags = [tag.get("term", "") for tag in entry.tags if tag.get("term")]

        # ---- 生成外部唯一标识 ----
        # 使用规范化处理生成稳定的标识符，避免追踪参数导致的重复
        # Generate stable external_id (normalized URL or id/guid)
        external_id = generate_stable_external_id(entry, url)

        # 同时保存规范化后的 URL（如果原始 URL 有追踪参数，这里会保存干净的 URL）
        normalized_url = normalize_url_for_dedup(url) if url else ""

        return {
            "external_id": external_id,
            "title": title,
            "url": url,  # 保留原始 URL 用于访问
            "author": author,
            "summary": summary,
            "content": content,
            "cover_image_url": cover_image_url,
            "tags": tags,
            "publish_time": publish_time,
        }
