# ==============================================================================
# 模块: ResearchPulse 数据清理定时任务
# 作用: 本模块负责对过期文章执行归档操作，将超过数据保留期限的文章标记为已归档状态。
# 架构角色: 数据生命周期管理的第一环。清理任务负责"软删除"（归档标记），
#           而实际的"硬删除"（物理删除）由备份任务（backup_job）在完成数据导出后执行。
# 设计思路: 采用两阶段删除策略 —— 先归档再删除，确保数据在被永久移除前有足够的缓冲期，
#           防止误删导致数据丢失。归档后的文章对普通用户不可见，但仍保留在数据库中。
# 执行方式: 由 APScheduler 的 CronTrigger 每天在指定时刻（如凌晨3点）触发执行。
# ==============================================================================

"""Cleanup job for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from core.database import get_session_factory
from apps.crawler.models import Article
from settings import settings

logger = logging.getLogger(__name__)


async def run_cleanup_job() -> dict:
    """Run cleanup for old articles.

    扫描过期文章并执行归档标记，删除由备份任务在导出后完成。

    Returns:
        dict: Cleanup summary with status, duration, and archived counts.
    """
    # 功能: 扫描数据库中的文章，将超过保留期限的文章标记为归档状态
    # 参数: 无（保留天数等配置从 settings 中读取）
    # 返回值: dict - 包含清理任务的执行统计（状态、耗时、归档文章数等）
    # 副作用: 数据库更新 —— 将符合条件的文章的 is_archived 字段设为 True，
    #         并记录归档时间 archived_at

    logger.info("Starting cleanup job")
    start_time = datetime.now(timezone.utc)

    # 计算归档和删除的时间阈值
    now = datetime.now(timezone.utc)
    # 归档阈值: 爬取时间早于此阈值的文章将被标记为归档
    # 例如: data_retention_days=30，则30天前的文章会被归档
    archive_threshold = now - timedelta(days=settings.data_retention_days)
    # 删除阈值: 爬取时间早于此阈值的文章将被物理删除（由 backup_job 处理）
    # 例如: data_archive_days=90，则90天前的文章会在备份后被删除
    delete_threshold = now - timedelta(days=settings.data_archive_days)

    # 初始化结果统计
    results = {
        "archived": 0,  # 本次归档的文章数量
        "deleted": 0,   # 本次删除的文章数量（当前始终为0，删除操作由 backup_job 执行）
        "errors": [],    # 清理过程中的错误列表
    }

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 执行批量归档操作
        # 条件: 爬取时间早于归档阈值 且 尚未被归档的文章
        # 使用 SQLAlchemy 的 update 语句实现批量更新，比逐条更新效率更高
        # Archive old articles
        archive_result = await session.execute(
            update(Article)
            .where(
                Article.crawl_time < archive_threshold,
                Article.is_archived == False,
            )
            .values(is_archived=True, archived_at=now)
        )
        # rowcount 返回受影响的行数，即本次被归档的文章数量
        results["archived"] = archive_result.rowcount or 0

        # 关于物理删除的说明:
        # 实际的文章删除操作不在此任务中执行，而是由 backup_job 负责。
        # backup_job 会先将待删除的文章导出为 JSON 备份文件，
        # 确认备份成功后才执行物理删除，从而保证数据安全。
        # Note: Actual deletion is handled by backup job
        # Articles to delete are backed up first, then deleted

        # 提交事务，使归档标记生效
        await session.commit()

    # 生成任务执行摘要
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "articles_archived": results["archived"],
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Cleanup job completed: {summary}")
    return summary
