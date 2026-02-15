"""Tests for apps/action/schemas.py — request/response validation.

行动项请求与响应模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestActionSchemas:
    """Validate action schema defaults and fields.

    行动项相关请求/响应模型校验测试。
    """

    def test_action_create_request_defaults(self):
        """Verify create request default values.

        验证创建请求的默认类型与优先级。

        Returns:
            None: This test does not return a value.
        """
        from apps.action.schemas import ActionItemCreateRequest

        req = ActionItemCreateRequest(
            article_id=42,
            description="Read the paper",
        )
        assert req.type == "跟进"
        assert req.priority == "中"

    def test_action_update_all_optional(self):
        """Verify update request fields are optional.

        验证更新请求的字段可全部为空。

        Returns:
            None: This test does not return a value.
        """
        from apps.action.schemas import ActionItemUpdateRequest

        req = ActionItemUpdateRequest()
        assert req.type is None
        assert req.description is None
        assert req.priority is None

    def test_action_item_schema(self):
        """Verify action item schema fields.

        验证行动项响应模型字段映射正确。

        Returns:
            None: This test does not return a value.
        """
        from apps.action.schemas import ActionItemSchema

        item = ActionItemSchema(
            id=1,
            article_id=42,
            user_id=1,
            type="跟进",
            description="Read it",
            priority="高",
            status="pending",
        )
        assert item.status == "pending"
