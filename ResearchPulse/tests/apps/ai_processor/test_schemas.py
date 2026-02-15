"""Tests for apps/ai_processor/schemas.py — request/response validation.

AI 处理请求与响应模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestAIProcessorSchemas:
    """Validate AI processor schemas.

    AI 处理相关模型校验测试。
    """

    def test_process_article_request(self):
        """Verify single-article request schema.

        验证单篇文章处理请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.ai_processor.schemas import ProcessArticleRequest

        req = ProcessArticleRequest(article_id=42)
        assert req.article_id == 42

    def test_batch_process_request(self):
        """Verify batch process request schema.

        验证批量处理请求模型与默认值。

        Returns:
            None: This test does not return a value.
        """
        from apps.ai_processor.schemas import BatchProcessRequest

        req = BatchProcessRequest(article_ids=[1, 2, 3])
        assert len(req.article_ids) == 3
        assert req.force is False

    def test_batch_process_max_100(self):
        """Verify batch request size limit.

        验证批量处理请求最大数量限制。

        Raises:
            pydantic.ValidationError: When list exceeds max size.
        """
        from apps.ai_processor.schemas import BatchProcessRequest

        with pytest.raises(ValidationError):
            BatchProcessRequest(article_ids=list(range(101)))

    def test_processing_result_schema(self):
        """Verify processing result schema defaults.

        验证处理结果模型字段与默认值。

        Returns:
            None: This test does not return a value.
        """
        from apps.ai_processor.schemas import ProcessingResultSchema

        result = ProcessingResultSchema(
            article_id=1,
            success=True,
            summary="Test summary",
            importance_score=8,
            one_liner="One line",
            key_points=[],
            actionable_items=[],
            provider="ollama",
            model="qwen3:32b",
            processing_method="full",
        )
        assert result.article_id == 1
        assert result.success is True
        assert result.category == "其他"  # default

    def test_key_point_schema(self):
        """Verify key point schema fields.

        验证关键点模型字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.ai_processor.schemas import KeyPointSchema

        kp = KeyPointSchema(type="技术突破", value="Something", impact="高")
        assert kp.type == "技术突破"
