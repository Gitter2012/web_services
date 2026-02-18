# =============================================================================
# 模块: apps/crawler/weibo/crawler.py
# 功能: 微博热搜数据爬取器
# 架构角色: 继承 BaseCrawler，实现微博热搜数据的获取和解析
# 数据源:
#   - 公开接口: https://weibo.com/ajax/side/hotSearch (热搜榜)
#   - 认证接口: https://weibo.com/ajax/statuses/hotband?band=* (多榜单)
# 支持榜单: 热搜榜(realtimehot)、要闻榜(socialevent)、文娱榜(entrank)、
#          体育榜(sport)、游戏榜(game)
# =============================================================================

"""Weibo hot search crawler implementation."""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apps.crawler.base import BaseCrawler
from apps.crawler.registry import CrawlerRegistry
from apps.crawler.models import WeiboHotSearch

# 模块级日志器
logger = logging.getLogger(__name__)

# 微博 API 端点
WEIBO_HOT_SEARCH_API = "https://weibo.com/ajax/side/hotSearch"  # 公开接口，热搜榜
WEIBO_HOTBAND_API = "https://weibo.com/ajax/statuses/hotband"  # 需要登录，多榜单

# 榜单类型映射
BOARD_TYPE_MAP = {
    "realtimehot": {
        "name": "热搜榜",
        "api": "public",  # 使用公开接口
        "data_key": "realtime",
        "description": "微博实时热搜榜单",
    },
    "socialevent": {
        "name": "要闻榜",
        "api": "auth",  # 需要认证
        "data_key": "band",
        "description": "微博社会要闻榜单",
    },
    "entrank": {
        "name": "文娱榜",
        "api": "auth",
        "data_key": "band",
        "description": "微博文娱热点榜单",
    },
    "sport": {
        "name": "体育榜",
        "api": "auth",
        "data_key": "band",
        "description": "微博体育热点榜单",
    },
    "game": {
        "name": "游戏榜",
        "api": "auth",
        "data_key": "band",
        "description": "微博游戏热点榜单",
    },
}


