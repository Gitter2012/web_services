# =============================================================================
# 模块: apps/scheduler/jobs/dedup_job.py
# 功能: 文章去重清理任务
# 架构角色: 调度系统的后台任务之一，负责清理跨源重复的文章记录
# 设计理念:
#   1. ArXiv 论文可能因为属于多个分类而被多次保存
#   2. RSS 文章可能因为 URL 追踪参数变化而被多次保存
#   3. 定期清理重复记录，保持数据质量
# =============================================================================

"""Deduplication cleanup job for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def deduplicate_arxiv_articles(session: AsyncSession) -> int:
    """Remove duplicate ArXiv articles.

    当同一篇论文因多个分类被重复保存时，保留最早记录并删除其余重复项。

    Args:
        session: Async database session.

    Returns:
        int: Number of deleted duplicate rows.
    """
    # 使用 SQL 删除重复的 ArXiv 论文
    # 保留每组中 id 最小的记录（最早爬取的）
    result = await session.execute(
        text("""
            DELETE a1 FROM articles a1
            INNER JOIN articles a2
            ON a1.arxiv_id = a2.arxiv_id
               AND a1.source_type = 'arxiv'
               AND a2.source_type = 'arxiv'
               AND a1.id > a2.id
        """)
    )
    deleted_count = result.rowcount
    return deleted_count


async def deduplicate_rss_articles(session: AsyncSession) -> int:
    """Remove duplicate RSS articles.

    当同一篇文章因 URL 追踪参数变化而多次保存时，按标题与来源去重。

    Args:
        session: Async database session.

    Returns:
        int: Number of deleted duplicate rows.
    """
    # 删除同一 RSS 源中标题相同的重复文章
    # 保留每组中 id 最小的记录
    result = await session.execute(
        text("""
            DELETE a1 FROM articles a1
            INNER JOIN articles a2
            ON a1.source_type = a2.source_type
               AND a1.source_id = a2.source_id
               AND a1.title = a2.title
               AND a1.source_type = 'rss'
               AND a1.id > a2.id
               AND LENGTH(a1.title) > 10
        """)
    )
    deleted_count = result.rowcount
    return deleted_count


async def run_dedup_job() -> dict:
    """Run the deduplication cleanup job.

    调度器入口函数，清理 ArXiv 与 RSS 的重复文章记录。

    Returns:
        dict: Deduplication summary with counts and status.
    """
    start_time = datetime.now(timezone.utc)
    logger.info("Starting deduplication cleanup job")

    total_deleted = 0
    results = {}

    try:
        from core.database import get_session_factory
        factory = get_session_factory()

        async with factory() as session:
            # 清理 ArXiv 重复
            arxiv_deleted = await deduplicate_arxiv_articles(session)
            results["arxiv_deleted"] = arxiv_deleted
            total_deleted += arxiv_deleted
            logger.info(f"Deleted {arxiv_deleted} duplicate arXiv articles")

            # 清理 RSS 重复
            rss_deleted = await deduplicate_rss_articles(session)
            results["rss_deleted"] = rss_deleted
            total_deleted += rss_deleted
            logger.info(f"Deleted {rss_deleted} duplicate RSS articles")

            # 提交事务
            await session.commit()

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        result = {
            "status": "success",
            "total_deleted": total_deleted,
            "details": results,
            "duration_seconds": duration,
            "timestamp": end_time.isoformat(),
        }

        logger.info(f"Dedup job completed: {total_deleted} duplicates removed in {duration:.2f}s")
        return result

    except Exception as e:
        logger.exception(f"Dedup job failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
