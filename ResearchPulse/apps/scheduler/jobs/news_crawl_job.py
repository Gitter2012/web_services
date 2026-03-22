# =============================================================================
# 模块: apps/scheduler/jobs/news_crawl_job.py
# 功能: 中文官方媒体新闻爬取定时任务
# 架构角色: 作为调度器的 job 之一，专门负责 cn_news 类型源的定时爬取
# 执行方式: 由 APScheduler 按配置的间隔周期（默认每6小时）自动触发
# 设计原因: cn_news 源需要独立于通用 crawl_job 调度（间隔不同、反爬策略不同）
# =============================================================================

"""News crawl job for ResearchPulse v2."""

from __future__ import annotations

import logging

from apps.crawler import CrawlerRunner

logger = logging.getLogger(__name__)


async def run_news_crawl_job() -> dict:
    """Crawl Chinese official media news sources (cn_news type).

    执行中文官方媒体新闻爬取任务，仅抓取 cn_news 源类型。

    Returns:
        dict: Crawl summary with counts and errors.
    """
    logger.info("Starting news crawl job (cn_news sources)")

    runner = CrawlerRunner()
    summary = await runner.run_all(source_types=["cn_news"])

    result = summary.to_dict()
    logger.info(f"News crawl job completed: {result}")

    return result
