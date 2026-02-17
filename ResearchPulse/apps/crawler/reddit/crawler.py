# =============================================================================
# 模块: apps/crawler/reddit/crawler.py
# 功能: Reddit RSS 爬虫模块
# 架构角色: 爬虫子系统的具体实现之一，负责从 Reddit RSS 获取内容
#           继承 BaseCrawler，实现 fetch() 和 parse() 抽象方法
# 适用场景: 抓取 Subreddit（子版块）和 Reddit User（用户）的帖子
# 设计理念:
#   1. 使用 Reddit 官方 RSS Feed 作为数据源，稳定可靠
#   2. 支持 Subreddit 和 User 两种订阅类型
#   3. 对于链接类帖子，自动尝试抓取外部链接内容增强信息量
#   4. 遵循 Reddit 的 bot 规范，使用自定义 User-Agent
# =============================================================================

"""Reddit crawler for ResearchPulse v2."""

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
# Reddit RSS URL 模板
# =============================================================================
SUBREDDIT_RSS_URL = "https://www.reddit.com/r/{name}/.rss"
USER_RSS_URL = "https://www.reddit.com/user/{name}/.rss"

# 自定义 User-Agent，遵循 Reddit 的 bot 规范
# 格式: platform:app_id:version (by /u/username or contact)
REDDIT_USER_AGENT = "python:ResearchPulse:1.0 (by ResearchPulse)"

# 链接帖子检测模式
# 典型的链接帖子内容: "submitted by /u/username [link] [comments]"
LINK_POST_PATTERN = re.compile(r"^\s*submitted by\s+/u/\S+\s*\[link\]\s*\[comments\]\s*$", re.I)


# =============================================================================
# RedditCrawler 类
# 职责: 从指定的 Subreddit 或 User 获取并解析帖子
# 设计决策:
#   1. 使用 Reddit 官方 RSS Feed，避免 API 限制
#   2. source_type 区分 "subreddit" 和 "user" 两种订阅类型
#   3. 对于链接类帖子，尝试抓取外部链接的内容
# =============================================================================
class RedditCrawler(BaseCrawler):
    """Crawler for Reddit RSS feeds.

    Reddit 爬虫实现，支持 Subreddit 和 User 两种订阅类型。
    """

    # 数据源类型标识
    source_type = "reddit"

    def __init__(
        self,
        source_type: str,
        source_name: str,
        timeout: float = 30.0,
        fetch_external_content: bool = True,
    ):
        """Initialize Reddit crawler.

        初始化 Reddit 爬虫。

        Args:
            source_type: Source type ("subreddit" or "user").
            source_name: Subreddit name or Reddit username.
            timeout: HTTP request timeout in seconds.
            fetch_external_content: Whether to fetch external link content.
        """
        # 组合 source_type 和 source_name 作为 source_id
        # 例如: "subreddit/python" 或 "user/spez"
        super().__init__(f"{source_type}/{source_name}")
        self.reddit_source_type = source_type  # "subreddit" or "user"
        self.source_name = source_name
        self.timeout = timeout
        self.fetch_external_content = fetch_external_content
        self.feed_url = self._get_feed_url()

    def _get_feed_url(self) -> str:
        """Get the RSS feed URL based on source type.

        根据源类型获取对应的 RSS URL。

        Returns:
            str: RSS feed URL.
        """
        if self.reddit_source_type == "subreddit":
            return SUBREDDIT_RSS_URL.format(name=self.source_name)
        return USER_RSS_URL.format(name=self.source_name)

    async def fetch(self) -> str:
        """Fetch Reddit RSS feed content.

        使用 HTTP 工具函数请求 Feed URL，带重试和指数退避。
        使用自定义 User-Agent 遵循 Reddit bot 规范。

        Returns:
            str: RSS XML text.

        Raises:
            Exception: Propagates fetch failures.
        """
        try:
            # Reddit 要求使用自定义 User-Agent
            from common.http import get_async_client
            client = get_async_client(self.timeout)

            # 构建请求头
            headers = {
                "User-Agent": REDDIT_USER_AGENT,
            }

            response = await client.get(
                self.feed_url,
                headers=headers,
            )
            response.raise_for_status()

            return response.text

        except Exception as e:
            self.logger.warning(f"Reddit fetch failed for {self.feed_url}: {e}")
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
                if self._is_link_post(article.get("content", "")):
                    external_url = article.get("external_link")
                    if external_url:
                        try:
                            content = await self._fetch_external_content(external_url)
                            if content:
                                article["content"] = (
                                    f"[外部链接] {external_url}\n\n{content}"
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
        content_clean = self._clean_html(content)

        # ---- 提取 URL ----
        url = entry.get("link", "")

        # ---- 提取外部链接（用于内容增强）----
        external_link = self._extract_external_url(entry, content)

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
            "url": url,
            "author": author,
            "summary": content_clean[:500] if content_clean else "",
            "content": content_clean[:10000] if content_clean else "",
            "publish_time": publish_time,
            "category": self.reddit_source_type,
            # 额外字段：外部链接，用于后续内容增强
            "external_link": external_link,
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

    def _is_link_post(self, content: str) -> bool:
        """Check if content indicates a link-post (no real content).

        判断是否为链接类帖子（内容很少或符合特定模式）。

        Args:
            content: Article content.

        Returns:
            bool: True if this is a link-post.
        """
        if not content:
            return True

        content = content.strip()

        # 检查典型的链接帖子模式
        if LINK_POST_PATTERN.match(content):
            return True

        # 内容过短也可能是链接帖子
        if len(content) < 100:
            return True

        return False

    def _extract_external_url(self, entry: dict, content_html: str) -> Optional[str]:
        """Extract external URL from RSS entry.

        从 RSS 条目中提取外部链接。

        Args:
            entry: FeedParser entry.
            content_html: Raw HTML content.

        Returns:
            Optional[str]: External URL or None.
        """
        # 在 HTML 中查找 [link] 标记
        # Reddit RSS 格式: <a href="[url]">[link]</a>
        link_match = re.search(
            r'<a\s+href="([^"]+)"[^>]*>\s*\[link\]\s*</a>',
            content_html,
            re.I
        )
        if link_match:
            url = link_match.group(1)
            # 跳过 Reddit 内部链接
            if "reddit.com" not in url and "redd.it" not in url:
                return url

        return None

    async def _fetch_external_content(self, url: str) -> str:
        """Fetch and extract content from external URL.

        从外部 URL 抓取并提取正文内容。

        Args:
            url: External URL to fetch.

        Returns:
            str: Extracted content, or empty string on failure.
        """
        try:
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
