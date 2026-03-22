# =============================================================================
# 模块: apps/crawler/cn_news/crawler.py
# 功能: 中文官方媒体新闻爬虫，基于 CSS 选择器配置驱动
# 架构角色: 爬虫子系统的具体实现之一，负责从 HTML 新闻页面提取文章。
#           继承 BaseCrawler，实现 fetch() 和 parse() 抽象方法。
# 适用场景: 新华网、人民网、央视新闻等需要 HTML 解析的中文新闻站点。
# 设计理念:
#   1. CSS 选择器存储在数据库 (NewsSource.selectors)，实现零代码扩展
#   2. UA 轮转 + 随机延迟降低反爬风险
#   3. 可选的全文内容获取（逐篇获取 + readability-lxml 降级）
# =============================================================================

"""Chinese news crawler for ResearchPulse v2."""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from apps.crawler.base import BaseCrawler
from apps.crawler.models import NewsSource
from apps.crawler.registry import CrawlerRegistry

logger = logging.getLogger(__name__)


# UA 轮转池，降低反爬风险
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def _generate_external_id(url: str) -> str:
    """Generate stable external_id from URL using md5 hash.

    通过 URL 的 MD5 哈希生成稳定的 external_id，用于去重。

    Args:
        url: 文章 URL

    Returns:
        str: MD5 hash of the normalized URL
    """
    normalized = url.strip().rstrip("/").lower()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


