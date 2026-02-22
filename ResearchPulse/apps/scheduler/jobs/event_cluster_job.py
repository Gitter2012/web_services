# ==============================================================================
# 模块: ResearchPulse 事件聚类定时任务
# 作用: 本模块负责定时将内容相关的文章聚合为事件簇（event cluster），
#       帮助用户从海量文章中识别出同一事件的多篇报道，实现信息去重和事件追踪。
# 架构角色: 数据分析流水线的聚合环节。
#           依赖嵌入计算任务（embedding_job）生成的向量数据，
#           通过向量相似度判断文章间的关联性，将相似文章归入同一事件。
# 前置条件: 需要在功能配置中启用 feature.event_clustering 开关。
#           隐含依赖: 文章需要已完成嵌入向量计算。
# 执行方式: 由 APScheduler 的 CronTrigger 每天凌晨定时触发（默认2:00 AM），
#           安排在嵌入计算任务之后执行，确保有最新的向量数据可用。
# ==============================================================================

"""Event clustering scheduled job for ResearchPulse."""

from __future__ import annotations

import logging

from core.database import get_session_factory

logger = logging.getLogger(__name__)


async def run_event_cluster_job() -> dict:
    """Cluster articles into events.

    对未聚类文章执行事件聚类，将语义相似文章归入同一事件簇。

    Returns:
        dict: Clustering summary or skipped status when disabled.
    """
    # 功能: 对未聚类的文章执行事件聚类分析，将语义相似的文章归入同一事件簇
    # 参数: 无（聚类参数由 EventService 内部管理）
    # 返回值: dict - 包含聚类统计信息:
    #   - clustered: 成功归入事件簇的文章数
    #   - new_clusters: 新创建的事件簇数量
    #   - total_processed: 本次任务处理的文章总数
    #   - 或 skipped=True 表示功能被禁用
    # 副作用: 数据库更新 —— 创建新的事件记录并将文章关联到事件簇中

    # 延迟导入功能配置，避免模块加载时的循环依赖
    from common.feature_config import feature_config

    # 双重检查功能开关: 运行时再次确认聚类功能是否仍然启用
    # 防御性编程，应对功能配置在运行时被动态修改的情况
    if not feature_config.get_bool("feature.event_clustering", False):
        logger.info("Event clustering disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting event clustering job")

    # 累计统计
    accumulated = {"total_processed": 0, "clustered": 0, "new_clusters": 0}

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 延迟导入事件聚类服务，仅在功能启用且实际执行时才加载
        from apps.event.service import EventService

        # 创建事件聚类服务实例
        service = EventService()

        # 循环处理：每次取 batch_limit 篇文章，直到没有待处理文章为止
        batch_limit = feature_config.get_int("pipeline.event_batch_limit", 500)
        while True:
            result = await service.cluster_articles(session, limit=batch_limit)

            batch_total = result.get("total_processed", 0)
            accumulated["total_processed"] += batch_total
            accumulated["clustered"] += result.get("clustered", 0)
            accumulated["new_clusters"] += result.get("new_clusters", 0)

            if batch_total < batch_limit:
                break

            # 每批次提交一次，避免长事务
            await session.commit()
            logger.info(
                f"Event clustering batch done ({batch_total} items), "
                f"continuing next batch..."
            )

        # 将聚类累计结果保存为 AIGC 文章
        if accumulated["clustered"] > 0 or accumulated["new_clusters"] > 0:
            await _save_event_aigc_article(session, accumulated)

        # 提交事务，持久化聚类结果（新事件簇和文章-事件关联关系）
        await session.commit()

    # 输出详细的聚类统计日志
    logger.info(
        f"Event clustering job completed: "
        f"{accumulated['clustered']} clustered ({accumulated['new_clusters']} new) "
        f"out of {accumulated['total_processed']}"
    )
    return accumulated


async def _save_event_aigc_article(session, result: dict) -> None:
    """Generate an AIGC summary article for the event clustering run."""
    from datetime import datetime, timezone
    from apps.aigc.article_writer import save_aigc_article

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    clustered = result.get("clustered", 0)
    new_clusters = result.get("new_clusters", 0)
    total = result.get("total_processed", 0)

    title = f"事件聚类日报 - {today}"
    lines = [
        f"# {title}\n",
        f"本次聚类处理了 **{total}** 篇文章，",
        f"成功归入事件簇 **{clustered}** 篇，",
        f"新建事件簇 **{new_clusters}** 个。\n",
    ]

    # Try to include new cluster details
    try:
        from sqlalchemy import select
        from apps.event.models import EventCluster
        recent = await session.execute(
            select(EventCluster)
            .where(EventCluster.is_active.is_(True))
            .order_by(EventCluster.last_updated_at.desc())
            .limit(10)
        )
        clusters = recent.scalars().all()
        if clusters:
            lines.append("## 最近活跃事件\n")
            for i, c in enumerate(clusters, 1):
                lines.append(
                    f"{i}. **{c.title}** ({c.article_count} 篇文章)"
                )
            lines.append("")
    except Exception:
        pass

    content = "\n".join(lines)
    await save_aigc_article(
        session,
        source_id="event_clustering",
        external_id=f"event_{today}",
        title=title,
        content=content,
        tags=["事件聚类", "AIGC", today],
    )
