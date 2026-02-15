"""Tests for apps/report/schemas.py — request/response validation.

报告相关模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestReportSchemas:
    """Validate report schemas.

    报告请求与响应模型校验测试。
    """

    def test_generate_report_request_default(self):
        """Verify report request default values.

        验证生成报告请求默认参数。

        Returns:
            None: This test does not return a value.
        """
        from apps.report.schemas import GenerateReportRequest

        req = GenerateReportRequest()
        assert req.weeks_ago == 0

    def test_generate_report_request_bounds(self):
        """Verify report request bounds validation.

        验证周报请求参数边界校验。

        Raises:
            pydantic.ValidationError: When weeks_ago exceeds bounds.
        """
        from apps.report.schemas import GenerateReportRequest

        with pytest.raises(ValidationError):
            GenerateReportRequest(weeks_ago=53)

    def test_report_schema(self):
        """Verify report schema fields.

        验证报告响应模型字段映射。

        Returns:
            None: This test does not return a value.
        """
        from apps.report.schemas import ReportSchema

        r = ReportSchema(
            id=1,
            user_id=1,
            type="weekly",
            period_start="2026-01-06",
            period_end="2026-01-12",
            title="Test report",
            content="Content here",
        )
        assert r.type == "weekly"
