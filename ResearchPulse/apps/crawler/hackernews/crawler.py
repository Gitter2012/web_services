# =============================================================================
# 模块: apps/crawler/hackernews/crawler.py
# 功能: HackerNews RSS 爬虫模块
# 架构角色: 爬虫子系统的具体实现之一，负责从 hnrss.org 获取 HackerNews 内容
#           继承 BaseCrawler，实现 fetch() 和 parse() 抽象方法
# 适用场景: 抓取 HackerNews 首页、最新、最佳、Ask HN、Show HN 等板块内容
# 设计理念:
#   1. 使用 hnrss.org 提供的 RSS Feed 作为数据源，稳定可靠
#   2. 支持多种 HN 板块类型（front/new/best/ask/show）
#   3. 对于外部链接类帖子，自动尝试抓取原文内容增强信息量
# =============================================================================

"""HackerNews crawler for ResearchPulse v2."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import feedparser

from apps.crawler.base import BaseCrawler
from common.http import get_text_async

# 模块级日志器
logger = logging.getLogger(__name__)


# =============================================================================
# HackerNews Feed 配置
# 支持的板块类型及其对应的 RSS URL
# =============================================================================
HN_FEEDS = {
    "front": "https://hnrss.org/frontpage",
    "new": "https://hnrss.org/newest",
    "best": "https://hnrss.org/best",
    "ask": "https://hnrss.org/ask",
    "show": "https://hnrss.org/show",
}

# Feed 类型到中文名称的映射
HN_FEED_NAMES = {
    "front": "HackerNews 首页",
    "new": "HackerNews 最新",
    "best": "HackerNews 精选",
    "ask": "Ask HN",
    "show": "Show HN",
}


# =============================================================================
# HackerNewsCrawler 类
# 职责: 从指定的 HackerNews 板块获取并解析帖子
# 设计决策:
#   1. 使用 hnrss.org 作为数据源，避免直接爬取 HackerNews 官网
#   2. 对于链接类帖子（非 Ask HN），尝试抓取外部链接的原文内容
#   3. 使用 HN 讨论页作为文章 URL，方便用户参与讨论
# =============================================================================
class HackerNewsCrawler(BaseCrawler):
    """Crawler for HackerNews RSS feeds via hnrss.org.

    HackerNews 爬虫实现，支持多种板块类型。
    """

    # 数据源类型标识
    source_type = "hackernews"

    def __init__(
        self,
        feed_type: str,
        timeout: float = 30.0,
        fetch_external_content: bool = True,
    ):
        """Initialize HackerNews crawler.

        初始化 HackerNews 爬虫。

        Args:
            feed_type: Feed type (front/new/best/ask/show).
            timeout: HTTP request timeout in seconds.
            fetch_external_content: Whether to fetch external link content.
        """
        # 使用 feed_type 作为 source_id
        super().__init__(feed_type)
        self.feed_type = feed_type
        self.timeout = timeout
        self.fetch_external_content = fetch_external_content
        self.feed_url = HN_FEEDS.get(feed_type, HN_FEEDS["front"])

    async def fetch(self) -> str:
        """Fetch HackerNews RSS feed content.

        使用 HTTP 工具函数请求 Feed URL，带重试和指数退避。

        Returns:
            str: RSS XML text.

        Raises:
            Exception: Propagates fetch failures.
        """
        try:
            feed_text = await get_text_async(
                self.feed_url,
                timeout=self.timeout,
                retries=3,
                backoff=1.0,
            )
            return feed_text
        except Exception as e:
            self.logger.warning(f"HackerNews fetch failed for {self.feed_url}: {e}")
            raise

    async def parse(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse RSS XML into article dictionaries.

        使用 feedparser 解析 XML 并逐条处理条目。
        对于链接类帖子，尝试访问原文 URL 提取完整正文。

        Args:
            raw_data: RSS XML text from fetch().

        Returns:
            List[Dict[str, Any]]: Article dictionaries.
        """
        feed = feedparser.parse(raw_data)

        # 检查解析错误
        if feed.bozo and not feed.entries:
            self.logger.warning(f"RSS parse error: {feed.bozo_exception}")
            return []

        articles = []
        for entry in feed.entries:
            article = self._parse_entry(entry)
            if article:
                articles.append(article)

        # 对于链接类帖子，尝试抓取外部链接的内容
        if self.fetch_external_content:
            for article in articles:
                external_url = article.get("external_link")
                if external_url and self._should_fetch_content(article):
                    try:
                        content = await self._fetch_external_content(external_url)
                        if content and len(content) > len(article.get("content", "")):
                            # 将外部链接信息添加到内容中
                            article["content"] = (
                                f"[外部链接] {external_url}\n\n"
                                f"{content}"
                            )
                    except Exception as e:
                        self.logger.debug(
                            f"Failed to fetch external content for {external_url}: {e}"
                        )

        return articles

    def _parse_entry(self, entry: feedparser.FeedParserDict) -> Optional[Dict[str, Any]]:
        """Parse a single RSS entry into an article dictionary.

        对字段采用多重降级策略兼容不同 Feed 格式。

        Args:
            entry: FeedParser entry.

        Returns:
            Dict[str, Any] | None: Article dict or None when missing title.
        """
        # ---- 提取外部唯一标识 ----
        external_id = entry.get("id") or entry.get("link", "")
        if not external_id:
            return None

        # ---- 提取标题（必填字段）----
        title = entry.get("title", "")
        if not title:
            return None

        # ---- 提取内容/摘要 ----
        content = ""
        if "content" in entry and entry["content"]:
            content = entry["content"][0].get("value", "")
        elif "summary" in entry:
            content = entry.get("summary", "")

        # 清理 HTML 标签
        content = self._clean_html(content)

        # ---- 提取 URL ----
        # hnrss.org 的 link 字段指向外部链接，comments 字段指向 HN 讨论页
        # 我们优先使用 HN 讨论页作为文章 URL，方便用户参与讨论
        external_link = entry.get("link", "")
        hn_url = entry.get("comments", "") or external_link

        # ---- 提取作者 ----
        author = entry.get("author", "")
        if not author and "authors" in entry and entry["authors"]:
            author = entry["authors"][0].get("name", "")

        # ---- 提取发布时间 ----
        publish_time = None
        if "published_parsed" in entry and entry["published_parsed"]:
            try:
                publish_time = datetime(
                    *entry["published_parsed"][:6], tzinfo=timezone.utc
                )
            except (TypeError, ValueError):
                pass
        elif "published" in entry:
            try:
                publish_time = parsedate_to_datetime(entry["published"])
            except (TypeError, ValueError):
                pass

        return {
            "external_id": external_id,
            "title": title,
            "url": hn_url,
            "author": author,
            "summary": content[:500] if content else "",
            "content": content[:10000] if content else "",
            "publish_time": publish_time,
            "category": self.feed_type,
            # 额外字段：外部链接，用于后续内容增强
            "external_link": external_link if external_link != hn_url else None,
        }

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities.

        清理 HTML 标签并解码实体。

        Args:
            text: Raw HTML text.

        Returns:
            str: Cleaned plain text.
        """
        if not text:
            return ""

        # 解码 HTML 实体
        text = html.unescape(text)

        # 移除 HTML 标签
        text = re.sub(r"<[^>]+>", " ", text)

        # 规范化空白字符
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _should_fetch_content(self, article: Dict[str, Any]) -> bool:
        """Check if we should fetch external content.

        判断是否需要抓取外部链接的内容。

        Args:
            article: Article dictionary.

        Returns:
            bool: True if content should be fetched.
        """
        content = article.get("content", "")
        # 内容为空或过短时需要抓取
        if not content or len(content.strip()) < 200:
            return True
        return False

    async def _fetch_external_content(self, url: str) -> str:
        """Fetch and extract content from external URL.

        从外部 URL 抓取并提取正文内容。

        Args:
            url: External URL to fetch.

        Returns:
            str: Extracted content, or empty string on failure.
        """
        try:
            # 检查是否为 HN 内部链接
            if "news.ycombinator.com" in url:
                return ""

            html_content = await get_text_async(
                url,
                timeout=15.0,
                retries=1,
                backoff=1.0,
            )

            if not html_content:
                return ""

            # 使用 BeautifulSoup 提取正文
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_content, "html.parser")

            # 移除干扰元素
            for tag in soup.find_all(
                ["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]
            ):
                tag.decompose()

            # 策略 1: 查找 <article> 标签
            article_tag = soup.find("article")
            if article_tag:
                text = article_tag.get_text(separator="\n", strip=True)
                if len(text) >= 100:
                    return text

            # 策略 2: 查找常见正文容器
            content_selectors = [
                {"class_": re.compile(r"article[_-]?(body|content|text)", re.I)},
                {"class_": re.compile(r"post[_-]?(body|content|text)", re.I)},
                {"class_": re.compile(r"(main[_-]?content|content[_-]?area)", re.I)},
            ]
            for selector in content_selectors:
                container = soup.find("div", **selector)
                if container:
                    text = container.get_text(separator="\n", strip=True)
                    if len(text) >= 100:
                        return text

            # 策略 3: 查找 body 中最长的文本段落
            body = soup.find("body")
            if body:
                paragraphs = body.find_all("p")
                if paragraphs:
                    full_text = "\n".join(
                        p.get_text(strip=True)
                        for p in paragraphs
                        if p.get_text(strip=True)
                    )
                    if len(full_text) >= 100:
                        return full_text

            return ""

        except Exception:
            return ""
