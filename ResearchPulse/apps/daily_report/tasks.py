# =============================================================================
# 模块: apps/daily_report/tasks.py
# 功能: 每日报告生成定时任务
# 架构角色: 调度任务层，负责定时触发报告生成
# =============================================================================

"""Daily report scheduled tasks."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .service import DailyReportService
from common.feature_config import feature_config

logger = logging.getLogger(__name__)


async def daily_report_job() -> None:
    """Daily report generation job.

    每日报告生成定时任务。

    触发时间: 根据配置 daily_report.hour 和 daily_report.minute
    功能开关: daily_report.enabled
    数据源类型: daily_report.source_types (默认 arxiv)
    """
    # 检查功能是否启用
    if not feature_config.get_bool("daily_report.enabled", True):
        logger.info("Daily report feature is disabled, skipping job")
        return

    logger.info("Starting daily report generation job")

    # 从配置读取数据源类型
    source_types_str = feature_config.get("daily_report.source_types", "arxiv")
    source_types = [s.strip() for s in source_types_str.split(",") if s.strip()]

    # 从配置读取分类（用于 arxiv）
    categories_str = feature_config.get("daily_report.categories", "cs.LG,cs.CV,cs.CL,cs.AI")
    categories = [c.strip() for c in categories_str.split(",") if c.strip()]

    try:
        service = DailyReportService()
        reports = await service.generate_daily_reports(
            source_types=source_types,
            categories=categories,
        )

        logger.info(f"Daily report job completed, generated {len(reports)} reports")

    except Exception as e:
        logger.error(f"Daily report job failed: {e}", exc_info=True)


def register_daily_report_job(scheduler: AsyncIOScheduler) -> None:
    """Register the daily report job with the scheduler.

    注册每日报告生成任务到调度器。

    Args:
        scheduler: APScheduler instance.
    """
    # 获取配置
    hour = feature_config.get_int("daily_report.hour", 8)
    minute = feature_config.get_int("daily_report.minute", 0)

    # 创建 Cron 触发器
    trigger = CronTrigger(hour=hour, minute=minute)

    # 添加任务
    scheduler.add_job(
        daily_report_job,
        trigger=trigger,
        id="daily_report_job",
        name="每日报告生成（多数据源）",
        replace_existing=True,
        max_instances=1,  # 同一时间只允许一个实例运行
        misfire_grace_time=3600,  # 允许 1 小时内的延迟执行
    )

    logger.info(f"Registered daily_report_job with trigger: {trigger}")
