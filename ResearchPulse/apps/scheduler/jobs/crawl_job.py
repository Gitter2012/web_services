# ==============================================================================
# 模块: ResearchPulse 文章爬取定时任务
# 作用: 本模块实现了从所有已激活数据源自动抓取最新文章的定时任务逻辑。
# 架构角色: 作为调度器（scheduler）的核心 job 之一，是数据采集流水线的入口，
#           爬取到的文章将进入后续的 AI 处理、嵌入计算、事件聚类等流程。
# 执行方式: 由 APScheduler 按配置的间隔周期（IntervalTrigger）自动触发执行。
# 副作用: 1. 向数据库写入新抓取的文章记录
#         2. 更新数据源的 last_fetched_at 时间戳
#         3. 爬取完成后可能触发邮件通知（管理员报告 + 用户订阅推送）
# ==============================================================================

"""Crawl job for ResearchPulse v2."""

from __future__ import annotations

import logging

from apps.crawler import CrawlerRunner
from settings import settings

logger = logging.getLogger(__name__)


async def run_crawl_job() -> dict:
    """Crawl all active sources.

    执行一次完整爬取流程，抓取所有已激活数据源的最新内容。

    Returns:
        dict: Crawl summary with counts, errors, and optional notifications.
    """
    logger.info("Starting crawl job")

    # 创建爬取运行器并执行全量爬取
    runner = CrawlerRunner()
    summary = await runner.run_all()

    # 构建返回结果
    result = summary.to_dict()

    logger.info(f"Crawl job completed: {result}")

    # ---- 发送管理员爬取完成报告 ----
    # 仅在邮件功能启用且有新文章时才发送管理员报告
    # 用户订阅邮件由独立的 notification_job 定时任务处理
    if settings.email_enabled and summary.total_articles > 0:
        try:
            from apps.scheduler.jobs.notification_job import (
                send_crawl_completion_notification,
            )

            await send_crawl_completion_notification(result)

        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")

    return result
