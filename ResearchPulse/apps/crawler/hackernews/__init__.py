# =============================================================================
# 模块: apps/crawler/hackernews/__init__.py
# 功能: HackerNews 爬虫模块入口
# 架构角色: 导出 HackerNewsCrawler 类供调度器使用
# =============================================================================

"""HackerNews crawler module for ResearchPulse v2."""

from apps.crawler.hackernews.crawler import HackerNewsCrawler

__all__ = ["HackerNewsCrawler"]
