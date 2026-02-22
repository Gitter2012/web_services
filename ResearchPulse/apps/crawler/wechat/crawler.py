# =============================================================================
# 模块: apps/crawler/wechat/crawler.py
# 功能: 微信公众号文章爬虫模块
# 架构角色: 爬虫子系统的具体实现之一，负责从微信公众号获取文章。
#           由于微信公众平台不提供公开 API，本模块通过 RSSHub 等第三方 RSS
#           聚合服务获取微信公众号的文章内容。
# 核心类:
#   - WechatCrawler: 单个微信公众号爬虫，继承 BaseCrawler
#   - WechatMultiCrawler: 多公众号批量爬取调度器（独立类，非 BaseCrawler 子类）
# 辅助功能:
#   - 图片下载与本地缓存（基于 URL 哈希的确定性文件名，自动跳过已缓存图片）
#   - RSS 条目解析（提取标题、摘要、封面图、发布时间、微信特有字段等）
# 设计理念: 微信公众号的内容获取较为特殊，依赖第三方 RSS 服务转发。
#           模块同时支持单号爬取和多号批量爬取，批量模式下在账号之间加入延迟避免限流。
# =============================================================================

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
from common.http import get_text_async, _get_user_agent, _build_headers

# 模块级日志器
logger = logging.getLogger(__name__)

# 图片缓存目录：下载的微信文章封面图会存储在此目录
# 使用相对路径，部署时需确保此目录可写
# Image cache directory for downloaded images
_IMAGE_CACHE_DIR = Path("./data/wechat/images")


# =============================================================================
# 图片下载与缓存相关的工具函数
# 微信文章封面图通常托管在微信 CDN（mmbiz.qpic.cn）上，
# 下载时需要设置正确的 Referer 头以绕过防盗链检查。
# =============================================================================

def _ensure_image_dir() -> Path:
    """Ensure image cache directory exists.

    确保图片缓存目录存在，不存在则递归创建。

    Returns:
        Path: Image cache directory.
    """
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _IMAGE_CACHE_DIR


def _url_to_cache_filename(url: str) -> str:
    """Generate deterministic cache filename from URL.

    使用 SHA-256 哈希生成文件名，并保留常见图片扩展名。

    Args:
        url: Image URL.

    Returns:
        str: Cache filename with extension.
    """
    # 使用 SHA-256 哈希确保文件名唯一且确定性
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    parsed = urlparse(url)
    path = parsed.path
    # 提取文件扩展名
    ext = Path(path).suffix.lower() if path else ""
    # 仅保留常见图片格式的扩展名，其他一律默认 .jpg
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"):
        ext = ".jpg"
    return f"{url_hash}{ext}"


