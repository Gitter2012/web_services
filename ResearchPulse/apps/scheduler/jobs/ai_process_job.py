# ==============================================================================
# 模块: ResearchPulse AI 文章处理定时任务
# 作用: 本模块负责定时调用 AI 处理服务，对新抓取但尚未处理的文章进行智能分析，
#       包括但不限于: 摘要生成、分类标注、关键词提取、情感分析等。
# 架构角色: 数据处理流水线中的 AI 增强环节。
#           位于爬虫任务之后、嵌入计算之前，为后续的语义搜索和聚类分析提供结构化数据。
# 前置条件: 需要在功能配置中启用 feature.ai_processor 开关。
# 执行方式: 由 APScheduler 的 IntervalTrigger 按固定间隔（默认每小时）自动触发。
# ==============================================================================

"""AI processing scheduled job for ResearchPulse."""

from __future__ import annotations

import logging

from core.database import get_session_factory

logger = logging.getLogger(__name__)


async def run_ai_process_job() -> dict:
    """Process new articles with AI.

    批量处理尚未经过 AI 分析的文章，生成摘要与结构化字段。

    Returns:
        dict: Processing statistics or a skipped status when disabled.
    """
    # 功能: 批量处理尚未经过 AI 分析的新文章
    # 参数: 无（批处理数量等配置在内部硬编码或由服务层管理）
    # 返回值: dict - 包含处理统计信息:
    #   - processed: 成功处理的文章数
    #   - cached: 命中缓存的文章数（已有相同内容的 AI 处理结果）
    #   - failed: 处理失败的文章数
    #   - total: 本次任务处理的文章总数
    #   - 或 skipped=True 表示功能被禁用
    # 副作用: 数据库更新 —— 为处理过的文章写入 AI 分析结果

    # 延迟导入功能配置，避免模块加载时的循环依赖
    from common.feature_config import feature_config

    # 双重检查功能开关: 即使任务被注册到调度器，执行时仍再次确认功能是否启用
    # 这是因为功能配置可能在运行时动态变更（如通过管理后台关闭），
    # 而调度器中已注册的任务不会自动移除
    if not feature_config.get_bool("feature.ai_processor", False):
        logger.info("AI processing disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting AI processing job")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 延迟导入 AI 处理服务，仅在实际需要执行时才加载
        # 这样做可以避免在 AI 功能未启用时加载 AI 相关的依赖库（如模型库）
        from apps.ai_processor.service import AIProcessorService

        # 创建 AI 处理服务实例
        service = AIProcessorService()
        # 累计统计
        accumulated = {"processed": 0, "cached": 0, "failed": 0, "total": 0}

        try:
            # 预热模型：向 Ollama 发送空请求触发模型加载到内存，
            # 避免第一篇文章处理时因冷启动（30-120 秒）导致超时失败
            warmup_ok = await service.warmup()
            if not warmup_ok:
                logger.warning("Model warmup did not complete, proceeding anyway")

            # 循环处理：每次取 batch_limit 篇文章，直到没有待处理文章为止
            batch_limit = feature_config.get_int("pipeline.ai_batch_limit", 200)
            while True:
                result = await service.process_unprocessed(session, limit=batch_limit)
                await session.commit()

                batch_total = result.get("total", 0)
                accumulated["processed"] += result.get("processed", 0)
                accumulated["cached"] += result.get("cached", 0)
                accumulated["failed"] += result.get("failed", 0)
                accumulated["total"] += batch_total

                if batch_total < batch_limit:
                    break

                logger.info(
                    f"AI processing batch done ({batch_total} items), "
                    f"continuing next batch..."
                )

            # 入队下游任务（使用独立 session，与主事务隔离）
            try:
                from apps.pipeline.triggers import enqueue_downstream_after_ai
                async with session_factory() as enqueue_session:
                    await enqueue_downstream_after_ai(enqueue_session, accumulated, trigger_source="ai_process_job")
                    await enqueue_session.commit()
            except Exception as trigger_err:
                logger.warning(f"Failed to enqueue downstream tasks: {trigger_err}")

        except Exception as e:
            logger.error(f"AI processing job failed: {e}", exc_info=True)
            await session.rollback()
            return {"error": str(e), "processed": accumulated["processed"], "cached": accumulated["cached"], "failed": accumulated["failed"], "total": accumulated["total"]}
        finally:
            # 确保释放 Provider 持有的 HTTP 连接池资源
            await service.close()

    # 输出详细的处理统计日志
    logger.info(
        f"AI processing job completed: "
        f"{accumulated['processed']} processed, {accumulated['cached']} cached, "
        f"{accumulated['failed']} failed out of {accumulated['total']}"
    )
    return accumulated
