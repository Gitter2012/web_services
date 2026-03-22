# =============================================================================
# 模块: apps/scheduler/jobs/news_report_job.py
# 功能: 每日新闻报告自动生成任务
# 架构角色: 作为调度器的 job 之一，负责按时生成中英文新闻报告
# 执行方式: 由 APScheduler CronTrigger 每日定时执行（默认 8:30）
# =============================================================================

"""News report generation job for ResearchPulse v2."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_news_report_job() -> dict:
    """Generate daily news reports (CN + EN).

    生成每日新闻报告（中文 + 英文）。

    Returns:
        dict: Summary of generated reports.
    """
    logger.info("Starting news report generation job")

    try:
        from apps.daily_report.news_service import NewsReportService

        service = NewsReportService()
        reports = await service.generate_news_reports()

        result = {
            "status": "success",
            "reports_generated": len(reports),
            "report_types": [r.source_type for r in reports],
        }

        logger.info(f"News report job completed: {len(reports)} reports generated")
        return result

    except Exception as e:
        logger.exception(f"News report job failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
