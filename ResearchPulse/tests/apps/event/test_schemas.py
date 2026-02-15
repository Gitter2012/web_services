"""Tests for apps/event/schemas.py — request/response validation.

事件相关模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestEventSchemas:
    """Validate event schemas.

    事件聚类相关请求/响应模型校验测试。
    """

    def test_trigger_cluster_request_defaults(self):
        """Verify trigger cluster request defaults.

        验证聚类触发请求默认参数。

        Returns:
            None: This test does not return a value.
        """
        from apps.event.schemas import TriggerClusterRequest

        req = TriggerClusterRequest()
        assert req.limit == 100
        assert req.min_importance == 5

    def test_trigger_cluster_request_max(self):
        """Verify trigger cluster request limit bound.

        验证聚类触发请求的最大限制。

        Raises:
            pydantic.ValidationError: When limit exceeds maximum.
        """
        from apps.event.schemas import TriggerClusterRequest

        with pytest.raises(ValidationError):
            TriggerClusterRequest(limit=501)

    def test_event_cluster_schema(self):
        """Verify event cluster schema fields.

        验证事件聚类响应模型字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.event.schemas import EventClusterSchema

        ec = EventClusterSchema(
            id=1,
            title="Test event",
            is_active=True,
            article_count=5,
        )
        assert ec.title == "Test event"
        assert ec.article_count == 5
