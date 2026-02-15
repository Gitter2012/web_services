"""Tests for apps/topic/schemas.py — request/response validation.

话题相关模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestTopicSchemas:
    """Validate topic schemas.

    话题请求与响应模型校验测试。
    """

    def test_topic_create_request(self):
        """Verify topic create request schema.

        验证话题创建请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.topic.schemas import TopicCreateRequest

        req = TopicCreateRequest(
            name="LLM Research",
            description="Large Language Model research",
            keywords=["LLM", "GPT"],
        )
        assert req.name == "LLM Research"
        assert len(req.keywords) == 2

    def test_topic_create_name_max_length(self):
        """Verify topic name length validation.

        验证话题名称长度上限校验。

        Raises:
            pydantic.ValidationError: When name exceeds max length.
        """
        from apps.topic.schemas import TopicCreateRequest

        with pytest.raises(ValidationError):
            TopicCreateRequest(
                name="a" * 101,
                description="too long name",
                keywords=["x"],
            )

    def test_topic_update_all_optional(self):
        """Verify topic update request optional fields.

        验证话题更新请求字段可全部为空。

        Returns:
            None: This test does not return a value.
        """
        from apps.topic.schemas import TopicUpdateRequest

        req = TopicUpdateRequest()
        assert req.name is None
        assert req.description is None
        assert req.keywords is None
        assert req.is_active is None

    def test_topic_trend_schema(self):
        """Verify topic trend schema fields.

        验证话题趋势响应模型字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.topic.schemas import TopicTrendSchema

        trend = TopicTrendSchema(
            direction="up",
            change_percent=25.0,
            current_count=15,
            previous_count=12,
        )
        assert trend.direction == "up"
