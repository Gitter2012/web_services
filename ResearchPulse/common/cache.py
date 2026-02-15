# =============================================================================
# 模块: common/cache.py
# 功能: 简单的内存级 HTTP 响应缓存，带 TTL（存活时间）支持
# 架构角色: 作为 HTTP 请求层（common/http.py）的缓存基础设施。
#   当爬虫在短时间内重复请求相同 URL 时（如重试、去重检查），
#   通过缓存避免不必要的网络请求，降低被目标网站封禁的风险。
#
# 设计决策:
#   - 使用纯内存字典存储（dict[str, tuple[str, float]]），简单高效
#   - 缓存键使用 URL + 参数的 MD5 哈希，节省内存且避免特殊字符问题
#   - 每条缓存条目独立计算 TTL（按条目创建时间 + 查询时传入的 TTL 判断）
#   - 过期条目在查询时惰性删除（Lazy Eviction），不需要后台清理线程
#   - 使用模块级单例实例（_cache），并提供模块级便捷函数
#   - 不使用 Redis 等外部存储，因为缓存的主要目的是短时间内的请求去重
# =============================================================================
"""Simple in-memory HTTP response cache with TTL."""

from __future__ import annotations

import hashlib
import time
from typing import Optional


# =============================================================================
# ResponseCache 类
# 职责: 管理 URL 响应的内存缓存
# 设计决策:
#   - 缓存结构：{md5_hash: (响应文本, 创建时间戳)}
#   - TTL 在读取时传入而非写入时指定，这样同一缓存条目可以被不同 TTL 的调用者使用
#   - 惰性过期：过期条目只在被查询时才删除，简化了实现
# =============================================================================
class ResponseCache:
    """Simple dict-based response cache with per-entry TTL."""

    # 最大缓存条目数，防止无限制的内存增长
    MAX_ENTRIES = 500

    def __init__(self):
        # 缓存存储：键为 URL+参数的 MD5 哈希，值为 (响应文本, 写入时间戳) 元组
        self._cache: dict[str, tuple[str, float]] = {}

    def _cache_key(self, url: str, params: Optional[dict] = None) -> str:
        """Generate cache key from URL and params.

        根据 URL 和查询参数生成缓存键。
        使用 MD5 哈希将任意长度的 URL+参数组合压缩为固定长度的键。

        Args:
            url: Request URL.
            params: Optional query parameters.

        Returns:
            str: 32-character MD5 hash key.
        """
        key_str = url
        if params:
            # 参数按键名排序后拼接，确保相同参数不同顺序生成相同的缓存键
            sorted_params = "&".join(
                f"{k}={v}" for k, v in sorted(params.items())
            )
            key_str = f"{url}?{sorted_params}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, url: str, params: Optional[dict] = None, ttl: int = 3600) -> Optional[str]:
        """Get cached response if not expired.

        获取缓存的响应内容（如果未过期）。过期条目会被惰性删除。

        Args:
            url: Request URL.
            params: Optional query parameters.
            ttl: Cache TTL in seconds.

        Returns:
            Optional[str]: Cached response text if available.
        """
        key = self._cache_key(url, params)
        if key not in self._cache:
            return None
        response, timestamp = self._cache[key]
        # 检查是否过期
        if time.time() - timestamp > ttl:
            # 惰性删除过期条目
            del self._cache[key]
            return None
        return response

    def set(self, url: str, response: str, params: Optional[dict] = None) -> None:
        """Cache a response.

        缓存一个 HTTP 响应并记录时间戳，用于 TTL 过期判断。

        Args:
            url: Request URL.
            response: Response text.
            params: Optional query parameters.

        Side Effects:
            - Writes/overwrites cache entry.
            - May evict the oldest entry when capacity is exceeded.
        """
        key = self._cache_key(url, params)
        self._cache[key] = (response, time.time())
        # 淘汰最旧的条目以维持大小限制
        if len(self._cache) > self.MAX_ENTRIES:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

    def clear(self) -> None:
        """Clear all cached responses.

        清空所有缓存条目。
        """
        self._cache.clear()

    def size(self) -> int:
        """Return number of cached entries.

        返回当前缓存中的条目数量（包括可能已过期但尚未被惰性删除的条目）。

        Returns:
            int: Number of cached entries.
        """
        return len(self._cache)


# 全局缓存单例实例
# 被 http.py 模块通过下方的便捷函数调用
_cache = ResponseCache()


def get_cached_response(
    url: str, params: Optional[dict] = None, ttl: int = 3600
) -> Optional[str]:
    """Get response from cache.

    从全局缓存中获取响应。

    Args:
        url: Request URL.
        params: Optional query parameters.
        ttl: Cache TTL in seconds.

    Returns:
        Optional[str]: Cached response text or ``None``.
    """
    return _cache.get(url, params, ttl)


def cache_response(
    url: str, response: str, params: Optional[dict] = None
) -> None:
    """Store response in cache.

    将响应存入全局缓存。

    Args:
        url: Request URL.
        response: Response text.
        params: Optional query parameters.
    """
    _cache.set(url, response, params)


def clear_cache() -> None:
    """Clear all cached responses.

    清空全局缓存中的所有条目。
    """
    _cache.clear()


def cache_size() -> int:
    """Get cache size.

    获取全局缓存中的条目数量。

    Returns:
        int: Cache entry count.
    """
    return _cache.size()
