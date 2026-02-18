# =============================================================================
# 模块: apps/crawler/factory.py
# 功能: 爬虫工厂，根据配置创建爬虫实例
# 架构角色: 封装爬虫实例化逻辑，支持动态创建和批量创建
# 设计理念:
#   1. 工厂模式（Factory Pattern）解耦爬虫创建与使用
#   2. 支持单个创建和批量创建激活源的爬虫
#   3. 自动处理配置构建和依赖注入
# =============================================================================

"""Crawler factory for creating crawler instances.

This module provides factory methods for creating crawler instances
based on source type and configuration.

Usage:
    # Create a single crawler
    crawler = await CrawlerFactory.create("arxiv", category="cs.AI")

    # Create crawlers for all active sources
    async for crawler, source in CrawlerFactory.create_for_active_sources():
        result = await crawler.run()
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.base import BaseCrawler
from apps.crawler.registry import CrawlerRegistry
from core.database import get_session_factory

logger = logging.getLogger(__name__)


class CrawlerFactory:
    """Factory for creating crawler instances.

    爬虫工厂类，提供静态方法创建爬虫实例。

    Features:
        - 根据 source_type 动态创建爬虫实例
        - 支持批量创建所有激活源的爬虫
        - 自动构建配置参数
    """

    @staticmethod
    def create_sync(source_type: str, **kwargs) -> BaseCrawler:
        """Create a crawler instance synchronously.

        同步创建爬虫实例。

        Args:
            source_type: Source type identifier (e.g., 'arxiv', 'rss')
            **kwargs: Arguments passed to the crawler constructor

        Returns:
            Crawler instance

        Raises:
            ValueError: If source type is not registered
        """
        crawler_class = CrawlerRegistry.get_crawler_class(source_type)
        if not crawler_class:
            raise ValueError(f"Unknown source type: {source_type}")

        return crawler_class(**kwargs)

    @staticmethod
    async def create(source_type: str, **kwargs) -> BaseCrawler:
        """Create a crawler instance asynchronously.

        异步创建爬虫实例（保持接口一致性）。

        Args:
            source_type: Source type identifier
            **kwargs: Arguments passed to the crawler constructor

        Returns:
            Crawler instance

        Raises:
            ValueError: If source type is not registered
        """
        return CrawlerFactory.create_sync(source_type, **kwargs)

    @staticmethod
    async def create_from_source(source_type: str, source: Any) -> BaseCrawler:
        """Create a crawler instance from a source model instance.

        根据数据源模型实例创建爬虫。

        Args:
            source_type: Source type identifier
            source: Source model instance (e.g., ArxivCategory, RssFeed)

        Returns:
            Crawler instance

        Raises:
            ValueError: If source type is not registered or config builder fails
        """
        crawler_class = CrawlerRegistry.get_crawler_class(source_type)
        if not crawler_class:
            raise ValueError(f"Unknown source type: {source_type}")

        # 获取配置构建器
        config_builder = CrawlerRegistry.get_config_builder(source_type)

        if config_builder:
            # 使用自定义配置构建器
            config = config_builder(source)
        else:
            # 使用默认配置构建逻辑
            config = CrawlerFactory._build_default_config(source_type, source)

        return crawler_class(**config)

    @staticmethod
    def _build_default_config(source_type: str, source: Any) -> Dict[str, Any]:
        """Build default configuration from source model.

        根据数据源模型构建默认配置。

        Args:
            source_type: Source type identifier
            source: Source model instance

        Returns:
            Configuration dictionary
        """
        # 各数据源的默认配置映射
        # 子类或注册时可以提供自定义的 config_builder 覆盖此逻辑
        config = {}

        # 通用字段
        if hasattr(source, 'code'):
            config['category'] = source.code
        if hasattr(source, 'feed_url'):
            config['feed_url'] = source.feed_url
        if hasattr(source, 'id'):
            config['feed_id'] = str(source.id)
        if hasattr(source, 'feed_type'):
            config['feed_type'] = source.feed_type
        if hasattr(source, 'source_type'):
            config['source_type'] = source.source_type
        if hasattr(source, 'source_name'):
            config['source_name'] = source.source_name
        if hasattr(source, 'username'):
            config['username'] = source.username
        if hasattr(source, 'board_type'):
            config['source_id'] = source.board_type

        return config

    @staticmethod
    async def create_for_active_sources(
        source_types: Optional[List[str]] = None,
        session: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[Tuple[BaseCrawler, Any], None]:
        """Create crawler instances for all active sources.

        为所有激活的数据源创建爬虫实例。

        Args:
            source_types: Optional list of source types to limit creation.
                         If None, create for all registered types.
            session: Optional database session. If None, creates a new one.

        Yields:
            Tuple of (crawler_instance, source_model_instance)
        """
        # 获取要处理的源类型
        types_to_process = source_types or CrawlerRegistry.list_sources(enabled_only=True)

        # 是否需要管理 session
        own_session = session is None
        session_factory = get_session_factory()

        if own_session:
            session_ctx = session_factory()
            session = await session_ctx.__aenter__()

        try:
            for source_type in types_to_process:
                # 获取该源类型对应的模型类
                model_class = CrawlerRegistry.get_model_class(source_type)
                if not model_class:
                    logger.debug(f"No model class for source type: {source_type}")
                    continue

                # 查询激活的数据源
                try:
                    result = await session.execute(
                        select(model_class).where(model_class.is_active == True)
                    )
                    sources = result.scalars().all()

                    for source in sources:
                        try:
                            crawler = await CrawlerFactory.create_from_source(
                                source_type, source
                            )
                            yield crawler, source
                        except Exception as e:
                            logger.error(
                                f"Failed to create crawler for {source_type}/{getattr(source, 'id', 'unknown')}: {e}"
                            )
                except Exception as e:
                    logger.error(f"Failed to query sources for {source_type}: {e}")

        finally:
            if own_session:
                await session_ctx.__aexit__(None, None, None)

    @staticmethod
    async def get_active_sources_count(
        source_types: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """Get count of active sources for each source type.

        获取每种源类型的激活源数量。

        Args:
            source_types: Optional list of source types to limit query

        Returns:
            Dictionary mapping source_type to count
        """
        types_to_process = source_types or CrawlerRegistry.list_sources(enabled_only=True)
        counts = {}

        session_factory = get_session_factory()
        async with session_factory() as session:
            for source_type in types_to_process:
                model_class = CrawlerRegistry.get_model_class(source_type)
                if not model_class:
                    continue

                try:
                    result = await session.execute(
                        select(model_class).where(model_class.is_active == True)
                    )
                    sources = result.scalars().all()
                    counts[source_type] = len(sources)
                except Exception as e:
                    logger.error(f"Failed to count sources for {source_type}: {e}")
                    counts[source_type] = 0

        return counts
