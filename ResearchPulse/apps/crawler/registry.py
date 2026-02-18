# =============================================================================
# 模块: apps/crawler/registry.py
# 功能: 爬虫注册表，管理所有已注册的爬虫类型和数据源模型映射
# 架构角色: 提供统一的爬虫注册机制，实现配置驱动的爬虫管理
# 设计理念:
#   1. 使用注册表模式（Registry Pattern）解耦爬虫定义与使用
#   2. 支持装饰器方式自动注册，添加新爬虫无需修改其他文件
#   3. 维护爬虫类与数据源模型的映射关系，便于动态查询
# =============================================================================

"""Crawler registry for managing registered crawler types.

This module provides a central registry for all crawler implementations,
enabling dynamic crawler discovery and instantiation.

Usage:
    # Register a crawler with decorator
    @CrawlerRegistry.register("arxiv", model=ArxivCategory)
    class ArxivCrawler(BaseCrawler):
        ...

    # Get registered crawler class
    crawler_class = CrawlerRegistry.get_crawler_class("arxiv")

    # List all registered sources
    sources = CrawlerRegistry.list_sources()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from apps.crawler.base import BaseCrawler

logger = logging.getLogger(__name__)


@dataclass
class CrawlerConfig:
    """Configuration for a crawler type.

    爬虫类型配置，包含创建爬虫实例所需的所有信息。

    Attributes:
        source_type: Source type identifier (e.g., 'arxiv', 'rss')
        crawler_class: The crawler class implementation
        model_class: SQLAlchemy model for the source configuration
        config_builder: Function to build crawler config from source model
        priority: Execution priority (lower = higher priority)
        enabled: Whether this crawler type is enabled
    """
    source_type: str
    crawler_class: Type[BaseCrawler]
    model_class: Optional[Type] = None
    config_builder: Optional[Callable[[Any], Dict[str, Any]]] = None
    priority: int = 100
    enabled: bool = True


class CrawlerRegistry:
    """Central registry for all crawler types.

    爬虫注册表，采用类级别的存储实现全局单例效果。
    支持装饰器注册和手动注册两种方式。

    Example:
        # 方式一：装饰器注册
        @CrawlerRegistry.register("arxiv", model=ArxivCategory)
        class ArxivCrawler(BaseCrawler):
            source_type = "arxiv"

        # 方式二：手动注册
        CrawlerRegistry.register_manual("rss", RssCrawler, model=RssFeed)

        # 获取爬虫类
        cls = CrawlerRegistry.get_crawler_class("arxiv")

        # 获取所有源类型
        types = CrawlerRegistry.list_sources()
    """

    # 类级别存储，保存所有注册的爬虫配置
    _configs: Dict[str, CrawlerConfig] = {}

    @classmethod
    def register(
        cls,
        source_type: str,
        model: Optional[Type] = None,
        config_builder: Optional[Callable[[Any], Dict[str, Any]]] = None,
        priority: int = 100,
    ) -> Callable[[Type[BaseCrawler]], Type[BaseCrawler]]:
        """Decorator to register a crawler class.

        装饰器：注册爬虫类到注册表。

        Args:
            source_type: Unique source type identifier
            model: SQLAlchemy model class for source configuration
            config_builder: Optional function to build config from model instance
            priority: Execution priority (lower = higher priority)

        Returns:
            Decorator function

        Example:
            @CrawlerRegistry.register("arxiv", model=ArxivCategory, priority=10)
            class ArxivCrawler(BaseCrawler):
                ...
        """
        def decorator(crawler_class: Type[BaseCrawler]) -> Type[BaseCrawler]:
            cls._configs[source_type] = CrawlerConfig(
                source_type=source_type,
                crawler_class=crawler_class,
                model_class=model,
                config_builder=config_builder,
                priority=priority,
            )
            logger.debug(f"Registered crawler: {source_type} -> {crawler_class.__name__}")
            return crawler_class
        return decorator

    @classmethod
    def register_manual(
        cls,
        source_type: str,
        crawler_class: Type[BaseCrawler],
        model: Optional[Type] = None,
        config_builder: Optional[Callable[[Any], Dict[str, Any]]] = None,
        priority: int = 100,
    ) -> None:
        """Manually register a crawler class.

        手动注册爬虫类到注册表（非装饰器方式）。

        Args:
            source_type: Unique source type identifier
            crawler_class: The crawler class to register
            model: SQLAlchemy model class for source configuration
            config_builder: Optional function to build config from model instance
            priority: Execution priority (lower = higher priority)
        """
        cls._configs[source_type] = CrawlerConfig(
            source_type=source_type,
            crawler_class=crawler_class,
            model_class=model,
            config_builder=config_builder,
            priority=priority,
        )
        logger.debug(f"Manually registered crawler: {source_type} -> {crawler_class.__name__}")

    @classmethod
    def unregister(cls, source_type: str) -> bool:
        """Unregister a crawler type.

        从注册表移除爬虫类型。

        Args:
            source_type: Source type to unregister

        Returns:
            True if unregistered, False if not found
        """
        if source_type in cls._configs:
            del cls._configs[source_type]
            logger.debug(f"Unregistered crawler: {source_type}")
            return True
        return False

    @classmethod
    def get_crawler_class(cls, source_type: str) -> Optional[Type[BaseCrawler]]:
        """Get the crawler class for a source type.

        获取指定源类型的爬虫类。

        Args:
            source_type: Source type identifier

        Returns:
            Crawler class or None if not found
        """
        config = cls._configs.get(source_type)
        return config.crawler_class if config else None

    @classmethod
    def get_config(cls, source_type: str) -> Optional[CrawlerConfig]:
        """Get the full configuration for a source type.

        获取指定源类型的完整配置。

        Args:
            source_type: Source type identifier

        Returns:
            CrawlerConfig or None if not found
        """
        return cls._configs.get(source_type)

    @classmethod
    def get_model_class(cls, source_type: str) -> Optional[Type]:
        """Get the source model class for a source type.

        获取指定源类型对应的数据源模型类。

        Args:
            source_type: Source type identifier

        Returns:
            Model class or None if not found
        """
        config = cls._configs.get(source_type)
        return config.model_class if config else None

    @classmethod
    def get_config_builder(cls, source_type: str) -> Optional[Callable[[Any], Dict[str, Any]]]:
        """Get the config builder function for a source type.

        获取指定源类型的配置构建函数。

        Args:
            source_type: Source type identifier

        Returns:
            Config builder function or None
        """
        config = cls._configs.get(source_type)
        return config.config_builder if config else None

    @classmethod
    def list_sources(cls, enabled_only: bool = True) -> List[str]:
        """List all registered source types.

        列出所有已注册的源类型。

        Args:
            enabled_only: If True, only return enabled sources

        Returns:
            List of source type identifiers, sorted by priority
        """
        configs = [
            (source_type, config)
            for source_type, config in cls._configs.items()
            if not enabled_only or config.enabled
        ]
        # 按优先级排序（数字小的优先）
        configs.sort(key=lambda x: x[1].priority)
        return [source_type for source_type, _ in configs]

    @classmethod
    def is_registered(cls, source_type: str) -> bool:
        """Check if a source type is registered.

        检查源类型是否已注册。

        Args:
            source_type: Source type identifier

        Returns:
            True if registered
        """
        return source_type in cls._configs

    @classmethod
    def enable(cls, source_type: str) -> bool:
        """Enable a crawler type.

        启用指定的爬虫类型。

        Args:
            source_type: Source type identifier

        Returns:
            True if enabled, False if not found
        """
        config = cls._configs.get(source_type)
        if config:
            config.enabled = True
            return True
        return False

    @classmethod
    def disable(cls, source_type: str) -> bool:
        """Disable a crawler type.

        禁用指定的爬虫类型。

        Args:
            source_type: Source type identifier

        Returns:
            True if disabled, False if not found
        """
        config = cls._configs.get(source_type)
        if config:
            config.enabled = False
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """Clear all registered crawlers.

        清空所有已注册的爬虫（主要用于测试）。
        """
        cls._configs.clear()
        logger.debug("Cleared all registered crawlers")

    @classmethod
    def get_all_configs(cls) -> Dict[str, CrawlerConfig]:
        """Get all registered configurations.

        获取所有已注册的配置（只读）。

        Returns:
            Copy of all configurations
        """
        return cls._configs.copy()
