# =============================================================================
# Embedding 向量嵌入元数据模型模块
# =============================================================================
# 本模块定义了文章向量嵌入的元数据 ORM 模型。
# 在架构中的定位：
#   - 向量数据本身存储在 Milvus 向量数据库中（高维浮点向量）
#   - 元数据存储在 MySQL 中（文章 ID、Milvus ID、模型信息等）
#   - 本模型负责管理这种双存储架构的关联信息
#
# 设计决策：
#   将向量存储和元数据存储分离，利用 Milvus 的 ANN 搜索能力处理高效向量检索，
#   同时利用 MySQL 的关系查询能力管理元数据和业务关联。
# =============================================================================

"""Embedding metadata models (vector data stored in Milvus)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# -----------------------------------------------------------------------------
# 文章向量嵌入元数据模型
# 每篇文章对应一条嵌入记录，通过 article_id 唯一关联
# 实际的向量数据存储在 Milvus 中，此表仅保存元数据和引用关系
# -----------------------------------------------------------------------------
class ArticleEmbedding(Base, TimestampMixin):
    """Metadata for article embeddings (vectors stored in Milvus).

    文章嵌入元数据模型。
    """

    __tablename__ = "article_embeddings"

    # 主键，自增 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 关联的文章 ID，唯一约束确保每篇文章只有一个嵌入记录
    article_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, index=True,
        comment="FK to articles table",
    )
    # Milvus 中的主键 ID，用于跨库关联查询和删除操作
    milvus_id: Mapped[str] = mapped_column(
        String(100), nullable=True,
        comment="Primary key in Milvus collection",
    )
    # 嵌入提供商名称（如 "sentence-transformers"、"openai"）
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Embedding provider: sentence-transformers, openai",
    )
    # 使用的具体模型名称（如 "all-MiniLM-L6-v2"、"text-embedding-3-small"）
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Model used for embedding",
    )
    # 向量维度，不同模型输出不同维度
    # 例如：all-MiniLM-L6-v2 -> 384, text-embedding-3-small -> 1536
    dimension: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Vector dimension (384, 1536, etc.)",
    )
    # 嵌入计算完成的时间戳
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
