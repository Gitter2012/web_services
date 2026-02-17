"""Tests for apps/ui/api.py — _article_to_dict content field fix.

验证 _article_to_dict 函数在返回字典中包含 content 字段。
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone


class TestArticleToDict:
    """Test _article_to_dict helper function.

    验证 ORM 文章对象到字典的转换包含完整的 content 字段。
    """

    def _make_article(self, **overrides):
        """Create a mock Article instance with sensible defaults.

        构造一个 mock Article 对象用于测试。

        Args:
            **overrides: Field overrides for the mock.

        Returns:
            MagicMock: Mock Article instance.
        """
        defaults = {
            "id": 1,
            "source_type": "rss",
            "title": "Test Article",
            "url": "https://example.com/article",
            "author": "Test Author",
            "summary": "Short summary",
            "content": "<p>Full article content with details.</p>",
            "content_summary": "AI generated summary",
            "category": "tech",
            "tags": ["python", "web"],
            "publish_time": datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
            "crawl_time": datetime(2025, 1, 15, 13, 0, tzinfo=timezone.utc),
            "cover_image_url": "https://example.com/cover.jpg",
            "is_archived": False,
            "arxiv_id": None,
            "arxiv_primary_category": None,
            "arxiv_updated_time": None,
            "wechat_account_name": None,
        }
        defaults.update(overrides)

        article = MagicMock()
        for key, value in defaults.items():
            setattr(article, key, value)
        return article

    def test_content_field_present_in_dict(self):
        """Verify 'content' key exists in the returned dictionary.

        验证返回字典中包含 'content' 键。
        """
        from apps.ui.api import _article_to_dict

        article = self._make_article(content="<p>Full content here</p>")
        result = _article_to_dict(article)

        assert "content" in result
        assert result["content"] == "<p>Full content here</p>"

    def test_content_field_with_none_returns_empty_string(self):
        """Verify content=None returns empty string.

        验证 content 为 None 时返回空字符串。
        """
        from apps.ui.api import _article_to_dict

        article = self._make_article(content=None)
        result = _article_to_dict(article)

        assert "content" in result
        assert result["content"] == ""

    def test_content_field_with_empty_string(self):
        """Verify content='' returns empty string.

        验证 content 为空字符串时返回空字符串。
        """
        from apps.ui.api import _article_to_dict

        article = self._make_article(content="")
        result = _article_to_dict(article)

        assert "content" in result
        assert result["content"] == ""

    def test_content_field_is_distinct_from_summary(self):
        """Verify content and summary are separate fields.

        验证 content 和 summary 是独立的字段，可以有不同值。
        """
        from apps.ui.api import _article_to_dict

        article = self._make_article(
            summary="Brief overview of the article.",
            content="<p>Full detailed article body with complete explanation.</p>",
        )
        result = _article_to_dict(article)

        assert result["summary"] != result["content"]
        assert result["summary"] == "Brief overview of the article."
        assert result["content"] == "<p>Full detailed article body with complete explanation.</p>"

    def test_summary_field_still_present(self):
        """Verify summary field is not removed by the content fix.

        验证添加 content 字段后，summary 字段仍然正常存在。
        """
        from apps.ui.api import _article_to_dict

        article = self._make_article(summary="Test summary")
        result = _article_to_dict(article)

        assert "summary" in result
        assert result["summary"] == "Test summary"

    def test_all_expected_fields_present(self):
        """Verify all expected fields are present in the output dict.

        验证输出字典包含所有期望的字段。
        """
        from apps.ui.api import _article_to_dict

        article = self._make_article()
        result = _article_to_dict(article)

        expected_keys = {
            "id", "source_type", "title", "url", "author",
            "summary", "content", "content_summary",
            "category", "tags", "publish_time", "crawl_time",
            "cover_image_url", "is_archived",
            "arxiv_id", "arxiv_primary_category", "arxiv_updated_time",
            "wechat_account_name",
        }
        assert expected_keys.issubset(set(result.keys())), (
            f"Missing keys: {expected_keys - set(result.keys())}"
        )

    def test_rss_article_with_rich_content(self):
        """Verify RSS article with full HTML content converts correctly.

        验证包含完整 HTML 正文的 RSS 文章正确转换。
        """
        from apps.ui.api import _article_to_dict

        html_content = """
        <h2>Introduction</h2>
        <p>This is a detailed article about Python web development.</p>
        <h2>Main Content</h2>
        <p>Here we discuss the key concepts and best practices.</p>
        """
        article = self._make_article(
            source_type="rss",
            summary="Article about Python web dev.",
            content=html_content,
        )
        result = _article_to_dict(article)

        assert result["content"] == html_content
        assert result["summary"] == "Article about Python web dev."

    def test_arxiv_article_content(self):
        """Verify arXiv article content (typically same as abstract) converts correctly.

        验证 arXiv 文章（content 通常是摘要）的转换。
        """
        from apps.ui.api import _article_to_dict

        abstract = "We present a novel approach to natural language processing..."
        article = self._make_article(
            source_type="arxiv",
            summary=abstract,
            content=abstract,
            arxiv_id="2401.12345",
            arxiv_primary_category="cs.CL",
        )
        result = _article_to_dict(article)

        assert result["content"] == abstract
        assert result["arxiv_id"] == "2401.12345"


class TestExportAuth:
    """Test export endpoint authentication (L2 fix).

    验证 Markdown 导出端点需要认证。
    """

    def test_export_markdown_unauthenticated(self, client):
        """GET /api/export/markdown requires authentication (L2 fix).

        未认证访问导出端点应返回 401。
        """
        from fastapi.testclient import TestClient

        response = client.get("/researchpulse/api/export/markdown")
        assert response.status_code == 401

    def test_export_markdown_authenticated(self, client, auth_headers):
        """GET /api/export/markdown allowed for authenticated user.

        已认证用户可访问导出端点。
        """
        from fastapi.testclient import TestClient

        response = client.get(
            "/researchpulse/api/export/markdown",
            headers=auth_headers,
        )
        # Should not be 401/403 -- permission passed
        assert response.status_code not in [401, 403]