def _download_image(url: str, referer: str = "", timeout: float = 15.0) -> Optional[str]:
    """Download an image and cache it locally.

    支持缓存命中、Referer 推断与内容类型校验。

    Args:
        url: Image URL.
        referer: Optional HTTP Referer; auto-derived when empty.
        timeout: Download timeout in seconds.

    Returns:
        Optional[str]: Cached filename (without path) or ``None``.
    """
    # 仅处理有效的 HTTP/HTTPS URL
    if not url or not url.startswith(("http://", "https://")):
        return None

    filename = _url_to_cache_filename(url)
    cache_dir = _ensure_image_dir()
    local_path = cache_dir / filename

    # 缓存命中：文件已存在且非空，直接返回文件名
    # Already cached
    if local_path.exists() and local_path.stat().st_size > 0:
        return filename

    parsed = urlparse(url)
    host = parsed.hostname or ""

    if not referer:
        # 自动推断 Referer：将 CDN 域名转换为对应的网站域名
        # 例如 image.example.com -> www.example.com
        # 这是为了绕过部分 CDN 的防盗链检查
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
        # 忽略 SSL 证书验证的警告（部分微信 CDN 证书可能有问题）
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(
                url,
                headers={
                    "User-Agent": _get_user_agent(),
                    "Referer": referer,
                    # 模拟浏览器的图片请求 Accept 头
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
                timeout=timeout,
                verify=False,         # 禁用 SSL 验证以兼容部分 CDN
                allow_redirects=True, # 允许重定向
            )

        ct = resp.headers.get("content-type", "")
        # 验证响应：HTTP 200 且内容类型为图片（或内容大于 1KB，兼容缺少 Content-Type 的情况）
        if resp.status_code == 200 and ("image" in ct or len(resp.content) > 1000):
            local_path.write_bytes(resp.content)
            return filename
        else:
            logger.debug(f"Image download failed: {url[:80]} -> HTTP {resp.status_code}")
            return None
    except Exception as e:
        logger.debug(f"Image download error: {url[:80]}: {e}")
        return None


# =============================================================================
# RSS 条目解析函数
# 将 RSSHub 返回的微信公众号文章条目解析为标准化的文章字典
# =============================================================================

def _parse_wechat_rss_entry(entry: feedparser.FeedParserDict, account_name: str) -> Dict[str, Any]:
    """Parse a WeChat RSS entry into an article dictionary.

    从 RSS 条目中提取标题、URL、封面图、摘要、作者与发布时间等信息。

    Args:
        entry: FeedParser entry.
        account_name: WeChat account name for metadata.

    Returns:
        Dict[str, Any]: Article dictionary (empty if title missing).
    """
    # ---- 提取并清洗标题 ----
    # Extract title
    title = entry.get("title", "")
    if not title:
        return {}

    # 移除标题中的 HTML 标签并反转义 HTML 实体
    # Clean title (remove HTML)
    title = re.sub(r"<[^>]+>", "", title)
    title = unescape(title).strip()

    # ---- 提取文章 URL ----
    # Extract URL
    url = entry.get("link", "")

    # ---- 提取正文内容 ----
    # 微信文章的完整内容通常在 summary 或 content 字段中
    # Extract WeChat specific URL if available
    content = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")

    # ---- 提取封面图片 ----
    # 从 HTML 内容中查找第一张图片作为封面
    # Extract cover image from content
    cover_url = ""
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if img_match:
        cover_url = img_match.group(1)
        # 下载图片到本地缓存，替换 URL 为本地路径
        # Download and cache image
        local_img = _download_image(cover_url)
        if local_img:
            cover_url = f"/data/wechat/images/{local_img}"

    # ---- 提取并处理摘要 ----
    # 清除 HTML 标签，反转义实体，压缩空白，限制长度为 300 字符
    # Extract digest/summary
    digest = entry.get("summary", "")
    digest = re.sub(r"<[^>]+>", " ", digest)  # 移除 HTML 标签
    digest = unescape(digest)                   # 反转义 HTML 实体
    digest = " ".join(digest.split()).strip()   # 压缩空白字符
    # 摘要超过 500 字符时截断并添加省略号
    if len(digest) > 500:
        digest = digest[:497] + "..."

    # ---- 提取作者 ----
    # Extract author
    author = ""
    if entry.get("author"):
        author = entry.get("author", "")
    elif "author" in entry:
        author = entry.get("author", "")

    # ---- 解析发布时间 ----
    # 尝试多个时间字段：published、pubDate、updated
    # 支持字符串格式（RFC 2822）和 struct_time 格式
    # Parse publish time
    publish_time = None
    for time_field in ["published", "pubDate", "updated"]:
        if entry.get(time_field):
            try:
                if isinstance(entry[time_field], str):
                    # 字符串格式使用 RFC 2822 解析
                    publish_time = parsedate_to_datetime(entry[time_field])
                else:
                    # struct_time 格式转换为 datetime
                    publish_time = datetime.fromtimestamp(
                        time.mktime(entry[time_field]),
                        tz=timezone.utc
                    )
                break  # 成功解析后跳出循环
            except Exception:
                pass

    # ---- 生成外部唯一标识 ----
    # 优先从微信 URL 中提取 sn 参数（微信文章的唯一标识）
    # 提取不到时降级使用 URL 的 MD5 哈希
    # Generate external ID from URL
    external_id = ""
    if url:
        # 微信文章 URL 中的 sn 参数是文章的唯一标识
        # Try to extract sn parameter from WeChat URL
        sn_match = re.search(r'sn=([a-zA-Z0-9]+)', url)
        if sn_match:
            external_id = sn_match.group(1)
        else:
            # 无法提取 sn 参数时，使用 URL 的 MD5 哈希前 16 位
            external_id = hashlib.md5(url.encode()).hexdigest()[:16]

    return {
        "external_id": external_id,
        "title": title,
        "url": url,
        "author": author,
        "summary": digest,
        "content": content,
        "cover_image_url": cover_url,
        "wechat_account_name": account_name,  # 微信公众号专有字段
        "wechat_digest": digest,               # 微信公众号专有字段：文章摘要
        "publish_time": publish_time,
    }


# =============================================================================
# WechatCrawler 类
# 职责: 从单个微信公众号的 RSS 源获取文章
# 设计决策:
#   1. 通过 RSSHub 等第三方服务将微信公众号内容转为 RSS 格式
#   2. 支持自定义 RSS URL（用户可配置不同的 RSSHub 实例）
#   3. 解析时自动去重（基于 external_id）
#   4. 重写了 run() 方法，返回简化的结果格式（不直接调用 save）
# =============================================================================
class WechatCrawler(BaseCrawler):
    """Crawler for WeChat official account articles via RSS feeds.

    微信公众号 RSS 爬虫实现。
    """

    # 数据源类型标识
    source_type = "wechat"

    # 默认的微信 RSS 服务列表
    # RSSHub 是最常用的开源 RSS 生成器，支持微信公众号订阅
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
        """Initialize WeChat crawler.

        初始化微信公众号爬虫。

        Args:
            account_name: WeChat account name (source_id).
            account_id: WeChat account ID (for RSS URL).
            rss_url: Optional custom RSS URL.
            timeout: HTTP request timeout in seconds.
            max_articles: Max number of articles to parse.
            download_images: Whether to download cover images.
        """
        super().__init__(account_name)
        self.account_name = account_name
        self.account_id = account_id or account_name  # 未提供 ID 时使用名称作为 ID
        self.rss_url = rss_url
        self.timeout = timeout
        self.max_articles = max_articles
        self.download_images = download_images

    async def fetch(self) -> str:
        """Fetch WeChat RSS feed content.

        如果未配置自定义 RSS URL，会使用默认模板生成 URL。

        Returns:
            str: RSS XML content.

        Raises:
            Exception: Propagates fetch failures.
        """
        if not self.rss_url:
            # 未指定 RSS URL 时，使用默认的 RSSHub 模板自动构造
            # Try to construct RSS URL from account name
            self.rss_url = f"https://rsshub.app/wechat/mp/msgalbum/{self.account_id}"

        try:
            self.logger.info(f"Fetching WeChat RSS: {self.rss_url}")
            feed_text = await get_text_async(
                self.rss_url,
                timeout=self.timeout,
                retries=3,       # 最多重试 3 次
                backoff=2.0,     # 指数退避基数（秒），比 arXiv 更大以应对 RSSHub 限流
                delay=1.0,       # 基础延迟
                jitter=0.5,      # 随机抖动
            )
            return feed_text
        except Exception as e:
            self.logger.error(f"WeChat RSS fetch failed: {e}")
            raise

    async def parse(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse WeChat RSS XML into article dictionaries.

        使用 feedparser 解析 XML，过滤无标题与重复条目。

        Args:
            raw_data: RSS XML text from fetch().

        Returns:
            List[Dict[str, Any]]: WeChat article dictionaries.
        """
        feed = feedparser.parse(raw_data)

        # feedparser 的 bozo 标志表示 XML 解析遇到错误
        # 如果有错误且没有条目，则视为解析失败
        if feed.bozo and not feed.entries:
            self.logger.warning(f"RSS parse error: {feed.bozo_exception}")
            return []

        articles = []
        seen_ids = set()  # 用于在单次解析中去重

        # 限制解析条目数量，避免处理过多历史文章
        for entry in feed.entries[:self.max_articles]:
            article = _parse_wechat_rss_entry(entry, self.account_name)
            if not article or not article.get("title"):
                continue

            # 基于 external_id 去重，避免同一篇文章出现多次
            # Skip duplicates
            ext_id = article.get("external_id", "")
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            articles.append(article)

        self.logger.info(f"Parsed {len(articles)} WeChat articles from {self.account_name}")
        return articles

    async def run(self) -> Dict[str, Any]:
        """Run crawl workflow for a single WeChat account.

        重写 BaseCrawler.run()，返回简化结果并由调用方存储。

        Returns:
            Dict[str, Any]: Result payload including account, articles, count.
        """
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


# =============================================================================
# WechatMultiCrawler 类
# 职责: 批量爬取多个微信公众号的文章
# 设计决策:
#   1. 不继承 BaseCrawler，因为它不是针对单个数据源的爬虫，而是一个调度器
#   2. 顺序执行而非并发，因为微信 RSS 服务（如 RSSHub）通常有严格的速率限制
#   3. 在每个账号之间加入可配置的延迟
#   4. 单个账号失败不影响其他账号的爬取
# =============================================================================
class WechatMultiCrawler:
    """Crawler for multiple WeChat accounts.

    多公众号批量爬取调度器。
    """

    def __init__(
        self,
        accounts: List[Dict[str, str]],
        timeout: float = 30.0,
        delay_between_accounts: float = 3.0,
    ):
        """Initialize multi-account WeChat crawler.

        初始化多公众号批量爬虫。

        Args:
            accounts: List of account dicts with name/id/rss_url.
            timeout: Request timeout in seconds.
            delay_between_accounts: Delay between accounts in seconds.
        """
        self.accounts = accounts       # 待爬取的公众号配置列表
        self.timeout = timeout         # 每个请求的超时时间
        self.delay = delay_between_accounts  # 账号间的延迟时间（秒）
        self.logger = logging.getLogger(f"{__name__}.WechatMultiCrawler")

    async def crawl_all(self) -> Dict[str, Any]:
        """Crawl all configured WeChat accounts sequentially.

        顺序爬取多个账号，单个失败不影响整体。

        Returns:
            Dict[str, Any]: Summary payload with per-account results.
        """
        import asyncio

        # 初始化汇总结果
        results = {
            "total_accounts": len(self.accounts),
            "successful": 0,
            "failed": 0,
            "total_articles": 0,
            "accounts": [],
        }

        for i, account in enumerate(self.accounts):
            # 从配置中提取账号信息
            name = account.get("name", "")
            account_id = account.get("id", name)   # ID 默认使用 name
            rss_url = account.get("rss_url")        # 可选的自定义 RSS URL

            self.logger.info(f"Crawling WeChat account [{i+1}/{len(self.accounts)}]: {name}")

            # 为每个公众号创建独立的爬虫实例
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
                # 单个账号失败时记录错误，不中断整体流程
                self.logger.error(f"Failed to crawl {name}: {e}")
                results["accounts"].append({
                    "account": name,
                    "error": str(e),
                    "count": 0,
                })
                results["failed"] += 1

            # 在账号之间加入延迟，最后一个账号不需要延迟
            # Delay between accounts
            if i < len(self.accounts) - 1:
                await asyncio.sleep(self.delay)

        return results
