# ==============================================================================
# 模块: ResearchPulse 调度任务注册与管理模块
# 作用: 本模块是整个定时调度系统的核心入口，负责创建和管理 APScheduler 调度器实例，
#       并根据功能配置（feature_config）动态注册各类定时任务。
# 架构角色: 作为调度层的顶层编排器，协调爬虫任务、数据清理、备份、AI处理、
#           向量嵌入计算、事件聚类和主题发现等所有后台定时任务的生命周期。
# 设计思路: 采用单例模式管理调度器，基础任务（爬虫/清理/备份）始终注册，
#           而高级功能（AI/嵌入/聚类/主题）通过功能开关按需注册，
#           实现灵活的功能组合部署。
# ==============================================================================

"""Scheduler tasks for ResearchPulse v2."""

from __future__ import annotations

import logging
from typing import Optional

# APScheduler 异步调度器及触发器
# AsyncIOScheduler: 基于 asyncio 事件循环的调度器，适用于异步 Web 框架
# CronTrigger: 类 cron 表达式触发器，用于定时定点执行（如每天凌晨2点）
# IntervalTrigger: 间隔触发器，用于周期性执行（如每隔N小时）
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from settings import settings

logger = logging.getLogger(__name__)

# 模块级别的调度器单例变量，确保整个应用只有一个调度器实例
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler singleton.

    获取或创建调度器单例实例，使用配置中的时区初始化。

    Returns:
        AsyncIOScheduler: Scheduler singleton instance.
    """
    # 使用全局变量实现单例模式
    global _scheduler
    # 懒加载：仅在首次调用时创建调度器实例
    if _scheduler is None:
        # 使用配置文件中的时区设置初始化调度器，确保任务触发时间与业务时区一致
        _scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    return _scheduler


async def start_scheduler() -> None:
    """Start scheduler and register all jobs.

    启动调度器并根据功能开关注册基础任务与高级分析任务。

    Returns:
        None: This function does not return a value.
    """
    # 延迟导入 feature_config，避免模块加载时的循环依赖问题
    from common.feature_config import feature_config

    scheduler = get_scheduler()

    # === 基础任务区域（始终注册，不受功能开关控制） ===
    # 这些是 ResearchPulse 系统运行的核心任务，无论部署配置如何都必须运行

    # --- Original jobs (always registered) ---

    # ---- 爬虫任务 ----
    # 功能: 定期从所有已激活的数据源（ArXiv、RSS、微信公众号）抓取最新文章
    # 触发方式: 间隔触发，默认间隔由配置中心或全局设置决定
    # 延迟导入爬虫任务函数，避免启动时加载不必要的依赖
    # Add crawl job
    from apps.scheduler.jobs.crawl_job import run_crawl_job
    scheduler.add_job(
        run_crawl_job,
        # 优先从功能配置中心获取爬取间隔时间，若未配置则使用全局默认值
        IntervalTrigger(hours=feature_config.get_int("scheduler.crawl_interval_hours", settings.crawl_interval_hours)),
        id="crawl_job",
        name="Crawl articles from all sources",
        # replace_existing=True 确保重启时不会出现重复任务
        replace_existing=True,
    )

    # ---- 数据清理任务 ----
    # 功能: 将超过保留期限的文章标记为已归档
    # 触发方式: 每天定时执行（Cron 触发），默认在配置的清理时刻运行
    # 注意: 该任务只做归档标记，实际删除由备份任务处理
    # Add cleanup job
    from apps.scheduler.jobs.cleanup_job import run_cleanup_job
    scheduler.add_job(
        run_cleanup_job,
        # 每天在指定整点执行清理操作
        CronTrigger(hour=feature_config.get_int("scheduler.cleanup_hour", settings.cleanup_hour), minute=0),
        id="cleanup_job",
        name="Cleanup old articles",
        replace_existing=True,
    )

    # ---- 备份任务 ----
    # 功能: 在删除旧文章之前先将其导出备份为 JSON 文件，然后再执行删除
    # 触发方式: 每天定时执行（Cron 触发），通常安排在清理任务之后
    # 设计原因: 先备份后删除，确保数据不会因清理而永久丢失
    # Add backup job
    from apps.scheduler.jobs.backup_job import run_backup_job
    scheduler.add_job(
        run_backup_job,
        CronTrigger(hour=feature_config.get_int("scheduler.backup_hour", settings.backup_hour), minute=0),
        id="backup_job",
        name="Backup articles before cleanup",
        replace_existing=True,
    )

    # ---- 去重清理任务 ----
    # 功能: 清理跨源重复的文章记录（ArXiv 跨分类重复、RSS 追踪参数导致的重复）
    # 触发方式: 每天定时执行，安排在爬虫任务后1小时
    # 设计原因: 新的去重逻辑已改进，但历史数据可能仍有重复，定期清理保持数据质量
    # Add dedup cleanup job
    from apps.scheduler.jobs.dedup_job import run_dedup_job
    scheduler.add_job(
        run_dedup_job,
        CronTrigger(hour=feature_config.get_int("scheduler.crawl_interval_hours", settings.crawl_interval_hours) % 24 + 1, minute=30),
        id="dedup_job",
        name="Cleanup duplicate articles",
        replace_existing=True,
    )

    # ---- 邮件通知任务 ----
    # 功能: 每天定时向订阅用户发送个性化的文章摘要邮件
    # 前置条件: 需要启用 feature.email_notification 功能开关
    # 触发方式: 每天定时执行（Cron 触发），默认每天 09:00
    # 设计原因: 将用户通知从爬虫任务中解耦，实现真正的"每天一封"定时推送
    # Email notification job
    if feature_config.get_bool("feature.email_notification", False):
        from apps.scheduler.jobs.notification_job import run_notification_job

        # 解析通知时间: 优先使用 feature_config 数据库配置，
        # 回退到 settings.email_notification_time 环境变量（"HH:MM" 格式）
        _default_hour, _default_minute = 9, 0
        try:
            _parts = settings.email_notification_time.split(":")
            _default_hour = int(_parts[0])
            _default_minute = int(_parts[1]) if len(_parts) > 1 else 0
        except (ValueError, IndexError, AttributeError):
            pass

        scheduler.add_job(
            run_notification_job,
            CronTrigger(
                hour=feature_config.get_int("scheduler.notification_hour", _default_hour),
                minute=feature_config.get_int("scheduler.notification_minute", _default_minute),
            ),
            id="notification_job",
            name="Send daily email notifications",
            replace_existing=True,
        )
        logger.info("Email notification job registered")
    else:
        logger.info("Email notification job skipped (feature.email_notification disabled)")

    # === 扩展功能任务区域（按功能开关条件注册） ===
    # 以下任务属于高级分析功能，需要额外的基础设施支持
    # （如 AI 模型、向量数据库等），通过功能开关控制是否注册

    # ---- AI 处理任务 ----
    # 功能: 使用 AI 模型对新抓取的文章进行智能处理（如摘要生成、分类、关键词提取等）
    # 前置条件: 需要启用 feature.ai_processor 功能开关
    # 触发方式: 间隔触发，默认每1小时执行一次
    # AI processing job
    if feature_config.get_bool("feature.ai_processor", False):
        # 仅在功能启用时才导入相关模块，减少不必要的依赖加载
        from apps.scheduler.jobs.ai_process_job import run_ai_process_job
        scheduler.add_job(
            run_ai_process_job,
            IntervalTrigger(hours=feature_config.get_int("scheduler.ai_process_interval_hours", 1)),
            id="ai_process_job",
            name="AI process new articles",
            replace_existing=True,
        )
        logger.info("AI processing job registered")
    else:
        logger.info("AI processing job skipped (feature.ai_processor disabled)")

    # ---- 向量嵌入计算任务 ----
    # 功能: 为尚未计算嵌入向量的文章生成向量表示，用于语义搜索和相似度计算
    # 前置条件: 需要启用 feature.embedding 功能开关，且需要向量数据库（如 Milvus）支持
    # 触发方式: 间隔触发，默认每2小时执行一次
    # Embedding computation job
    if feature_config.get_bool("feature.embedding", False):
        from apps.scheduler.jobs.embedding_job import run_embedding_job
        scheduler.add_job(
            run_embedding_job,
            IntervalTrigger(hours=feature_config.get_int("scheduler.embedding_interval_hours", 2)),
            id="embedding_job",
            name="Compute article embeddings",
            replace_existing=True,
        )
        logger.info("Embedding computation job registered")
    else:
        logger.info("Embedding computation job skipped (feature.embedding disabled)")

    # ---- 事件聚类任务 ----
    # 功能: 将相关文章聚合为事件簇，帮助用户从海量文章中识别出同一事件的多篇报道
    # 前置条件: 需要启用 feature.event_clustering 功能开关
    # 触发方式: 每天凌晨定时执行（Cron 触发），默认2点
    # 设计原因: 聚类依赖文章的嵌入向量，安排在嵌入计算之后执行
    # Event clustering job
    if feature_config.get_bool("feature.event_clustering", False):
        from apps.scheduler.jobs.event_cluster_job import run_event_cluster_job
        scheduler.add_job(
            run_event_cluster_job,
            CronTrigger(hour=feature_config.get_int("scheduler.event_cluster_hour", 2), minute=0),
            id="event_cluster_job",
            name="Cluster articles into events",
            replace_existing=True,
        )
        logger.info("Event clustering job registered")
    else:
        logger.info("Event clustering job skipped (feature.event_clustering disabled)")

    # ---- 主题发现任务 ----
    # 功能: 从近期文章中自动发现新兴研究主题和热点趋势
    # 前置条件: 需要启用 feature.topic_radar 功能开关
    # 触发方式: 每周定时执行（Cron 触发），默认每周一凌晨1点
    # 设计原因: 主题发现需要积累一定量的文章数据才有意义，因此采用周级别执行频率
    # Topic discovery job
    if feature_config.get_bool("feature.topic_radar", False):
        from apps.scheduler.jobs.topic_discovery_job import run_topic_discovery_job
        scheduler.add_job(
            run_topic_discovery_job,
            CronTrigger(
                # 从配置中心获取执行日期，默认周一
                day_of_week=feature_config.get("scheduler.topic_discovery_day", "mon"),
                # 从配置中心获取执行时刻，默认凌晨1点
                hour=feature_config.get_int("scheduler.topic_discovery_hour", 1),
                minute=0,
            ),
            id="topic_discovery_job",
            name="Discover new topics",
            replace_existing=True,
        )
        logger.info("Topic discovery job registered")
    else:
        logger.info("Topic discovery job skipped (feature.topic_radar disabled)")

    # ---- 行动项批量提取任务 ----
    # 功能: 从已 AI 处理的高重要性文章中自动提取行动项
    # 前置条件: 需要启用 feature.action_items 功能开关
    # 触发方式: 间隔触发，默认每2小时执行一次
    # Action item extraction job
    if feature_config.get_bool("feature.action_items", False):
        from apps.scheduler.jobs.action_extract_job import run_action_extract_job
        scheduler.add_job(
            run_action_extract_job,
            IntervalTrigger(hours=feature_config.get_int("scheduler.action_extract_interval_hours", 2)),
            id="action_extract_job",
            name="Extract action items from articles",
            replace_existing=True,
        )
        logger.info("Action item extraction job registered")
    else:
        logger.info("Action item extraction job skipped (feature.action_items disabled)")

    # ---- 流水线任务队列 Worker ----
    # 功能: 轮询 pipeline_tasks 表，消费执行待处理的流水线任务
    # 无 feature flag 门控 —— worker 通过委托给各 job 函数继承其 feature flag
    # Pipeline task queue worker
    from apps.pipeline.worker import run_pipeline_worker
    worker_interval = feature_config.get_int("pipeline.worker_interval_minutes", 10)
    scheduler.add_job(
        run_pipeline_worker,
        IntervalTrigger(minutes=worker_interval),
        id="pipeline_worker",
        name="Pipeline task queue worker",
        replace_existing=True,
    )
    logger.info("Pipeline worker job registered (interval=%d min)", worker_interval)

    # ---- 周报自动生成任务 ----
    # 功能: 每周为所有活跃用户自动生成上周的周报
    # 前置条件: 需要启用 feature.report_generation 功能开关
    # 触发方式: 每周定时执行（Cron 触发），默认每周一早上6点
    # Weekly report generation job
    if feature_config.get_bool("feature.report_generation", False):
        from apps.scheduler.jobs.report_generate_job import run_weekly_report_job, run_monthly_report_job
        scheduler.add_job(
            run_weekly_report_job,
            CronTrigger(
                day_of_week=feature_config.get("scheduler.report_weekly_day", "mon"),
                hour=feature_config.get_int("scheduler.report_weekly_hour", 6),
                minute=0,
            ),
            id="weekly_report_job",
            name="Generate weekly reports",
            replace_existing=True,
        )

        # ---- 月报自动生成任务 ----
        # 功能: 每月1号为所有活跃用户自动生成上月的月报
        # Monthly report generation job
        scheduler.add_job(
            run_monthly_report_job,
            CronTrigger(
                day=1,
                hour=feature_config.get_int("scheduler.report_monthly_hour", 7),
                minute=0,
            ),
            id="monthly_report_job",
            name="Generate monthly reports",
            replace_existing=True,
        )
        logger.info("Report generation jobs registered (weekly + monthly)")
    else:
        logger.info("Report generation jobs skipped (feature.report_generation disabled)")

    # 所有任务注册完毕后，启动调度器开始按计划执行任务
    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler() -> None:
    """Stop the scheduler gracefully.

    优雅停止调度器，等待正在执行的任务完成后关闭。

    Returns:
        None: This function does not return a value.
    """
    # 访问模块级别的调度器单例
    global _scheduler
    # 安全检查：仅在调度器存在且正在运行时才执行关闭操作
    if _scheduler and _scheduler.running:
        # 优雅关闭调度器，等待当前正在执行的任务完成后停止
        _scheduler.shutdown()
        logger.info("Scheduler stopped")
