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

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 延迟导入嵌入服务，仅在功能启用且实际执行时才加载
        # 避免在嵌入功能未启用时加载向量模型等重量级依赖
        from apps.embedding.service import EmbeddingService

        # 创建嵌入计算服务实例
        service = EmbeddingService()
        # 批量计算未生成嵌入的文章，limit=100（比 AI 处理的 limit=50 大，
        # 因为嵌入计算通常比 AI 处理更快速且资源消耗更少）
        result = await service.compute_uncomputed(session, limit=100)
        # 提交事务，持久化嵌入计算结果
        await session.commit()

    # 输出详细的计算统计日志
    logger.info(
        f"Embedding job completed: "
        f"{result['computed']} computed, {result['skipped']} skipped, "
        f"{result['failed']} failed out of {result['total']}"
    )
    return result
