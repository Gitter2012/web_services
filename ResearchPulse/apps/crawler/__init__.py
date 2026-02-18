# =============================================================================
# 模块: apps/crawler/__init__.py
# 功能: 爬虫模块包入口，导出核心组件
# 架构角色: 提供统一的导入接口，隐藏内部实现细节
# =============================================================================

"""Crawler module for ResearchPulse v2.

This module provides a complete crawler system with:
- BaseCrawler: Abstract base class for all crawlers
- CrawlerRegistry: Central registry for crawler types
- CrawlerFactory: Factory for creating crawler instances
- CrawlerRunner: Unified runner for executing crawls

Usage:
    # Import base class for creating new crawlers
    from apps.crawler import BaseCrawler, CrawlerRegistry

    # Import factory and runner for executing crawls
    from apps.crawler import CrawlerFactory, CrawlerRunner

    # Register a new crawler
    @CrawlerRegistry.register("my_source", model=MySourceModel)
    class MyCrawler(BaseCrawler):
        ...

    # Run crawlers
    runner = CrawlerRunner()
    result = await runner.run_source("my_source", param1="value1")
"""

from apps.crawler.base import BaseCrawler
from apps.crawler.registry import CrawlerRegistry
from apps.crawler.factory import CrawlerFactory
from apps.crawler.runner import CrawlerRunner, CrawlResult, CrawlSummary

__all__ = [
    # Core components
    "BaseCrawler",
    "CrawlerRegistry",
    "CrawlerFactory",
    "CrawlerRunner",
    # Result types
    "CrawlResult",
    "CrawlSummary",
]

# =============================================================================
# 自动导入所有爬虫实现类以触发注册
# Auto-import all crawler implementations to trigger registration
# =============================================================================
# 注意：导入语句放在末尾，避免循环导入问题
# Note: Imports at the end to avoid circular import issues
from apps.crawler.arxiv import ArxivCrawler
from apps.crawler.rss import RssCrawler
from apps.crawler.weibo import WeiboCrawler
from apps.crawler.hackernews import HackerNewsCrawler
from apps.crawler.reddit import RedditCrawler
from apps.crawler.twitter import TwitterCrawler

__all__.extend([
    "ArxivCrawler",
    "RssCrawler",
    "WeiboCrawler",
    "HackerNewsCrawler",
    "RedditCrawler",
    "TwitterCrawler",
])
