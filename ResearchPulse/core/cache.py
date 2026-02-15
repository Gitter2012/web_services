# =============================================================================
# 缓存模块
# =============================================================================
# 本模块提供 ResearchPulse 项目的缓存功能，支持 Redis 缓存和无缓存两种模式。
# 主要职责：
#   1. 定义缓存后端的抽象接口（CacheBackend），统一缓存操作的 API
#   2. 提供 Redis 缓存实现（RedisCache），支持 TTL 过期机制
#   3. 提供无操作缓存实现（NoCache），作为 Redis 不可用时的降级方案
#   4. 提供全局缓存实例的惰性初始化和代理访问机制
#
# 架构角色：
#   - 作为可选的性能优化层，可被任何需要缓存的模块调用
#   - 通过 CacheProxy 代理对象提供全局统一的缓存访问入口
#   - 支持优雅降级：当 Redis 不可用时自动退化为 NoCache，不影响系统正常运行
#
# 设计决策：
#   - 使用策略模式（Strategy Pattern）：CacheBackend 为抽象策略，
#     RedisCache 和 NoCache 为具体策略，运行时根据配置动态选择
#   - 使用代理模式（Proxy Pattern）：CacheProxy 延迟初始化真实的缓存实例，
#     避免模块加载时就连接 Redis
#   - 所有 Redis 操作都包裹在 try-except 中，确保缓存故障不会导致系统崩溃
#   - 缓存值使用 JSON 序列化存储，支持 Python 基本数据类型
# =============================================================================

