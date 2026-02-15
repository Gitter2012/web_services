# =============================================================================
# Embedding 向量嵌入 Pydantic 数据校验模块
# =============================================================================
# 本模块定义了 Embedding API 所有端点的请求和响应数据结构。
# 使用 Pydantic BaseModel 实现自动的数据验证、序列化和文档生成。
# 主要包含：
#   - 请求模型：ComputeEmbeddingRequest, BatchComputeRequest
#   - 响应模型：ComputeEmbeddingResponse, BatchComputeResponse,
#               SimilarArticlesResponse, EmbeddingStatsResponse
#   - 子结构：SimilarArticleSchema
# =============================================================================

"""Embedding Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# 单篇文章嵌入计算请求
# 仅包含文章 ID
# -----------------------------------------------------------------------------
class ComputeEmbeddingRequest(BaseModel):
    """Request schema for single embedding computation.

    单篇文章嵌入计算请求。

    Attributes:
        article_id: Article ID.
    """

    article_id: int


# -----------------------------------------------------------------------------
# 批量嵌入计算请求
# article_ids 最多 1000 篇，防止单次请求过大
# （嵌入计算比 AI 处理轻量得多，所以上限比 AI 批处理的 100 高）
# -----------------------------------------------------------------------------
class BatchComputeRequest(BaseModel):
    """Request schema for batch embedding computation.

    批量嵌入计算请求。

    Attributes:
        article_ids: List of article IDs.
    """

    article_ids: list[int] = Field(default_factory=list, max_length=1000)


# -----------------------------------------------------------------------------
# 相似文章 Schema
# 表示一篇与查询文章相似的文章及其相似度分数
# -----------------------------------------------------------------------------
class SimilarArticleSchema(BaseModel):
    """Schema for a similar article entry.

    相似文章条目。

    Attributes:
        article_id: Similar article ID.
        title: Article title.
        similarity_score: Cosine similarity score.
    """

    article_id: int               # 相似文章的 ID
    title: str = ""               # 相似文章的标题
    similarity_score: float = 0.0  # 余弦相似度分数（0.0 - 1.0）


# -----------------------------------------------------------------------------
# 相似文章查询响应
# 包含查询的文章 ID 和相似文章列表
# -----------------------------------------------------------------------------
class SimilarArticlesResponse(BaseModel):
    """Response schema for similar article search.

    相似文章查询响应。

    Attributes:
        article_id: Source article ID.
        similar_articles: Similar article list.
    """

    article_id: int                                                            # 查询的源文章 ID
    similar_articles: list[SimilarArticleSchema] = Field(default_factory=list)  # 相似文章列表


# -----------------------------------------------------------------------------
# 单篇嵌入计算响应
# 返回计算结果的详细信息
# -----------------------------------------------------------------------------
class ComputeEmbeddingResponse(BaseModel):
    """Response schema for single embedding computation.

    单篇嵌入计算响应。

    Attributes:
        article_id: Article ID.
        success: Whether computation succeeded.
        provider: Embedding provider name.
        model: Model name.
        dimension: Vector dimension.
        error_message: Error message on failure.
    """

    article_id: int
    success: bool = True              # 是否计算成功
    provider: str = ""                # 使用的嵌入提供商
    model: str = ""                   # 使用的模型名称
    dimension: int = 0                # 向量维度
    error_message: Optional[str] = None  # 错误信息（失败时）


# -----------------------------------------------------------------------------
# 批量嵌入计算响应
# 汇总批量计算的整体结果统计
# -----------------------------------------------------------------------------
class BatchComputeResponse(BaseModel):
    """Response schema for batch embedding computation.

    批量嵌入计算响应。

    Attributes:
        total: Total requested.
        computed: Computed count.
        skipped: Skipped count (already computed).
        failed: Failed count.
    """

    total: int = 0     # 请求计算的总数
    computed: int = 0  # 成功计算的数量
    skipped: int = 0   # 跳过的数量（已有嵌入的文章）
    failed: int = 0    # 计算失败的数量


# -----------------------------------------------------------------------------
# 嵌入统计信息响应
# 用于系统状态监控仪表盘
# -----------------------------------------------------------------------------
class EmbeddingStatsResponse(BaseModel):
    """Response schema for embedding statistics.

    嵌入统计信息响应。

    Attributes:
        total_embeddings: Total computed embeddings.
        provider: Current provider.
        model: Current model.
        dimension: Vector dimension.
        milvus_connected: Milvus connection status.
        collection_count: Vector count in Milvus collection.
    """

    total_embeddings: int = 0     # 已计算的嵌入总数
    provider: str = ""            # 当前配置的嵌入提供商
    model: str = ""               # 当前配置的嵌入模型
    dimension: int = 0            # 当前向量维度
    milvus_connected: bool = False  # Milvus 是否已连接
    collection_count: int = 0     # Milvus 集合中的向量数量
