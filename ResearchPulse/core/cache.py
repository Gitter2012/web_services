"""Cache module for ResearchPulse v2.

Provides optional Redis caching with fallback to no-cache.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheBackend:
    """Abstract cache backend."""

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a value in cache with TTL in seconds."""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        """Delete a value from cache."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        raise NotImplementedError

    def clear(self) -> None:
        """Clear all cached values."""
        raise NotImplementedError


class NoCache(CacheBackend):
    """No-op cache implementation when Redis is not available."""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def exists(self, key: str) -> bool:
        return False

    def clear(self) -> None:
        pass


class RedisCache(CacheBackend):
    """Redis cache implementation."""

    def __init__(
        self,
        host: str,
        port: int = 6379,
        password: str = "",
        db: int = 0,
        default_ttl: int = 300,
    ):
        import redis

        self.client = redis.Redis(
            host=host,
            port=port,
            password=password if password else None,
            db=db,
            decode_responses=True,
        )
        self.default_ttl = default_ttl
        logger.info(f"Redis cache initialized: {host}:{port}/{db}")

    def get(self, key: str) -> Optional[Any]:
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Redis get error for key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        try:
            self.client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"Redis set error for key {key}: {e}")

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete error for key {key}: {e}")

    def exists(self, key: str) -> bool:
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists error for key {key}: {e}")
            return False

    def clear(self) -> None:
        try:
            self.client.flushdb()
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")


def get_cache() -> CacheBackend:
    """Get the appropriate cache backend based on configuration."""
    from settings import settings

    if settings.redis_available:
        try:
            return RedisCache(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                db=settings.redis_db,
                default_ttl=settings.cache_default_ttl,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}")
            return NoCache()
    return NoCache()


# Global cache instance (lazy initialization)
_cache_instance: CacheBackend | None = None


def get_cache_instance() -> CacheBackend:
    """Get or create the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = get_cache()
    return _cache_instance


# Convenience proxy object
class CacheProxy:
    """Proxy object that delegates to the actual cache instance."""

    @property
    def _cache(self) -> CacheBackend:
        return get_cache_instance()

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self._cache.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self._cache.delete(key)

    def exists(self, key: str) -> bool:
        return self._cache.exists(key)

    def clear(self) -> None:
        self._cache.clear()


# Global cache proxy
cache = CacheProxy()
