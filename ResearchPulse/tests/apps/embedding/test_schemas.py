"""Tests for apps/embedding/schemas.py — request/response validation.

嵌入计算相关模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestEmbeddingSchemas:
    """Validate embedding schemas.

    向量嵌入相关模型校验测试。
    """

    def test_compute_embedding_request(self):
        """Verify compute-embedding request schema.

        验证单条嵌入请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.embedding.schemas import ComputeEmbeddingRequest

        req = ComputeEmbeddingRequest(article_id=1)
        assert req.article_id == 1

    def test_batch_compute_request(self):
        """Verify batch compute request schema.

        验证批量嵌入请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.embedding.schemas import BatchComputeRequest

        req = BatchComputeRequest(article_ids=[1, 2, 3, 4, 5])
        assert len(req.article_ids) == 5

    def test_batch_compute_max_1000(self):
        """Verify batch compute request size limit.

        验证批量嵌入请求最大数量限制。

        Raises:
            pydantic.ValidationError: When list exceeds max size.
        """
        from apps.embedding.schemas import BatchComputeRequest

        with pytest.raises(ValidationError):
            BatchComputeRequest(article_ids=list(range(1001)))

    def test_similar_article_schema(self):
        """Verify similar-article schema fields.

        验证相似文章响应模型字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.embedding.schemas import SimilarArticleSchema

        sa = SimilarArticleSchema(
            article_id=42, title="Test", similarity_score=0.92
        )
        assert sa.similarity_score == 0.92

    def test_embedding_stats_response(self):
        """Verify embedding stats response model.

        验证嵌入统计响应模型字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.embedding.schemas import EmbeddingStatsResponse

        resp = EmbeddingStatsResponse(
            total_embeddings=5000,
            provider="sentence-transformers",
            model="all-MiniLM-L6-v2",
            dimension=384,
            milvus_connected=True,
            collection_count=5000,
        )
        assert resp.dimension == 384
