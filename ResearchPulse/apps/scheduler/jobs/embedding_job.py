# ==============================================================================
# 模块: ResearchPulse 向量嵌入计算定时任务
# 作用: 本模块负责定时为尚未计算嵌入向量的文章生成向量表示（embedding），
#       这些向量用于支撑语义搜索、文章相似度计算和事件聚类等高级功能。
# 架构角色: 数据处理流水线中的向量化环节。
#           位于 AI 处理任务之后、事件聚类任务之前。
#           嵌入向量是语义理解的基础，聚类和搜索功能都依赖于它。
# 前置条件: 需要在功能配置中启用 feature.embedding 开关，
#           且需要向量数据库（如 Milvus）基础设施的支持。
# 执行方式: 由 APScheduler 的 IntervalTrigger 按固定间隔（默认每2小时）自动触发。
# ==============================================================================

"""Embedding computation scheduled job for ResearchPulse."""

from __future__ import annotations

import logging

from core.database import get_session_factory

logger = logging.getLogger(__name__)


async def run_embedding_job() -> dict:
    """Compute embeddings for unprocessed articles.

    批量为尚未生成向量的文章计算嵌入表示，用于语义检索与聚类。

    Returns:
        dict: Embedding computation summary or skipped status.
    """
    # 功能: 批量为尚未生成嵌入向量的文章计算向量表示
    # 参数: 无（批处理数量在内部配置）
    # 返回值: dict - 包含嵌入计算统计信息:
    #   - computed: 成功计算嵌入的文章数
    #   - skipped: 跳过的文章数（如内容为空、已有嵌入等）
    #   - failed: 计算失败的文章数
    #   - total: 本次任务处理的文章总数
    #   - 或 skipped=True 表示功能被禁用
    # 副作用: 数据库/向量数据库更新 —— 为文章写入嵌入向量数据

    # 延迟导入功能配置，避免模块加载时的循环依赖
    from common.feature_config import feature_config

    # 双重检查功能开关: 运行时再次确认功能是否仍然启用
    # 功能配置可能在任务注册后被动态关闭，此处做防御性检查
    if not feature_config.get_bool("feature.embedding", False):
        logger.info("Embedding computation disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting embedding computation job")

    # 累计统计
    accumulated = {"computed": 0, "skipped": 0, "failed": 0, "total": 0}

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 延迟导入嵌入服务，仅在功能启用且实际执行时才加载
        # 避免在嵌入功能未启用时加载向量模型等重量级依赖
        from apps.embedding.service import EmbeddingService

        # 创建嵌入计算服务实例
        service = EmbeddingService()

        # 循环处理：每次取 batch_limit 篇文章，直到没有待处理文章为止
        batch_limit = feature_config.get_int("pipeline.embedding_batch_limit", 500)
        while True:
            result = await service.compute_uncomputed(session, limit=batch_limit)
            await session.commit()

            batch_total = result.get("total", 0)
            accumulated["computed"] += result.get("computed", 0)
            accumulated["skipped"] += result.get("skipped", 0)
            accumulated["failed"] += result.get("failed", 0)
            accumulated["total"] += batch_total

            if batch_total < batch_limit:
                break

            logger.info(
                f"Embedding batch done ({batch_total} items), "
                f"continuing next batch..."
            )

    # 入队下游任务（使用独立 session，与主事务隔离）
    try:
        from apps.pipeline.triggers import enqueue_downstream_after_embedding
        async with session_factory() as enqueue_session:
            await enqueue_downstream_after_embedding(enqueue_session, accumulated, trigger_source="embedding_job")
            await enqueue_session.commit()
    except Exception as trigger_err:
        logger.warning(f"Failed to enqueue downstream tasks: {trigger_err}")

    # 输出详细的计算统计日志
    logger.info(
        f"Embedding job completed: "
        f"{accumulated['computed']} computed, {accumulated['skipped']} skipped, "
        f"{accumulated['failed']} failed out of {accumulated['total']}"
    )
    return accumulated