@CrawlerRegistry.register("weibo", model=WeiboHotSearch, priority=30)
class WeiboCrawler(BaseCrawler):
    """Weibo hot search crawler.

    微博热搜爬虫，支持获取微博热搜榜单数据。

    支持的榜单:
        - realtimehot: 热搜榜（公开接口）
        - socialevent: 要闻榜（需要登录 Cookie）
        - entrank: 文娱榜（需要登录 Cookie）
        - sport: 体育榜（需要登录 Cookie）
        - game: 游戏榜（需要登录 Cookie）

    Attributes:
        source_type: 数据源类型，固定为 "weibo"
        source_id: 榜单类型
        cookie: 微博登录 Cookie（用于需要认证的榜单）
    """

    source_type = "weibo"

    def __init__(
        self,
        source_id: str,
        timeout: float = 30.0,
        cookie: str = "",
        delay_base: float = 5.0,
        delay_jitter: float = 2.0,
    ):
        """Initialize Weibo crawler.

        初始化微博爬虫实例。

        Args:
            source_id: 榜单类型（realtimehot, socialevent, entrank, sport, game）
            timeout: 请求超时时间（秒）
            cookie: 微博登录 Cookie（用于需要认证的榜单）
            delay_base: 基础延迟时间（秒）
            delay_jitter: 延迟抖动范围（秒）
        """
        super().__init__(source_id)
        self.timeout = timeout
        self.cookie = cookie
        self.delay_base = delay_base
        self.delay_jitter = delay_jitter
        self._board_config = BOARD_TYPE_MAP.get(source_id, {})

    async def fetch(self) -> Dict[str, Any]:
        """Fetch hot search data from Weibo API.

        从微博 API 获取热搜数据。

        Returns:
            Dict containing raw API response with hot search items.

        Raises:
            RuntimeError: If the API request fails or returns invalid data.
        """
        if not self._board_config:
            self.logger.warning(f"Unknown board type: '{self.source_id}'")
            return {"ok": False, "data": {}, "error": "Unknown board type"}

        api_type = self._board_config.get("api")

        # 根据榜单类型选择不同的获取方式
        if api_type == "public":
            return await self._fetch_public()
        elif api_type == "auth":
            return await self._fetch_with_auth()
        else:
            return {"ok": False, "data": {}, "error": "Unsupported board type"}

    async def _fetch_public(self) -> Dict[str, Any]:
        """Fetch data from public API (no authentication required).

        从公开接口获取数据（热搜榜）。

        Returns:
            Dict containing raw API response.
        """
        import httpx

        data_key = self._board_config.get("data_key")
        headers = self._build_headers()

        # 添加请求延迟
        await self._request_delay()

        self.logger.info(f"Fetching hot search data from {WEIBO_HOT_SEARCH_API}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    WEIBO_HOT_SEARCH_API,
                    headers=headers,
                    follow_redirects=True,
                )

                if response.status_code == 429:
                    self.logger.warning("Rate limited by Weibo API")
                    raise RuntimeError("Rate limited by Weibo API")

                response.raise_for_status()
                data = response.json()

                if not data.get("ok"):
                    self.logger.error(f"Weibo API returned error: {data}")
                    raise RuntimeError(f"Weibo API error: {data}")

                items_count = len(data.get("data", {}).get(data_key, []))
                self.logger.info(f"Successfully fetched {items_count} items from public API")
                return data

        except Exception as e:
            self.logger.error(f"Failed to fetch from public API: {e}")
            raise

    async def _fetch_with_auth(self) -> Dict[str, Any]:
        """Fetch data from authenticated API (requires login cookie).

        从需要认证的接口获取数据（其他榜单）。

        Returns:
            Dict containing raw API response.
        """
        import httpx

        # 检查是否配置了 Cookie
        if not self.cookie:
            self.logger.warning(
                f"Board '{self.source_id}' requires authentication, "
                f"but no cookie is configured. Skipping."
            )
            return {"ok": False, "data": {}, "error": "Authentication required, no cookie configured"}

        data_key = self._board_config.get("data_key")
        headers = self._build_headers(with_cookie=True)

        # 添加请求延迟
        await self._request_delay()

        # 构建带参数的 URL
        params = {"band": self.source_id}
        self.logger.info(f"Fetching {self.source_id} data from {WEIBO_HOTBAND_API}")

        try:
            # 创建带有 Cookie 的客户端
            cookies = self._parse_cookie_string(self.cookie)

            async with httpx.AsyncClient(
                timeout=self.timeout,
                cookies=cookies,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    WEIBO_HOTBAND_API,
                    headers=headers,
                    params=params,
                )

                if response.status_code == 429:
                    self.logger.warning("Rate limited by Weibo API")
                    raise RuntimeError("Rate limited by Weibo API")

                response.raise_for_status()
                data = response.json()

                # 检查是否返回了登录重定向
                if "url" in data and "login" in data.get("url", ""):
                    self.logger.error(
                        f"Cookie authentication failed, redirected to login. "
                        f"Please check your WEIBO_COOKIE configuration."
                    )
                    return {"ok": False, "data": {}, "error": "Authentication failed, please check cookie"}

                if not data.get("ok"):
                    self.logger.error(f"Weibo API returned error: {data}")
                    raise RuntimeError(f"Weibo API error: {data}")

                # 检查是否有数据
                items = data.get("data", {}).get(data_key, [])
                items_count = len(items) if isinstance(items, list) else 0

                if items_count == 0:
                    self.logger.warning(f"No items found for board '{self.source_id}'")
                    return {"ok": False, "data": {}, "error": "No data found"}

                self.logger.info(f"Successfully fetched {items_count} items from authenticated API")
                return data

        except Exception as e:
            self.logger.error(f"Failed to fetch from authenticated API: {e}")
            raise

    async def parse(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse raw Weibo API data into article dictionaries.

        将微博 API 原始数据解析为文章字典列表。

        Args:
            raw_data: Raw API response from fetch()

        Returns:
            List of article dictionaries ready for database storage.
        """
        articles = []

        if not raw_data.get("ok"):
            return articles

        # 获取对应榜单的数据键
        data_key = self._board_config.get("data_key")
        if not data_key:
            return articles

        # 提取热搜项
        hot_items = raw_data.get("data", {}).get(data_key, [])

        if not hot_items:
            self.logger.warning(f"No hot search items found for board '{self.source_id}'")
            return articles

        crawl_time = datetime.now(timezone.utc)

        for item in hot_items:
            try:
                # 跳过广告
                if item.get("is_ad") or item.get("topic_ad"):
                    self.logger.debug(f"Skipping ad item: {item.get('word', 'N/A')}")
                    continue

                article = self._parse_hot_item(item, crawl_time)
                if article:
                    articles.append(article)

            except Exception as e:
                self.logger.warning(f"Failed to parse hot search item: {e}")
                continue

        self.logger.info(f"Parsed {len(articles)} articles from Weibo '{self.source_id}'")
        return articles

    def _parse_hot_item(
        self, item: Dict[str, Any], crawl_time: datetime
    ) -> Optional[Dict[str, Any]]:
        """Parse a single hot search item into an article dictionary.

        解析单条热搜数据为文章字典。

        Args:
            item: Single hot search item from API
            crawl_time: Crawl timestamp

        Returns:
            Article dictionary or None if parsing fails.
        """
        # 提取核心字段
        word = item.get("word", "") or item.get("name", "")  # 不同榜单字段可能不同
        if not word:
            return None

        # 生成外部 ID（使用标题的 MD5）
        external_id = hashlib.md5(word.encode("utf-8")).hexdigest()[:16]

        # 构建搜索 URL
        word_scheme = item.get("word_scheme", word)
        if word_scheme.startswith("#"):
            # 话题搜索
            url = f"https://s.weibo.com/weibo?q={word_scheme}"
        else:
            # 普通关键词搜索
            url = f"https://s.weibo.com/weibo?q={word}"

        # 提取热度信息
        hot_value = item.get("num", 0)
        label = item.get("label_name", "") or item.get("icon_desc", "")
        rank = item.get("realpos") or item.get("rank") or item.get("pos", 0)

        # 构建摘要（包含热度信息）
        summary_parts = []
        if label:
            summary_parts.append(f"[{label}]")
        summary_parts.append(word)
        if hot_value:
            summary_parts.append(f"热度: {hot_value:,}")
        summary = " | ".join(summary_parts)

        # 构建 tags（存储热搜特有数据）
        tags = {
            "hot_rank": rank + 1 if isinstance(rank, int) else 0,
            "hot_value": hot_value,
            "label": label,
            "flag_desc": item.get("flag_desc", ""),
            "topic_flag": item.get("topic_flag", 0),
            "emoticon": item.get("emoticon", ""),
        }

        # 构建文章字典
        article = {
            "external_id": external_id,
            "title": word,
            "url": url,
            "summary": summary,
            "content": "",  # 热搜本身没有详细内容
            "author": "微博热搜",
            "category": self._board_config.get("name", "热搜榜"),
            "tags": tags,  # 使用 tags 字段存储热搜元数据
            "publish_time": crawl_time,
        }

        return article

    def _build_headers(self, with_cookie: bool = False) -> Dict[str, str]:
        """Build request headers for Weibo API.

        构建微博 API 请求头。

        Args:
            with_cookie: Whether to include cookie in headers.

        Returns:
            Headers dictionary.
        """
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        headers = {
            "User-Agent": random.choice(user_agents),
            "Referer": "https://weibo.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://weibo.com",
            "Connection": "keep-alive",
            "X-Requested-With": "XMLHttpRequest",
        }

        # 如果需要认证，添加 Cookie
        if with_cookie and self.cookie:
            headers["Cookie"] = self.cookie

        return headers

    def _parse_cookie_string(self, cookie_str: str) -> Dict[str, str]:
        """Parse cookie string into dictionary.

        将 Cookie 字符串解析为字典。

        Args:
            cookie_str: Cookie string like "SUB=xxx; SUBP=yyy"

        Returns:
            Cookie dictionary.
        """
        cookies = {}
        if not cookie_str:
            return cookies

        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()

        return cookies

    async def _request_delay(self) -> None:
        """Add delay between requests to avoid rate limiting.

        在请求之间添加延迟，避免触发速率限制。
        """
        import asyncio

        # 基础延迟 + 随机抖动
        jitter = random.uniform(0, self.delay_jitter)
        delay = self.delay_base + jitter
        await asyncio.sleep(delay)
