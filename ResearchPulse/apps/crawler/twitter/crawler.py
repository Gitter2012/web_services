# =============================================================================
# 模块: apps/crawler/twitter/crawler.py
# 功能: Twitter 爬虫模块（使用 TwitterAPI.io 第三方 API）
# 架构角色: 爬虫子系统的具体实现之一，负责从 Twitter 获取用户推文
#           继承 BaseCrawler，实现 fetch() 和 parse() 抽象方法
# 适用场景: 抓取指定 Twitter 用户的最新推文
# 设计理念:
#   1. 使用 TwitterAPI.io 第三方 API，比官方 API 更便宜
#   2. 支持增量抓取，通过 last_tweet_id 过滤已抓取内容
#   3. 内置 TTL 内存缓存，避免短时间内重复请求
#   4. 需要配置 TWITTERAPI_IO_KEY 环境变量
# =============================================================================

"""Twitter crawler for ResearchPulse v2."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from apps.crawler.base import BaseCrawler
from apps.crawler.registry import CrawlerRegistry
from apps.crawler.models import TwitterSource

# 模块级日志器
logger = logging.getLogger(__name__)

# TwitterAPI.io API 端点
TWITTERAPI_BASE_URL = "https://api.twitterapi.io/twitter/user/last_tweets"

# 默认缓存 TTL（秒）
DEFAULT_CACHE_TTL = 300.0  # 5 minutes


# =============================================================================
# TwitterCrawler 类
# 职责: 从指定的 Twitter 用户获取最新推文
# 设计决策:
#   1. 使用 TwitterAPI.io 第三方 API，避免官方 API 的高昂费用
#   2. 支持 last_tweet_id 增量抓取，减少重复数据
#   3. 类级别 TTL 缓存，避免短时间内重复请求
# =============================================================================
@CrawlerRegistry.register("twitter", model=TwitterSource, priority=60)
class TwitterCrawler(BaseCrawler):
    """Crawler for Twitter user tweets using TwitterAPI.io.

    Twitter 爬虫实现，需要 TwitterAPI.io API Key。
    """

    # 数据源类型标识
    source_type = "twitter"

    # 类级别缓存: {username: (timestamp, tweets_data)}
    _cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
    _cache_ttl: float = DEFAULT_CACHE_TTL

    def __init__(
        self,
        username: str,
        api_key: Optional[str] = None,
        max_results: int = 20,
        timeout: float = 15.0,
    ):
        """Initialize Twitter crawler.

        初始化 Twitter 爬虫。

        Args:
            username: Twitter username (without @).
            api_key: TwitterAPI.io API key. If not provided, will use settings.
            max_results: Maximum number of tweets to fetch.
            timeout: HTTP request timeout in seconds.
        """
        # 使用 username 作为 source_id
        super().__init__(username.lstrip("@"))
        self.username = username.lstrip("@")
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self._shared_client: Optional[httpx.AsyncClient] = None

    def set_shared_client(self, client: httpx.AsyncClient) -> None:
        """Set a shared HTTP client for connection pooling.

        设置共享 HTTP 客户端，用于连接池复用。

        Args:
            client: Shared httpx.AsyncClient instance.
        """
        self._shared_client = client

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the response cache.

        清除响应缓存（用于测试）。
        """
        cls._cache.clear()

    @classmethod
    def set_cache_ttl(cls, ttl: float) -> None:
        """Set cache TTL in seconds.

        设置缓存 TTL（秒）。

        Args:
            ttl: Cache TTL in seconds.
        """
        cls._cache_ttl = ttl

    @classmethod
    def _get_cached_tweets(cls, username: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached tweets if still valid within TTL.

        从缓存获取推文数据（如果在 TTL 有效期内）。

        Args:
            username: Twitter username.

        Returns:
            Cached tweets data or None if expired/missing.
        """
        cache_key = username.lower()
        if cache_key in cls._cache:
            cached_time, cached_data = cls._cache[cache_key]
            if time.time() - cached_time < cls._cache_ttl:
                return cached_data
            # 已过期，删除缓存
            del cls._cache[cache_key]
        return None

    @classmethod
    def _set_cached_tweets(cls, username: str, tweets: List[Dict[str, Any]]) -> None:
        """Store tweets in cache with current timestamp.

        将推文数据存入缓存。

        Args:
            username: Twitter username.
            tweets: Tweets data to cache.
        """
        cache_key = username.lower()
        cls._cache[cache_key] = (time.time(), tweets)

    async def fetch(self) -> Dict[str, Any]:
        """Fetch tweets from TwitterAPI.io API.

        从 TwitterAPI.io API 获取推文数据。

        Returns:
            Dict containing API response data.

        Raises:
            RuntimeError: If API key not configured or API request fails.
        """
        # 获取 API Key
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError(
                "TwitterAPI.io API key not configured. "
                "Set TWITTERAPI_IO_KEY environment variable or pass api_key parameter."
            )

        # 检查缓存
        cached_tweets = self._get_cached_tweets(self.username)
        if cached_tweets is not None:
            self.logger.info(f"Using cached results for @{self.username} (TTL: {self._cache_ttl}s)")
            return {"tweets": cached_tweets, "from_cache": True}

        # 使用共享客户端或创建新客户端
        http_client = self._shared_client
        should_close = http_client is None

        if http_client is None:
            http_client = httpx.AsyncClient(timeout=self.timeout)

        try:
            response = await http_client.get(
                TWITTERAPI_BASE_URL,
                params={
                    "userName": self.username,
                    "includeReplies": "false",
                },
                headers={"X-API-Key": api_key},
            )

            # 处理特定错误状态码
            if response.status_code == 401:
                raise RuntimeError(
                    "TwitterAPI.io authentication failed. Check your API key."
                )
            elif response.status_code == 402:
                raise RuntimeError(
                    "TwitterAPI.io credits exhausted. Please add credits."
                )
            elif response.status_code == 404:
                raise RuntimeError(f"Twitter user @{self.username} not found.")

            response.raise_for_status()
            data = response.json()

        finally:
            if should_close:
                await http_client.aclose()

        # 检查 API 响应状态
        if data.get("status") != "success":
            err_msg = data.get("msg") or data.get("message") or "Unknown TwitterAPI.io error"
            raise RuntimeError(f"TwitterAPI.io error: {err_msg}")

        # 提取推文数据
        tweets = data.get("data", {}).get("tweets", [])

        # 缓存结果
        self._set_cached_tweets(self.username, tweets)

        return {"tweets": tweets, "from_cache": False}

    async def parse(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse API response into article dictionaries.

        将 API 响应解析为文章字典列表。

        Args:
            raw_data: API response data from fetch().

        Returns:
            List[Dict[str, Any]]: Article dictionaries.
        """
        tweets = raw_data.get("tweets", [])
        articles = []

        for tweet in tweets[: self.max_results]:
            article = self._parse_tweet(tweet)
            if article:
                articles.append(article)

        return articles

    def _parse_tweet(self, tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single tweet into an article dictionary.

        解析单条推文。

        Args:
            tweet: Tweet data from API.

        Returns:
            Dict[str, Any] | None: Article dict or None on error.
        """
        try:
            external_id = tweet.get("id", "")
            if not external_id:
                return None

            text = tweet.get("text", "")
            author_info = tweet.get("author", {})
            username = author_info.get("userName", self.username)

            # 使用第一行或截断文本作为标题
            title = text.split("\n")[0][:100]
            if len(text) > 100:
                title = title[:97] + "..."

            # 构建推文 URL
            url = tweet.get(
                "url",
                f"https://twitter.com/{username}/status/{external_id}"
            )

            # 解析创建时间
            # TwitterAPI.io 格式: "Fri Jan 24 18:30:00 +0000 2025"
            publish_time = None
            created_at_str = tweet.get("createdAt", "")
            if created_at_str:
                try:
                    publish_time = datetime.strptime(
                        created_at_str, "%a %b %d %H:%M:%S %z %Y"
                    )
                except (ValueError, TypeError):
                    pass

            return {
                "external_id": external_id,
                "title": title,
                "url": url,
                "author": f"@{username}",
                "summary": text[:280] if text else "",  # Twitter 字符限制
                "content": text,
                "publish_time": publish_time,
                "category": "tweet",
            }

        except Exception:
            return None

    def _get_api_key(self) -> Optional[str]:
        """Get TwitterAPI.io API key from settings or instance.

        从配置或实例获取 API Key。

        Returns:
            API key string or None.
        """
        if self.api_key:
            return self.api_key

        # 尝试从 settings 获取
        try:
            from settings import settings
            return getattr(settings, "twitterapi_io_key", None)
        except Exception:
            pass

        # 尝试从环境变量获取
        import os
        return os.environ.get("TWITTERAPI_IO_KEY")