"""Cache module for ResearchPulse v2.

Provides optional Redis caching with fallback to no-cache.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheBackend:
    """Abstract cache backend interface.

    Defines the standard cache operations implemented by concrete backends.
    用于统一缓存后端的标准接口。
    """
    # 缓存后端抽象基类，定义了所有缓存实现必须提供的统一接口
    # 子类必须实现以下所有方法，否则调用时会抛出 NotImplementedError

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value.

        Args:
            key: Cache key.

        Returns:
            Optional[Any]: Cached value if present, otherwise ``None``.
        """
        # 根据键名获取缓存值
        # 参数 key：缓存键名
        # 返回值：缓存的值，如果键不存在则返回 None
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a cached value with a TTL.

        Args:
            key: Cache key.
            value: Value to cache (JSON-serializable).
            ttl: Time-to-live in seconds.
        """
        # 设置缓存值，带有 TTL（生存时间）
        # 参数 key：缓存键名
        # 参数 value：要缓存的值（需可 JSON 序列化）
        # 参数 ttl：过期时间，单位为秒，默认 300 秒（5 分钟）
        raise NotImplementedError

    def delete(self, key: str) -> None:
        """Delete a cached value.

        Args:
            key: Cache key to delete.
        """
        # 删除指定键的缓存
        # 参数 key：要删除的缓存键名
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """Check whether a key exists in cache.

        Args:
            key: Cache key to check.

        Returns:
            bool: ``True`` if the key exists, otherwise ``False``.
        """
        # 检查指定键是否存在于缓存中
        # 参数 key：要检查的缓存键名
        # 返回值：True 表示存在，False 表示不存在
        raise NotImplementedError

    def clear(self) -> None:
        """Clear all cached values.

        Warning:
            This removes all keys in the configured cache backend.
            清空缓存会删除当前后端的所有缓存键。
        """
        # 清空所有缓存数据
        # 注意：此操作会删除当前数据库中的所有键值对，使用需谨慎
        raise NotImplementedError


class NoCache(CacheBackend):
    """No-op cache implementation.

    Used when Redis is unavailable or disabled.
    当 Redis 不可用或未配置时使用该实现。
    """
    # 无操作缓存实现：所有操作都是空操作（no-op）
    # 当 Redis 不可用或未配置时使用此实现作为降级方案
    # 系统在没有缓存的情况下仍能正常工作，只是无法享受缓存带来的性能优化

    def get(self, key: str) -> Optional[Any]:
        # 始终返回 None，表示缓存未命中
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        # 不执行任何操作，数据不会被缓存
        pass

    def delete(self, key: str) -> None:
        # 不执行任何操作
        pass

    def exists(self, key: str) -> bool:
        # 始终返回 False，表示键不存在
        return False

    def clear(self) -> None:
        # 不执行任何操作
        pass


class RedisCache(CacheBackend):
    """Redis-backed cache implementation.

    Stores values as JSON strings with TTL support.
    使用 JSON 序列化存储缓存值，并支持 TTL 过期。
    """
    # Redis 缓存实现：基于 Redis 的高性能分布式缓存
    # 支持 TTL 过期机制，值通过 JSON 序列化存储
    # 所有操作都包裹在异常处理中，确保 Redis 故障不会影响业务逻辑

    def __init__(
        self,
        host: str,
        port: int = 6379,
        password: str = "",
        db: int = 0,
        default_ttl: int = 300,
    ):
        """Initialize a Redis cache client.

        Args:
            host: Redis host.
            port: Redis port.
            password: Redis password (empty for none).
            db: Redis database index.
            default_ttl: Default TTL in seconds.
        """
        # 初始化 Redis 缓存实例
        # 参数 host：Redis 服务器地址
        # 参数 port：Redis 服务器端口，默认 6379
        # 参数 password：Redis 连接密码，为空字符串时不使用密码
        # 参数 db：Redis 数据库编号，默认 0
        # 参数 default_ttl：默认缓存过期时间（秒），默认 300 秒
        import redis

        self.client = redis.Redis(
            host=host,
            port=port,
            password=password if password else None,  # 空字符串时传 None，表示无密码
            db=db,
            decode_responses=True,  # 自动将 Redis 返回的字节解码为字符串
        )
        self.default_ttl = default_ttl
        logger.info(f"Redis cache initialized: {host}:{port}/{db}")

    def get(self, key: str) -> Optional[Any]:
        # 从 Redis 中获取缓存值，并将 JSON 字符串反序列化为 Python 对象
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)  # 将 JSON 字符串反序列化
            return None
        except Exception as e:
            # Redis 操作失败时记录警告并返回 None（视为缓存未命中）
            # 这样即使 Redis 出现问题，系统也能继续正常工作
            logger.warning(f"Redis get error for key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        # 将值序列化为 JSON 并存入 Redis，同时设置过期时间
        try:
            # setex：SET with EXpire，原子性地设置值和过期时间
            self.client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            # 缓存写入失败不应中断业务流程，仅记录警告日志
            logger.warning(f"Redis set error for key {key}: {e}")

    def delete(self, key: str) -> None:
        # 从 Redis 中删除指定键
        try:
            self.client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete error for key {key}: {e}")

    def exists(self, key: str) -> bool:
        # 检查键是否存在于 Redis 中
        try:
            # Redis 的 exists 命令返回匹配的键数量，转换为布尔值
            return bool(self.client.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists error for key {key}: {e}")
            return False

    def clear(self) -> None:
        # 清空当前 Redis 数据库中的所有数据
        # 注意：flushdb 只清空当前数据库，不影响其他数据库编号的数据
        try:
            self.client.flushdb()
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")


def get_cache() -> CacheBackend:
    """Select the cache backend based on configuration.

    Returns:
        CacheBackend: Redis cache when available, otherwise a NoCache instance.
    """
    # 根据系统配置选择合适的缓存后端（策略模式）
    # 如果 Redis 可用且配置正确，返回 RedisCache 实例
    # 否则返回 NoCache 实例（优雅降级）
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
            # Redis 初始化失败时降级为无缓存模式，不影响系统启动
            logger.warning(f"Failed to initialize Redis cache: {e}")
            return NoCache()
    # Redis 未配置时直接使用无缓存模式
    return NoCache()


# 全局缓存实例（惰性初始化）
# 使用模块级全局变量实现单例模式，避免重复创建缓存连接
# Global cache instance (lazy initialization)
_cache_instance: CacheBackend | None = None


def get_cache_instance() -> CacheBackend:
    """Get or create the global cache instance.

    Returns:
        CacheBackend: Singleton cache backend instance.
    """
    # 获取或创建全局缓存实例
    # 首次调用时初始化，后续调用直接返回已有实例
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = get_cache()
    return _cache_instance


# =============================================================================
# 缓存代理对象
# =============================================================================
# 使用代理模式封装缓存访问，实现延迟初始化
# 外部模块可以直接导入并使用 cache 对象，无需关心缓存的初始化时机

# Convenience proxy object
class CacheProxy:
    """Proxy object that delegates to the actual cache instance.

    Accesses the singleton cache lazily on first use.
    通过惰性加载获取全局缓存实例。
    """
    # 缓存代理类：将所有操作委托给实际的缓存后端实例
    # 通过 @property 实现延迟初始化，只有在首次实际使用缓存时才会创建连接
    # 这避免了在模块导入时就尝试连接 Redis

    @property
    def _cache(self) -> CacheBackend:
        """Return the underlying cache backend instance."""
        # 获取实际的缓存后端实例（惰性加载）
        return get_cache_instance()

    def get(self, key: str) -> Optional[Any]:
        """Proxy get operation.

        Args:
            key: Cache key.

        Returns:
            Optional[Any]: Cached value if present.
        """
        # 代理 get 操作到实际的缓存后端
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Proxy set operation.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds.
        """
        # 代理 set 操作到实际的缓存后端
        self._cache.set(key, value, ttl)

    def delete(self, key: str) -> None:
        """Proxy delete operation.

        Args:
            key: Cache key.
        """
        # 代理 delete 操作到实际的缓存后端
        self._cache.delete(key)

    def exists(self, key: str) -> bool:
        """Proxy exists operation.

        Args:
            key: Cache key.

        Returns:
            bool: ``True`` if key exists.
        """
        # 代理 exists 操作到实际的缓存后端
        return self._cache.exists(key)

    def clear(self) -> None:
        """Proxy clear operation."""
        # 代理 clear 操作到实际的缓存后端
        self._cache.clear()


# 全局缓存代理实例
# 其他模块可以直接导入使用：from core.cache import cache
# 使用示例：cache.get("key")、cache.set("key", value, ttl=60)
# Global cache proxy
cache = CacheProxy()
