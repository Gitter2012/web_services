# =============================================================================
# Embedding 向量嵌入服务层模块
# =============================================================================
# 本模块是 Embedding 子系统的核心业务逻辑层，负责：
#   1. 为文章生成向量嵌入（通过 Embedding Provider）
#   2. 将向量存储到 Milvus 向量数据库
#   3. 将元数据存储到 MySQL
#   4. 基于向量相似度查找相似文章
#   5. 查询嵌入统计信息
#
# 数据流：
#   文章 -> 拼接标题+摘要 -> Embedding Provider 编码 -> Milvus 存储 -> MySQL 元数据
#
# 设计决策：
#   - 嵌入计算是 CPU 密集型操作，使用 asyncio.to_thread 放到线程池中执行
#   - Milvus 客户端采用懒连接模式，首次使用时才建立连接
#   - 支持在无 Milvus 的环境下运行（仅生成元数据，不存储向量）
# =============================================================================

"""Embedding service layer."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from settings import settings

from .models import ArticleEmbedding
from .milvus_client import MilvusClient
from .providers.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Get the configured embedding provider.

    根据配置选择嵌入提供商（OpenAI 或本地模型）。

    Returns:
        BaseEmbeddingProvider: Provider instance.
    """
    # 根据配置选择嵌入提供商
    # "openai": 使用 OpenAI API，质量高但有成本
    # 其他（默认）: 使用本地 sentence-transformers，免费且数据不离开本机
    if settings.embedding_provider == "openai":
        from .providers.openai_provider import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider()
    else:
        from .providers.sentence_transformer import SentenceTransformerProvider
        return SentenceTransformerProvider(model_name=settings.embedding_model)


