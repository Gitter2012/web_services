# =============================================================================
# 模块: apps/daily_digest/tasks.py
# 功能: 每日精选日报定时任务注册
# 架构角色: 调度任务层，注册 08:05 / 20:10 两次定时任务
#
# Pipeline 时序对齐：
#   00:00 crawler → 01:xx ai_process → 02:00 event_cluster
#   08:05 【早报生成】← event_cluster 已完成，覆盖前一天完整数据 + 今天06:00批次
#   20:10 【晚报更新】← force=True 重新生成，纳入全天内容
#
# 每次定时任务会按照配置的 daily_digest.categories 遍历所有分类生成精选。
# 默认分类：all（全量聚合）、AI、金融、技术
# =============================================================================

"""Daily digest scheduled tasks."""

from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from common.feature_config import feature_config

logger = logging.getLogger(__name__)


def _get_configured_categories() -> list[str]:
    """从配置读取需要生成的精选分类列表。"""
    cats_str = feature_config.get("daily_digest.categories", "all,AI,金融,技术")
    return [c.strip() for c in cats_str.split(",") if c.strip()]


async def _run_digest_for_date(report_date: date, force: bool) -> None:
    """为指定日期生成所有配置分类的精选日报。

    Args:
        report_date: 生成日期。
        force: 是否强制覆盖已有日报。
    """
    categories = _get_configured_categories()
    top_n = feature_config.get_int("daily_digest.top_n", 25)

    logger.info(
        "Running digest for %s, categories=%s, force=%s, top_n=%d",
        report_date, categories, force, top_n
    )

    from .service import DailyDigestService
    service = DailyDigestService()
    reports = await service.generate_multi_digests(
        report_date=report_date,
        categories=categories,
        force=force,
        top_n=top_n,
    )
    logger.info(
        "Digest job completed for %s: %d/%d categories generated",
        report_date, len(reports), len(categories)
    )


async def daily_digest_morning_job() -> None:
    """早报生成任务（默认 08:05）。

    幂等：已存在时不覆盖（force=False）。
    覆盖前一天完整数据 + 今天06:00批次。
    """
    if not feature_config.get_bool("daily_digest.enabled", False):
        logger.debug("Daily digest disabled, skipping morning job")
        return

    logger.info("Starting daily digest morning job")
    report_date = date.today()

    try:
        await _run_digest_for_date(report_date, force=False)
    except Exception as e:
        logger.error("Daily digest morning job failed: %s", e, exc_info=True)


async def daily_digest_evening_job() -> None:
    """晚报更新任务（默认 20:10）。

    force=True：强制重新生成，纳入全天内容。
    """
    if not feature_config.get_bool("daily_digest.enabled", False):
        logger.debug("Daily digest disabled, skipping evening job")
        return

    logger.info("Starting daily digest evening job")
    report_date = date.today()

    try:
        await _run_digest_for_date(report_date, force=True)
    except Exception as e:
        logger.error("Daily digest evening job failed: %s", e, exc_info=True)


def register_daily_digest_tasks(scheduler: AsyncIOScheduler) -> None:
    """注册每日精选日报的早报和晚报定时任务。

    Args:
        scheduler: APScheduler AsyncIOScheduler 实例。
    """
    morning_hour = feature_config.get_int("daily_digest.morning_hour", 8)
    morning_minute = feature_config.get_int("daily_digest.morning_minute", 5)
    evening_hour = feature_config.get_int("daily_digest.evening_hour", 20)
    evening_minute = feature_config.get_int("daily_digest.evening_minute", 10)

    # 早报任务（默认 08:05）
    scheduler.add_job(
        daily_digest_morning_job,
        trigger=CronTrigger(hour=morning_hour, minute=morning_minute),
        id="daily_digest_morning_job",
        name="每日精选早报生成",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,  # 10分钟内错过可补跑
    )

    # 晚报任务（默认 20:10）
    scheduler.add_job(
        daily_digest_evening_job,
        trigger=CronTrigger(hour=evening_hour, minute=evening_minute),
        id="daily_digest_evening_job",
        name="每日精选晚报更新",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,
    )

    logger.info(
        "Daily digest tasks registered: morning=%02d:%02d, evening=%02d:%02d",
        morning_hour, morning_minute, evening_hour, evening_minute,
    )
