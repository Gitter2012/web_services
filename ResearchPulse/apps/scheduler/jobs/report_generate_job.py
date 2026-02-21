# ==============================================================================
# 模块: ResearchPulse 报告自动生成定时任务
# 作用: 定时为活跃用户自动生成周报和月报。
#       周报每周一生成上周数据，月报每月 1 号生成上月数据。
# 架构角色: 数据消费层的最终输出环节，汇总 AI 处理、事件聚类、行动项等结果。
# 前置条件: 需要在功能配置中启用 feature.report_generation 开关。
# 执行方式: 周报由 CronTrigger(day_of_week) 触发，月报由 CronTrigger(day=1) 触发。
# ==============================================================================

"""Report generation scheduled jobs."""

from __future__ import annotations

import logging

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session_factory

logger = logging.getLogger(__name__)


async def run_weekly_report_job() -> dict:
    """Generate weekly reports for all active users.

    为所有活跃用户生成上周的周报。跳过已存在同期报告的用户。

    Returns:
        dict: Generation statistics.
    """
    from common.feature_config import feature_config

    if not feature_config.get_bool("feature.report_generation", False):
        logger.info("Report generation disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting weekly report generation job")

    session_factory = get_session_factory()
    generated = 0
    skipped = 0

    async with session_factory() as session:
        try:
            from core.models.user import User
            import core.models.permission  # noqa: F401 — ensure Role mapper is initialized
            from apps.report.models import Report
            from apps.report.service import ReportService

            # 查询所有活跃用户
            result = await session.execute(
                select(User.id).where(User.is_active.is_(True))
            )
            user_ids = [row[0] for row in result.all()]

            if not user_ids:
                logger.info("No active users, skipping report generation")
                return {"generated": 0, "skipped": 0}

            service = ReportService()

            # 计算上周的时间范围用于去重检查
            from datetime import datetime, timedelta, timezone
            today = datetime.now(timezone.utc)
            last_week_start = today - timedelta(days=today.weekday() + 7)
            last_week_start = last_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            period_start_str = last_week_start.strftime("%Y-%m-%d")

            for user_id in user_ids:
                # 幂等检查：同用户 + 同类型 + 同期不重复生成
                existing = await session.execute(
                    select(Report.id).where(
                        and_(
                            Report.user_id == user_id,
                            Report.type == "weekly",
                            Report.period_start == period_start_str,
                        )
                    ).limit(1)
                )
                if existing.scalar():
                    skipped += 1
                    continue

                try:
                    await service.generate_weekly(user_id, session, weeks_ago=1)
                    generated += 1
                except Exception as e:
                    logger.warning(f"Failed to generate weekly report for user {user_id}: {e}")

            # 将报告生成结果保存为 AIGC 文章
            if generated > 0:
                await _save_report_aigc_article(
                    session, "weekly", period_start_str, generated, skipped
                )

            await session.commit()
        except Exception as e:
            logger.error(f"Weekly report generation failed: {e}", exc_info=True)
            await session.rollback()
            return {"error": str(e), "generated": 0, "skipped": 0}

    logger.info(f"Weekly report job completed: {generated} generated, {skipped} skipped")
    return {"generated": generated, "skipped": skipped}


async def run_monthly_report_job() -> dict:
    """Generate monthly reports for all active users.

    为所有活跃用户生成上月的月报。跳过已存在同期报告的用户。

    Returns:
        dict: Generation statistics.
    """
    from common.feature_config import feature_config

    if not feature_config.get_bool("feature.report_generation", False):
        logger.info("Report generation disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting monthly report generation job")

    session_factory = get_session_factory()
    generated = 0
    skipped = 0

    async with session_factory() as session:
        try:
            from core.models.user import User
            import core.models.permission  # noqa: F401 — ensure Role mapper is initialized
            from apps.report.models import Report
            from apps.report.service import ReportService

            result = await session.execute(
                select(User.id).where(User.is_active.is_(True))
            )
            user_ids = [row[0] for row in result.all()]

            if not user_ids:
                logger.info("No active users, skipping report generation")
                return {"generated": 0, "skipped": 0}

            service = ReportService()

            # 计算上月的起始日期用于去重检查
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc)
            month = today.month - 1
            year = today.year
            if month <= 0:
                month += 12
                year -= 1
            period_start_str = f"{year}-{month:02d}-01"

            for user_id in user_ids:
                existing = await session.execute(
                    select(Report.id).where(
                        and_(
                            Report.user_id == user_id,
                            Report.type == "monthly",
                            Report.period_start == period_start_str,
                        )
                    ).limit(1)
                )
                if existing.scalar():
                    skipped += 1
                    continue

                try:
                    await service.generate_monthly(user_id, session, months_ago=1)
                    generated += 1
                except Exception as e:
                    logger.warning(f"Failed to generate monthly report for user {user_id}: {e}")

            # 将报告生成结果保存为 AIGC 文章
            if generated > 0:
                await _save_report_aigc_article(
                    session, "monthly", period_start_str, generated, skipped
                )

            await session.commit()
        except Exception as e:
            logger.error(f"Monthly report generation failed: {e}", exc_info=True)
            await session.rollback()
            return {"error": str(e), "generated": 0, "skipped": 0}

    logger.info(f"Monthly report job completed: {generated} generated, {skipped} skipped")
    return {"generated": generated, "skipped": skipped}


async def _save_report_aigc_article(
    session, report_type: str, period_start: str, generated: int, skipped: int
) -> None:
    """Generate an AIGC summary article for report generation results."""
    from apps.aigc.article_writer import save_aigc_article

    type_label = "周报" if report_type == "weekly" else "月报"
    title = f"报告中心摘要 - {type_label} {period_start}"
    lines = [
        f"# {title}\n",
        f"本次为 **{generated}** 位用户生成了{type_label}，跳过 **{skipped}** 位（已有同期报告）。\n",
        f"- 报告类型: {type_label}",
        f"- 覆盖周期起始: {period_start}",
        f"- 生成数量: {generated}",
        f"- 跳过数量: {skipped}",
        "",
    ]
    content = "\n".join(lines)

    await save_aigc_article(
        session,
        source_id="report",
        external_id=f"report_{report_type}_{period_start}",
        title=title,
        content=content,
        tags=["报告中心", type_label, "AIGC", period_start],
    )
