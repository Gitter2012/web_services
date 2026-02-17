# =============================================================================
# 模块: apps/crawler/reddit/__init__.py
# 功能: Reddit 爬虫模块入口
# 架构角色: 导出 RedditCrawler 类供调度器使用
# =============================================================================

"""Reddit crawler module for ResearchPulse v2."""

from apps.crawler.reddit.crawler import RedditCrawler

__all__ = ["RedditCrawler"]