# -----------------------------------------------------------------------------
# Embedding 服务类
# 封装所有向量嵌入相关的业务逻辑。
# 设计决策：
#   - 支持依赖注入（provider 和 milvus 都可通过构造函数传入），方便单元测试
#   - Milvus 采用懒初始化，避免启动时的连接开销
# -----------------------------------------------------------------------------
class EmbeddingService:
    """Service for computing and managing article embeddings.

    向量嵌入服务层，负责计算、存储与相似度检索。
    """

    def __init__(
        self,
        provider: BaseEmbeddingProvider | None = None,
        milvus: MilvusClient | None = None,
    ):
        """Initialize embedding service.

        初始化嵌入服务，支持注入 provider 与 Milvus 客户端。

        Args:
            provider: Embedding provider override.
            milvus: Milvus client override.
        """
        # 嵌入提供商，未传入则根据配置自动创建
        self.provider = provider or get_embedding_provider()
        # Milvus 客户端实例，支持外部注入
        self._milvus = milvus
        # Milvus 连接状态标记，避免重复连接
        self._milvus_initialized = False

    def _get_milvus(self) -> MilvusClient | None:
        """Get Milvus client, connecting lazily.

        懒初始化 Milvus 客户端。

        Returns:
            MilvusClient | None: Connected client or ``None`` if disabled/unavailable.
        """
        # 懒初始化 Milvus 客户端：首次调用时创建并连接
        # 如果 embedding 功能未启用，直接返回 None
        if not settings.embedding_enabled:
            return None
        if self._milvus is None:
            self._milvus = MilvusClient()
        # 尝试建立连接（仅在未初始化时执行）
        if not self._milvus_initialized:
            if self._milvus.connect():
                self._milvus_initialized = True
            else:
                return None  # 连接失败返回 None，上层会优雅降级
        return self._milvus

    async def compute_embedding(
        self, article_id: int, db: AsyncSession
    ) -> dict:
        """Compute embedding for a single article.

        为单篇文章生成向量嵌入并写入元数据。

        Args:
            article_id: Article ID.
            db: Async database session.

        Returns:
            dict: Result payload including status and metadata.
        """
        # 第一步：查询文章
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            return {"success": False, "error_message": f"Article {article_id} not found"}

        # 第二步：检查是否已计算过嵌入（幂等性保障）
        existing = await db.execute(
            select(ArticleEmbedding).where(ArticleEmbedding.article_id == article_id)
        )
        if existing.scalar_one_or_none():
            return {"success": True, "article_id": article_id, "provider": "cached"}

        # 第三步：构建用于嵌入的文本
        # 拼接标题和摘要（优先使用 AI 摘要，其次使用原始摘要）
        text = f"{article.title or ''} {article.ai_summary or article.summary or ''}"
        # 截断到 2000 字符，超长文本不会显著提升嵌入质量
        if len(text) > 2000:
            text = text[:2000]

        # 第四步：计算嵌入向量
        # 使用 asyncio.to_thread 将 CPU 密集型的编码操作放到线程池
        # 避免阻塞事件循环
        embedding = await asyncio.to_thread(self.provider.encode, text)
        dimension = len(embedding)

        # 第五步：存储向量到 Milvus
        milvus = self._get_milvus()
        milvus_id = None
        if milvus:
            try:
                ids = milvus.insert_vectors([article_id], [embedding])
                milvus_id = str(ids[0]) if ids else None
            except Exception as e:
                # Milvus 写入失败不阻断整个流程，仅记录警告
                logger.warning(f"Milvus insert failed for article {article_id}: {e}")

        # 第六步：存储元数据到 MySQL
        meta = ArticleEmbedding(
            article_id=article_id,
            milvus_id=milvus_id,
            provider=settings.embedding_provider,
            model_name=settings.embedding_model,
            dimension=dimension,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(meta)

        return {
            "success": True,
            "article_id": article_id,
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "dimension": dimension,
        }

    async def batch_compute(
        self, article_ids: list[int], db: AsyncSession
    ) -> dict:
        """Batch compute embeddings using bulk encoding.

        批量计算文章嵌入，使用 encode_batch 一次性编码所有文本，
        并批量写入 Milvus 和 MySQL，显著提升吞吐量。

        Args:
            article_ids: Article ID list.
            db: Async database session.

        Returns:
            dict: Summary of computed/skipped/failed counts.
        """
        if not article_ids:
            return {"total": 0, "computed": 0, "skipped": 0, "failed": 0}

        computed = 0
        skipped = 0
        failed = 0

        # 第一步：批量查询文章
        result = await db.execute(
            select(Article).where(Article.id.in_(article_ids))
        )
        articles = {a.id: a for a in result.scalars().all()}

        # 第二步：批量检查已有嵌入（幂等性保障）
        existing_result = await db.execute(
            select(ArticleEmbedding.article_id).where(
                ArticleEmbedding.article_id.in_(article_ids)
            )
        )
        existing_ids = {row[0] for row in existing_result.all()}

        # 第三步：构建待编码的文本列表
        to_encode_ids: list[int] = []
        to_encode_texts: list[str] = []
        for aid in article_ids:
            if aid in existing_ids:
                skipped += 1
                continue
            article = articles.get(aid)
            if not article:
                failed += 1
                continue
            text = f"{article.title or ''} {article.ai_summary or article.summary or ''}"
            if len(text) > 2000:
                text = text[:2000]
            to_encode_ids.append(aid)
            to_encode_texts.append(text)

        if not to_encode_texts:
            return {"total": len(article_ids), "computed": computed, "skipped": skipped, "failed": failed}

        # 第四步：批量编码（使用 encode_batch，通过线程池避免阻塞事件循环）
        try:
            embeddings = await asyncio.to_thread(self.provider.encode_batch, to_encode_texts)
        except Exception as e:
            logger.error(f"Batch encoding failed: {e}")
            return {"total": len(article_ids), "computed": 0, "skipped": skipped, "failed": failed + len(to_encode_texts)}

        # 第五步：批量写入 Milvus
        milvus = self._get_milvus()
        milvus_ids_map: dict[int, str] = {}
        if milvus:
            try:
                ids = milvus.insert_vectors(to_encode_ids, embeddings)
                if ids:
                    for i, aid in enumerate(to_encode_ids):
                        if i < len(ids):
                            milvus_ids_map[aid] = str(ids[i])
            except Exception as e:
                logger.warning(f"Milvus batch insert failed: {e}")

        # 第六步：批量创建 MySQL 元数据记录
        dimension = len(embeddings[0]) if embeddings else settings.embedding_dimension
        now = datetime.now(timezone.utc)
        meta_records = []
        for aid in to_encode_ids:
            meta_records.append(ArticleEmbedding(
                article_id=aid,
                milvus_id=milvus_ids_map.get(aid),
                provider=settings.embedding_provider,
                model_name=settings.embedding_model,
                dimension=dimension,
                computed_at=now,
            ))
            computed += 1
        db.add_all(meta_records)

        return {
            "total": len(article_ids),
            "computed": computed,
            "skipped": skipped,
            "failed": failed,
        }

    async def compute_uncomputed(self, db: AsyncSession, limit: int = 100) -> dict:
        """Compute embeddings for articles missing them.

        查找未计算嵌入的文章并进行批量计算。

        Args:
            db: Async database session.
            limit: Max number of articles to process.

        Returns:
            dict: Batch computation summary.
        """
        # 查找尚未计算嵌入的文章（需已经过 AI 处理且未归档）
        # 通过 LEFT JOIN + IS NULL 找到没有嵌入记录的文章
        # 此方法通常由定时调度任务调用
        from sqlalchemy import and_

        result = await db.execute(
            select(Article.id)
            .outerjoin(ArticleEmbedding, Article.id == ArticleEmbedding.article_id)
            .where(
                and_(
                    ArticleEmbedding.id.is_(None),       # 没有嵌入记录
                    Article.is_archived.is_(False),       # 未归档
                    Article.ai_processed_at.isnot(None),  # 已经过 AI 处理（确保有摘要可用）
                )
            )
            .order_by(Article.crawl_time.desc())
            .limit(limit)
        )
        article_ids = [row[0] for row in result.all()]
        if not article_ids:
            return {"total": 0, "computed": 0, "skipped": 0, "failed": 0}
        return await self.batch_compute(article_ids, db)

    async def find_similar(
        self, article_id: int, db: AsyncSession, top_k: int = 10
    ) -> list[dict]:
        """Find similar articles using Milvus vector search.

        基于向量相似度检索相似文章。

        Args:
            article_id: Source article ID.
            db: Async database session.
            top_k: Number of similar articles to return.

        Returns:
            list[dict]: Similar article entries with scores.
        """
        # 第一步：获取源文章信息
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            return []

        # 第二步：构建文本并计算嵌入向量（作为查询向量）
        text = f"{article.title or ''} {article.ai_summary or article.summary or ''}"
        if len(text) > 2000:
            text = text[:2000]

        # 在线程池中计算查询向量
        embedding = await asyncio.to_thread(self.provider.encode, text)

        # 第三步：在 Milvus 中搜索相似向量
        milvus = self._get_milvus()
        if not milvus:
            return []  # Milvus 不可用时返回空列表

        try:
            # 排除自身文章，避免搜索结果包含查询文章本身
            matches = milvus.search_similar(
                embedding, top_k=top_k, exclude_article_id=article_id
            )
        except Exception as e:
            logger.warning(f"Milvus search failed: {e}")
            return []

        # 第四步：批量查询匹配文章的标题信息
        # 过滤掉相似度过低的结果（低于阈值的 50%）
        min_score = settings.embedding_similarity_threshold * 0.5
        valid_matches = [
            (mid, score) for mid, score in matches if score >= min_score
        ]
        if not valid_matches:
            return []

        matched_ids = [mid for mid, _ in valid_matches]
        score_map = {mid: score for mid, score in valid_matches}

        result = await db.execute(
            select(Article.id, Article.title).where(Article.id.in_(matched_ids))
        )
        rows = {row[0]: row[1] for row in result.all()}

        similar = []
        for mid in matched_ids:
            if mid in rows:
                similar.append({
                    "article_id": mid,
                    "title": rows[mid] or "",
                    "similarity_score": round(score_map[mid], 4),
                })

        return similar

    async def get_stats(self, db: AsyncSession) -> dict:
        """Get embedding statistics.

        获取嵌入统计信息。

        Args:
            db: Async database session.

        Returns:
            dict: Embedding statistics payload.
        """
        # 获取嵌入系统的统计信息，用于状态监控
        from sqlalchemy import func

        # 查询 MySQL 中的嵌入记录总数
        result = await db.execute(select(func.count()).select_from(ArticleEmbedding))
        total = result.scalar() or 0

        # 检查 Milvus 连接状态和集合中的向量数量
        milvus = self._get_milvus()
        milvus_connected = milvus is not None and milvus.is_connected
        collection_count = 0
        if milvus and milvus_connected:
            stats = milvus.get_collection_stats()
            collection_count = stats.get("num_entities", 0)

        return {
            "total_embeddings": total,
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "dimension": settings.embedding_dimension,
            "milvus_connected": milvus_connected,
            "collection_count": collection_count,
        }
