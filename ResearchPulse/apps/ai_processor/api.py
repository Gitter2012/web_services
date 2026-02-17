# =============================================================================
# AI 处理器 API 端点模块
# =============================================================================
# 本模块定义了 AI 内容处理相关的 RESTful API 接口。
# 在架构中，它是 AI 处理器子系统对外暴露的 HTTP 层，负责：
#   1. 接收前端或其他服务发来的文章处理请求
#   2. 调用 AIProcessorService 执行实际的 AI 分析逻辑
#   3. 查询文章的 AI 处理状态和 token 使用统计
# 所有端点均需启用 "feature.ai_processor" 功能开关才可访问。
# =============================================================================

"""AI processor API endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import CurrentUser, get_current_user, require_permissions

from common.feature_config import require_feature

from .models import AIProcessingLog, TokenUsageStat
from .schemas import (
    BatchProcessRequest,
    BatchProcessResponse,
    ProcessArticleRequest,
    ProcessingResultSchema,
    ProcessingStatusResponse,
    TokenStatsResponse,
)
from .service import AIProcessorService

logger = logging.getLogger(__name__)

# 创建路由器，所有端点都归属于 "AI Processing" 标签组
# dependencies 中的 require_feature 确保只有启用了 ai_processor 功能时才可访问
router = APIRouter(tags=["AI Processing"], dependencies=[require_feature("feature.ai_processor")])


# -----------------------------------------------------------------------------
# 单篇文章 AI 处理接口
# -----------------------------------------------------------------------------
@router.post("/process", response_model=ProcessingResultSchema)
async def process_article(
    request: ProcessArticleRequest,
    user=Depends(require_permissions("ai:process")),
    db: AsyncSession = Depends(get_session),
):
    """Trigger AI processing for a single article."""
    # 实例化 AI 处理服务（会根据配置自动选择 provider：Ollama 或 OpenAI）
    service = AIProcessorService()
    # 调用服务层处理单篇文章，返回处理结果字典
    result = await service.process_article(request.article_id, db)
    # 如果处理失败且错误信息中包含 "not found"，返回 404 状态码
    if not result.get("success") and "not found" in result.get("error_message", ""):
        raise HTTPException(status_code=404, detail=result["error_message"])
    return ProcessingResultSchema(**result)


# -----------------------------------------------------------------------------
# 批量文章 AI 处理接口
# -----------------------------------------------------------------------------
@router.post("/batch-process", response_model=BatchProcessResponse)
async def batch_process(
    request: BatchProcessRequest,
    user=Depends(require_permissions("ai:process")),
    db: AsyncSession = Depends(get_session),
):
    """Batch process multiple articles."""
    service = AIProcessorService()
    # force 参数控制是否对已处理的文章进行重新处理
    result = await service.batch_process(request.article_ids, db, force=request.force)
    # 构造批量处理响应，包含总数、已处理、缓存命中和失败数
    return BatchProcessResponse(
        total=result["total"],
        processed=result["processed"],
        cached=result["cached"],
        failed=result["failed"],
        results=[ProcessingResultSchema(**r) for r in result["results"]],
    )


# -----------------------------------------------------------------------------
# 查询文章 AI 处理状态接口
# -----------------------------------------------------------------------------
@router.get("/status/{article_id}", response_model=ProcessingStatusResponse)
async def get_processing_status(
    article_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Check AI processing status for an article."""
    # 延迟导入，避免循环依赖
    from apps.crawler.models.article import Article

    # 根据 article_id 查询文章记录
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # 通过 ai_processed_at 是否为 None 来判断文章是否已被 AI 处理过
    return ProcessingStatusResponse(
        article_id=article_id,
        is_processed=article.ai_processed_at is not None,
        processed_at=article.ai_processed_at,
        provider=article.ai_provider,
        model=article.ai_model,
        method=article.processing_method,
    )


# -----------------------------------------------------------------------------
# Token 使用统计接口
# -----------------------------------------------------------------------------
@router.get("/token-stats", response_model=list[TokenStatsResponse])
async def get_token_stats(
    days: int = 7,
    user=Depends(require_permissions("ai:view_stats")),
    db: AsyncSession = Depends(get_session),
):
    """Get token usage statistics."""
    # 计算时间截止点，只统计最近 N 天的数据
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # 按日期、provider、model 分组聚合，计算调用次数、缓存命中率、字符数、平均耗时等
    result = await db.execute(
        select(
            func.date(AIProcessingLog.created_at).label("date"),
            AIProcessingLog.provider,
            AIProcessingLog.model,
            func.count().label("total_calls"),                                  # 总调用次数
            func.sum(AIProcessingLog.cached.cast(Integer)).label("cached_calls"),  # 缓存命中次数
            func.sum(AIProcessingLog.input_chars).label("total_input_chars"),    # 总输入字符数
            func.sum(AIProcessingLog.output_chars).label("total_output_chars"),  # 总输出字符数
            func.avg(AIProcessingLog.duration_ms).label("avg_duration_ms"),      # 平均处理耗时（毫秒）
            func.sum((~AIProcessingLog.success).cast(Integer)).label("failed_calls"),  # 失败次数（对 success 取反后求和）
        )
        .where(AIProcessingLog.created_at >= cutoff)
        .group_by(
            func.date(AIProcessingLog.created_at),
            AIProcessingLog.provider,
            AIProcessingLog.model,
        )
        .order_by(func.date(AIProcessingLog.created_at).desc())
    )
    rows = result.all()
    # 将查询结果逐行转换为响应 Schema，对 None 值进行默认处理
    return [
        TokenStatsResponse(
            date=str(row.date),
            provider=row.provider,
            model=row.model,
            total_calls=row.total_calls or 0,
            cached_calls=row.cached_calls or 0,
            total_input_chars=row.total_input_chars or 0,
            total_output_chars=row.total_output_chars or 0,
            avg_duration_ms=float(row.avg_duration_ms or 0),
            failed_calls=row.failed_calls or 0,
        )
        for row in rows
    ]
