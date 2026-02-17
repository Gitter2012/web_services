# =============================================================================
# 模块: apps/crawler/twitter/__init__.py
# 功能: Twitter 爬虫模块入口
# 架构角色: 导出 TwitterCrawler 类供调度器使用
# =============================================================================

"""Twitter crawler module for ResearchPulse v2."""

from apps.crawler.twitter.crawler import TwitterCrawler

__all__ = ["TwitterCrawler"]
