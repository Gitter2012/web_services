# =============================================================================
# Embedding 向量嵌入 API 端点模块
# =============================================================================
# 本模块定义了文章向量嵌入相关的 RESTful API 接口。
# 在架构中，它是 Embedding 子系统对外暴露的 HTTP 层，负责：
#   1. 单篇/批量文章的向量嵌入计算
#   2. 基于向量相似度的相似文章查询
#   3. 嵌入统计信息查询
#   4. Milvus 向量索引重建
# 所有端点均需启用 "feature.embedding" 功能开关才可访问。
# =============================================================================

"""Embedding API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import get_current_user, require_permissions

from common.feature_config import require_feature

from .schemas import (
    BatchComputeRequest,
    BatchComputeResponse,
    ComputeEmbeddingRequest,
    ComputeEmbeddingResponse,
    EmbeddingStatsResponse,
    SimilarArticlesResponse,
    SimilarArticleSchema,
)
from .service import EmbeddingService

logger = logging.getLogger(__name__)

# 创建路由器，所有端点归属于 "Embedding" 标签组
# 通过 require_feature 依赖确保只有启用了 embedding 功能时才可访问
router = APIRouter(tags=["Embedding"], dependencies=[require_feature("feature.embedding")])


# -----------------------------------------------------------------------------
# 单篇文章嵌入计算接口
# 为指定文章生成向量嵌入并存入 Milvus
# -----------------------------------------------------------------------------
@router.post("/compute", response_model=ComputeEmbeddingResponse)
async def compute_embedding(
    request: ComputeEmbeddingRequest,
    user=Depends(require_permissions("embedding:compute")),
    db: AsyncSession = Depends(get_session),
):
    """Compute embedding for a single article.

    为指定文章计算向量嵌入。

    Args:
        request: Compute embedding request payload.
        user: Authenticated user.
        db: Async database session.

    Returns:
        ComputeEmbeddingResponse: Embedding computation result.

    Raises:
        HTTPException: If article not found.
    """
    service = EmbeddingService()
    result = await service.compute_embedding(request.article_id, db)
    # 如果文章未找到，返回 404
    if not result.get("success") and "not found" in result.get("error_message", ""):
        raise HTTPException(status_code=404, detail=result["error_message"])
    return ComputeEmbeddingResponse(
        article_id=request.article_id,
        success=result.get("success", False),
        provider=result.get("provider", ""),
        model=result.get("model", ""),
        dimension=result.get("dimension", 0),   # 向量维度（如 384、1536）
        error_message=result.get("error_message"),
    )


# -----------------------------------------------------------------------------
# 批量嵌入计算接口
# 对多篇文章进行批量向量嵌入计算
# -----------------------------------------------------------------------------
@router.post("/batch", response_model=BatchComputeResponse)
async def batch_compute(
    request: BatchComputeRequest,
    user=Depends(require_permissions("embedding:compute")),
    db: AsyncSession = Depends(get_session),
):
    """Batch compute embeddings.

    批量计算文章嵌入向量。

    Args:
        request: Batch compute request payload.
        user: Authenticated user.
        db: Async database session.

    Returns:
        BatchComputeResponse: Batch computation summary.
    """
    service = EmbeddingService()
    result = await service.batch_compute(request.article_ids, db)
    return BatchComputeResponse(**result)


# -----------------------------------------------------------------------------
# 相似文章查询接口
# 基于 Milvus 向量搜索查找与指定文章最相似的文章
# -----------------------------------------------------------------------------
@router.get("/similar/{article_id}", response_model=SimilarArticlesResponse)
async def find_similar(
    article_id: int,
    top_k: int = 10,  # 返回最相似的文章数量，默认 10
    db: AsyncSession = Depends(get_session),
):
    """Find similar articles using Milvus vector search.

    基于向量相似度检索相似文章。

    Args:
        article_id: Target article ID.
        top_k: Number of similar articles to return.
        db: Async database session.

    Returns:
        SimilarArticlesResponse: Similar article list.
    """
    service = EmbeddingService()
    similar = await service.find_similar(article_id, db, top_k=top_k)
    return SimilarArticlesResponse(
        article_id=article_id,
        similar_articles=[SimilarArticleSchema(**s) for s in similar],
    )


# -----------------------------------------------------------------------------
# 嵌入统计信息查询接口
# 返回总嵌入数量、使用的 provider/model、Milvus 连接状态等
# -----------------------------------------------------------------------------
@router.get("/stats", response_model=EmbeddingStatsResponse)
async def get_stats(
    user=Depends(require_permissions("embedding:compute")),
    db: AsyncSession = Depends(get_session),
):
    """Get embedding statistics.

    查询嵌入统计信息。

    Args:
        user: Authenticated user.
        db: Async database session.

    Returns:
        EmbeddingStatsResponse: Embedding stats payload.
    """
    service = EmbeddingService()
    stats = await service.get_stats(db)
    return EmbeddingStatsResponse(**stats)


# -----------------------------------------------------------------------------
# Milvus 向量索引重建接口
# 删除并重新创建 Milvus 集合索引，用于索引损坏或参数变更后的修复
# 注意：这是一个重量级操作，会导致搜索短暂不可用
# -----------------------------------------------------------------------------
@router.post("/rebuild")
async def rebuild_index(
    user=Depends(require_permissions("embedding:rebuild")),
):
    """Rebuild Milvus index.

    重建 Milvus 向量索引。

    Args:
        user: Authenticated user.

    Returns:
        dict: Status message.

    Raises:
        HTTPException: If Milvus is unavailable or rebuild fails.
    """
    from .milvus_client import MilvusClient
    client = MilvusClient()
    # 尝试连接 Milvus，连接失败返回 503
    if not client.connect():
        raise HTTPException(status_code=503, detail="Cannot connect to Milvus")
    # 执行索引重建，维度默认 384（对应 all-MiniLM-L6-v2 模型）
    success = client.rebuild_index(dimension=384)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to rebuild index")
    return {"status": "ok", "message": "Milvus index rebuilt successfully"}
