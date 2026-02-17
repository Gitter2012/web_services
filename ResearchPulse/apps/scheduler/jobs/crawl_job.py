# ==============================================================================
# 模块: ResearchPulse 文章爬取定时任务
# 作用: 本模块实现了从所有已激活数据源（ArXiv 学术论文、RSS 订阅源、微信公众号）
#       自动抓取最新文章的定时任务逻辑。
# 架构角色: 作为调度器（scheduler）的核心 job 之一，是数据采集流水线的入口，
#           爬取到的文章将进入后续的 AI 处理、嵌入计算、事件聚类等流程。
# 执行方式: 由 APScheduler 按配置的间隔周期（IntervalTrigger）自动触发执行。
# 副作用: 1. 向数据库写入新抓取的文章记录
#         2. 更新 RSS 源的 last_fetched_at 时间戳
#         3. 爬取完成后可能触发邮件通知（管理员报告 + 用户订阅推送）
# ==============================================================================

"""Crawl job for ResearchPulse v2."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from core.database import get_session_factory
# 导入各数据源的模型类，用于查询已激活的爬取目标
from apps.crawler.models import ArxivCategory, RssFeed, WechatAccount, WeiboHotSearch
# 导入具体的爬虫实现类
from apps.crawler.arxiv import ArxivCrawler
from apps.crawler.rss import RssCrawler
from apps.crawler.weibo import WeiboCrawler
from settings import settings

logger = logging.getLogger(__name__)


async def run_crawl_job() -> dict:
    """Crawl all active sources.

    执行一次完整爬取流程，抓取 ArXiv 与 RSS 等数据源的最新内容。

    Returns:
        dict: Crawl summary with counts, errors, and optional notifications.
    """
    # 功能: 执行一次完整的爬取流程，遍历所有已激活的数据源并抓取最新内容
    # 参数: 无（所有配置通过 settings 和数据库获取）
    # 返回值: dict - 包含爬取统计摘要信息（状态、耗时、各源文章数、错误数等）
    # 副作用:
    #   1. 数据库写入: 新抓取的文章 + 更新 RSS 源的 last_fetched_at
    #   2. 网络请求: 访问 ArXiv API 和 RSS 源
    #   3. 可能触发邮件通知发送

    logger.info("Starting crawl job")
    # 记录任务开始时间，用于计算总耗时和确定通知的时间范围
    start_time = datetime.now(timezone.utc)

    # 初始化结果字典，分类记录各数据源的爬取结果
    results = {
        "arxiv": [],      # ArXiv 各分类的爬取结果列表
        "rss": [],        # RSS 各订阅源的爬取结果列表
        "wechat": [],     # 微信公众号的爬取结果列表（当前未实现具体爬取逻辑）
        "weibo": [],      # 微博热搜的爬取结果列表
        "errors": [],     # 所有爬取过程中产生的错误信息
        "total_articles": 0,  # 本次爬取总计保存的文章数量
    }

    # 获取数据库会话工厂，用于创建异步数据库连接
    session_factory = get_session_factory()
    async with session_factory() as session:
        # ---- 第一阶段: 爬取 ArXiv 学术论文 ----
        # 查询所有已激活的 ArXiv 分类（如 cs.AI, cs.CL 等）
        # Crawl arxiv categories
        arxiv_result = await session.execute(
            select(ArxivCategory).where(ArxivCategory.is_active == True)
        )
        arxiv_categories = arxiv_result.scalars().all()

        # 逐个分类进行爬取，每个分类使用独立的爬虫实例
        for category in arxiv_categories:
            try:
                # 为每个分类创建 ArXiv 爬虫实例
                # max_results: 每次爬取的最大论文数量，控制请求量
                # delay_base: 请求间的基础延迟时间，避免触发 ArXiv 的频率限制
                crawler = ArxivCrawler(
                    category=category.code,
                    max_results=50,
                    delay_base=settings.arxiv_delay_base,
                )
                result = await crawler.run()
                results["arxiv"].append(result)
                # 累加保存的文章数，用于最终统计
                results["total_articles"] += result.get("saved_count", 0)
                # 分类之间添加2秒延迟，避免对 ArXiv API 造成过大请求压力
                await asyncio.sleep(2)  # Delay between categories
            except Exception as e:
                # 单个分类爬取失败不影响其他分类，记录错误后继续
                logger.error(f"Arxiv crawl failed for {category.code}: {e}")
                results["errors"].append(f"arxiv:{category.code}: {str(e)}")

        # ---- 第二阶段: 爬取 RSS 订阅源 ----
        # 查询所有已激活的 RSS 订阅源
        # Crawl RSS feeds
        rss_result = await session.execute(
            select(RssFeed).where(RssFeed.is_active == True)
        )
        rss_feeds = rss_result.scalars().all()

        # 逐个订阅源进行爬取
        successful_feed_ids = set()
        for feed in rss_feeds:
            try:
                # 为每个 RSS 源创建爬虫实例
                crawler = RssCrawler(
                    feed_id=str(feed.id),
                    feed_url=feed.feed_url,
                )
                result = await crawler.run()
                results["rss"].append(result)
                results["total_articles"] += result.get("saved_count", 0)
                if result.get("status") == "success":
                    successful_feed_ids.add(feed.id)
                # RSS 源之间添加1秒延迟，比 ArXiv 间隔短因为 RSS 请求通常更轻量
                await asyncio.sleep(1)  # Delay between feeds
            except Exception as e:
                # 同样采用容错策略，单个源失败不影响整体任务
                logger.error(f"RSS crawl failed for {feed.title}: {e}")
                results["errors"].append(f"rss:{feed.id}: {str(e)}")

        # ---- 仅更新成功爬取的 RSS 源的最后抓取时间 ----
        # Update last fetched time for successful feeds
        for feed in rss_feeds:
            if feed.id in successful_feed_ids:
                feed.last_fetched_at = datetime.now(timezone.utc)

        # ---- 第三阶段: 爬取微博热搜榜单 ----
        # 查询所有已激活的微博热搜榜单
        # Crawl Weibo hot search boards
        weibo_result = await session.execute(
            select(WeiboHotSearch).where(WeiboHotSearch.is_active == True)
        )
        weibo_boards = weibo_result.scalars().all()

        successful_board_ids = set()
        for board in weibo_boards:
            try:
                # 为每个榜单创建微博爬虫实例
                crawler = WeiboCrawler(
                    source_id=board.board_type,
                    timeout=settings.weibo_timeout,
                    cookie=settings.weibo_cookie,
                    delay_base=settings.weibo_delay_base,
                    delay_jitter=settings.weibo_delay_jitter,
                )
                result = await crawler.run()
                results["weibo"].append(result)
                results["total_articles"] += result.get("saved_count", 0)
                if result.get("status") == "success":
                    successful_board_ids.add(board.id)
                    # 更新最后抓取时间
                    board.last_fetched_at = datetime.now(timezone.utc)
                # 榜单之间添加延迟，微博反爬较严格
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Weibo crawl failed for {board.board_type}: {e}")
                results["errors"].append(f"weibo:{board.board_type}: {str(e)}")

        # 提交数据库事务，持久化所有更改（新文章 + 更新的时间戳）
        await session.commit()

    # ---- 生成任务执行摘要 ----
    end_time = datetime.now(timezone.utc)
    # 计算整个爬取任务的执行耗时（秒）
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "arxiv_count": len(results["arxiv"]),    # ArXiv 爬取的分类数
        "rss_count": len(results["rss"]),          # RSS 爬取的源数
        "weibo_count": len(results["weibo"]),      # 微博爬取的榜单数
        "error_count": len(results["errors"]),     # 发生的错误总数
        "total_articles": results["total_articles"],  # 总计保存的文章数
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Crawl job completed: {summary}")

    # ---- 第三阶段: 发送管理员爬取完成报告 ----
    # 仅在邮件功能启用且有新文章时才发送管理员报告
    # 用户订阅邮件由独立的 notification_job 定时任务处理
    # Send admin crawl completion report
    if settings.email_enabled and results["total_articles"] > 0:
        try:
            from apps.scheduler.jobs.notification_job import (
                send_crawl_completion_notification,
            )

            await send_crawl_completion_notification(summary)

        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")
            results["errors"].append(f"notification: {str(e)}")

    return summary