@CrawlerRegistry.register("cn_news", model=NewsSource, priority=15)
class CnNewsCrawler(BaseCrawler):
    """Chinese news HTML crawler with CSS-selector-driven parsing.

    中文新闻 HTML 爬虫，基于数据库中存储的 CSS 选择器配置进行解析。

    Features:
        - CSS 选择器由数据库 NewsSource.selectors 提供，零代码扩展
        - UA 轮转降低反爬风险
        - 可选全文内容获取（readability-lxml 降级）
        - 随机延迟避免请求过于规律
    """

    source_type = "cn_news"

    def __init__(
        self,
        source_id: str,
        list_url: str,
        selectors: dict,
        site_url: str = "",
        encoding: str = "utf-8",
        country: str = "CN",
        news_category: str = "general",
        timeout: float = 30.0,
        fetch_content: bool = False,
    ):
        """Initialize CnNewsCrawler.

        Args:
            source_id: 数据源 ID（NewsSource.id 的字符串形式）
            list_url: 文章列表页 URL
            selectors: CSS 选择器配置字典
            site_url: 站点首页 URL（用于 urljoin 解析相对链接）
            encoding: 页面编码（utf-8/gbk 等）
            country: 新闻来源国家（CN/EN）
            news_category: 新闻分类（general/tech/finance 等）
            timeout: HTTP 请求超时时间（秒）
            fetch_content: 是否逐篇获取全文内容
        """
        super().__init__(source_id=source_id)
        self.list_url = list_url
        self.selectors = selectors
        self.site_url = site_url
        self.encoding = encoding
        self.country = country
        self.news_category = news_category
        self.timeout = timeout
        self.fetch_content = fetch_content

    def _get_headers(self) -> dict:
        """Build request headers with rotating UA.

        构建带 UA 轮转的请求头。
        """
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }

    def _resolve_url(self, href: str) -> str:
        """Resolve relative URL to absolute.

        将相对链接转换为绝对链接。

        Args:
            href: 原始链接（可能是相对路径）

        Returns:
            str: 绝对 URL
        """
        if not href:
            return ""
        # 已经是绝对 URL
        if href.startswith(("http://", "https://")):
            return href
        # 使用 site_url 或 list_url 作为基础解析
        base = self.site_url or self.list_url
        return urljoin(base, href)

    async def fetch(self) -> str:
        """Fetch the news list page HTML.

        获取新闻列表页的 HTML 内容。

        Returns:
            str: 列表页 HTML 文本
        """
        self.logger.info(f"Fetching news list page: {self.list_url}")

        req_timeout = httpx.Timeout(
            connect=min(self.timeout, 10.0),
            read=self.timeout,
            write=self.timeout,
            pool=min(self.timeout, 5.0),
        )

        async with httpx.AsyncClient(
            timeout=req_timeout,
            follow_redirects=True,
            verify=False,
        ) as client:
            response = await client.get(self.list_url, headers=self._get_headers())
            response.raise_for_status()

            # 处理编码
            if self.encoding.lower() != "utf-8":
                return response.content.decode(self.encoding, errors="replace")
            return response.text

    async def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Parse the HTML list page into article dictionaries.

        解析 HTML 列表页，提取文章列表。

        Args:
            raw_data: HTML 文本（来自 fetch()）

        Returns:
            List[Dict]: 文章字典列表，键名与 Article 模型字段对应
        """
        html = raw_data
        soup = BeautifulSoup(html, "html.parser")

        articles = []
        article_list_selector = self.selectors.get("article_list", "")

        if not article_list_selector:
            self.logger.warning("No article_list selector configured, cannot parse")
            return []

        items = soup.select(article_list_selector)
        self.logger.info(f"Found {len(items)} items with selector '{article_list_selector}'")

        for item in items:
            try:
                article = self._parse_item(item)
                if article:
                    articles.append(article)
            except Exception as e:
                self.logger.debug(f"Failed to parse item: {e}")
                continue

        self.logger.info(f"Parsed {len(articles)} articles from {self.list_url}")

        # 可选：逐篇获取全文内容
        if self.fetch_content and articles:
            articles = await self._fetch_article_contents(articles)

        return articles

    def _parse_item(self, item: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Parse a single list item into an article dict.

        解析列表中的单个条目为文章字典。

        Args:
            item: BeautifulSoup 元素（列表项）

        Returns:
            Dict or None: 文章字典或 None（如果缺少必要字段）
        """
        # 提取标题
        title = ""
        title_selector = self.selectors.get("title", "a")
        title_elem = item.select_one(title_selector)
        if title_elem:
            title = title_elem.get_text(strip=True)

        if not title:
            return None

        # 提取链接
        link = ""
        link_selector = self.selectors.get("link", "a")
        link_elem = item.select_one(link_selector)
        if link_elem:
            link = link_elem.get("href", "")
        link = self._resolve_url(link)

        if not link:
            return None

        # 生成 external_id（基于 URL 的 MD5）
        external_id = _generate_external_id(link)

        # 提取摘要
        summary = ""
        summary_selector = self.selectors.get("summary", "")
        if summary_selector:
            summary_elem = item.select_one(summary_selector)
            if summary_elem:
                summary = summary_elem.get_text(strip=True)

        # 提取时间
        publish_time = None
        time_selector = self.selectors.get("time", "")
        if time_selector:
            time_elem = item.select_one(time_selector)
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                publish_time = self._parse_time(time_text)

        # 提取图片
        image_url = ""
        image_selector = self.selectors.get("image", "img")
        if image_selector:
            img_elem = item.select_one(image_selector)
            if img_elem:
                image_url = img_elem.get("src", "") or img_elem.get("data-src", "")
                image_url = self._resolve_url(image_url)

        return {
            "external_id": external_id,
            "title": title,
            "url": link,
            "summary": summary,
            "publish_time": publish_time,
            "image_url": image_url,
            "cover_image_url": image_url,
            "news_source_country": self.country,
            "news_category": self.news_category,
            "source_crawler_type": "cn_news",
        }

    def _parse_time(self, time_text: str) -> Optional[datetime]:
        """Parse a time string into datetime.

        尝试多种中文日期格式解析时间字符串。

        Args:
            time_text: 时间字符串

        Returns:
            datetime or None: 解析后的时间对象
        """
        if not time_text:
            return None

        # 常见中文新闻站时间格式
        time_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y年%m月%d日 %H:%M:%S",
            "%Y年%m月%d日 %H:%M",
            "%Y年%m月%d日",
            "%m-%d %H:%M",
            "%m月%d日 %H:%M",
        ]

        for fmt in time_formats:
            try:
                dt = datetime.strptime(time_text.strip(), fmt)
                # 如果缺少年份，补充当前年份
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        self.logger.debug(f"Could not parse time: '{time_text}'")
        return None

    async def _fetch_article_contents(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fetch full content for each article.

        逐篇获取文章全文内容。

        Args:
            articles: 文章字典列表

        Returns:
            List[Dict]: 更新了 content 字段的文章列表
        """
        content_selector = self.selectors.get("content", "")

        for article in articles:
            url = article.get("url", "")
            if not url:
                continue

            try:
                # 随机延迟 1~3 秒
                delay = random.uniform(1.0, 3.0)
                import asyncio
                await asyncio.sleep(delay)

                req_timeout = httpx.Timeout(
                    connect=min(self.timeout, 10.0),
                    read=self.timeout,
                    write=self.timeout,
                    pool=min(self.timeout, 5.0),
                )

                async with httpx.AsyncClient(
                    timeout=req_timeout,
                    follow_redirects=True,
                    verify=False,
                ) as client:
                    response = await client.get(url, headers=self._get_headers())
                    response.raise_for_status()

                    if self.encoding.lower() != "utf-8":
                        html = response.content.decode(self.encoding, errors="replace")
                    else:
                        html = response.text

                # 尝试使用 CSS 选择器提取正文
                content = ""
                if content_selector:
                    soup = BeautifulSoup(html, "html.parser")
                    content_elem = soup.select_one(content_selector)
                    if content_elem:
                        content = content_elem.get_text(separator="\n", strip=True)

                # 降级：使用 readability-lxml 自动提取
                if not content:
                    try:
                        from readability import Document
                        doc = Document(html)
                        readable_html = doc.summary()
                        readable_soup = BeautifulSoup(readable_html, "html.parser")
                        content = readable_soup.get_text(separator="\n", strip=True)
                    except ImportError:
                        self.logger.debug("readability-lxml not available, skipping content extraction")
                    except Exception as e:
                        self.logger.debug(f"readability extraction failed for {url}: {e}")

                if content:
                    # 截断过长的内容
                    if len(content) > 10000:
                        content = content[:10000] + "..."
                    article["content"] = content

            except Exception as e:
                self.logger.debug(f"Failed to fetch content from {url}: {e}")
                continue

        return articles
