# =============================================================================
# 模块: common/wechat_mp/token_manager.py
# 功能: 微信公众号 Access Token 缓存管理
# 架构角色: 管理微信 API access_token 的获取和缓存
# 设计决策:
#   1. access_token 有效期 2 小时（7200 秒），使用内存缓存避免频繁请求
#   2. 缓存 TTL 设为 7000 秒（预留 200 秒安全边际）
#   3. 使用 asyncio.Lock 保证并发安全，避免多次同时刷新 token
#   4. 支持强制刷新，用于 token 失效后的重试场景
# =============================================================================

"""WeChat MP Access Token manager with caching."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from common.wechat_mp.client import WeChatMPClient

logger = logging.getLogger(__name__)


class TokenManager:
    """Access Token manager with automatic caching and refresh.

    微信公众号 access_token 管理器。

    access_token 是调用微信 API 的凭证，有效期 2 小时（7200 秒）。
    本管理器负责：
    1. 缓存 token，避免每次 API 调用都请求新 token
    2. 自动检测 token 过期并刷新
    3. 并发安全：多个协程同时请求 token 时只发起一次刷新

    Attributes:
        _token: 当前缓存的 access_token
        _expires_at: token 过期时间戳（Unix 秒）
        _lock: 异步锁，保证并发刷新安全
    """

    # 默认缓存 TTL（秒）：7000 秒 ≈ 116 分钟
    # 微信 access_token 有效期 7200 秒，预留 200 秒安全边际
    DEFAULT_CACHE_TTL = 7000

    def __init__(self, client: WeChatMPClient, cache_ttl: int = DEFAULT_CACHE_TTL):
        """Initialize TokenManager.

        Args:
            client: WeChatMPClient instance for fetching tokens.
            cache_ttl: Cache TTL in seconds (default 7000s).
        """
        self._client = client
        self._cache_ttl = cache_ttl
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock: Optional[asyncio.Lock] = None  # Lazy-initialized per event loop

    @property
    def is_valid(self) -> bool:
        """Check if the cached token is still valid.

        判断缓存的 token 是否仍在有效期内。
        """
        return bool(self._token and time.time() < self._expires_at)

    async def get_valid_token(self, force_refresh: bool = False) -> str:
        """Get a valid access_token, refreshing if necessary.

        获取有效的 access_token。如果缓存有效则直接返回，否则自动刷新。

        Args:
            force_refresh: Force refresh even if cached token is valid.

        Returns:
            Valid access_token string.

        Raises:
            WeChatAPIError: If token fetch fails.
        """
        # 快速路径：缓存有效且不强制刷新
        if self.is_valid and not force_refresh:
            return self._token  # type: ignore

        # 慢路径：需要刷新 token，使用锁保证并发安全
        # 延迟初始化锁以支持多事件循环场景
        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            # 二次检查：可能在等待锁时已被其他协程刷新
            if self.is_valid and not force_refresh:
                return self._token  # type: ignore

            logger.info("Refreshing WeChat MP access_token...")
            token_data = await self._client.fetch_access_token()

            self._token = token_data["access_token"]
            # 使用配置的 TTL 而非 API 返回的 expires_in，更保守
            expires_in = min(token_data.get("expires_in", 7200), self._cache_ttl)
            self._expires_at = time.time() + expires_in

            logger.info(
                "WeChat MP access_token refreshed, expires in %d seconds",
                expires_in,
            )
            return self._token

    def invalidate(self) -> None:
        """Invalidate the cached token.

        手动使缓存的 token 失效，下次调用 get_valid_token 时将强制刷新。
        用于收到微信 API 返回 token 过期错误（errcode=42001）时。
        """
        self._token = None
        self._expires_at = 0.0
        logger.info("WeChat MP access_token cache invalidated")
