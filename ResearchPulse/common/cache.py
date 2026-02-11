"""Simple in-memory HTTP response cache with TTL."""

from __future__ import annotations

import hashlib
import time
from typing import Optional


class ResponseCache:
    """Simple dict-based response cache with per-entry TTL."""

    def __init__(self):
        self._cache: dict[str, tuple[str, float]] = {}

    def _cache_key(self, url: str, params: Optional[dict] = None) -> str:
        """Generate cache key from URL and params."""
        key_str = url
        if params:
            sorted_params = "&".join(
                f"{k}={v}" for k, v in sorted(params.items())
            )
            key_str = f"{url}?{sorted_params}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, url: str, params: Optional[dict] = None, ttl: int = 3600) -> Optional[str]:
        """Get cached response if not expired."""
        key = self._cache_key(url, params)
        if key not in self._cache:
            return None
        response, timestamp = self._cache[key]
        if time.time() - timestamp > ttl:
            del self._cache[key]
            return None
        return response

    def set(self, url: str, response: str, params: Optional[dict] = None) -> None:
        """Cache a response."""
        key = self._cache_key(url, params)
        self._cache[key] = (response, time.time())

    def clear(self) -> None:
        """Clear all cached responses."""
        self._cache.clear()

    def size(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)


# Global cache instance
_cache = ResponseCache()


def get_cached_response(
    url: str, params: Optional[dict] = None, ttl: int = 3600
) -> Optional[str]:
    """Get response from cache."""
    return _cache.get(url, params, ttl)


def cache_response(
    url: str, response: str, params: Optional[dict] = None
) -> None:
    """Store response in cache."""
    _cache.set(url, response, params)


def clear_cache() -> None:
    """Clear all cached responses."""
    _cache.clear()


def cache_size() -> int:
    """Get cache size."""
    return _cache.size()
