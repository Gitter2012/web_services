"""Tests for apps/ui/templates/index.html — Frontend content display fix.

验证前端模板中优先使用 content 字段展示文章内容。
"""

from __future__ import annotations

import os
import pytest


class TestIndexTemplate:
    """Test index.html template content display logic.

    验证前端模板中文章内容展示优先使用 content 字段。
    """

    @pytest.fixture
    def template_content(self):
        """Load the index.html template content.

        读取 index.html 模板文件内容。

        Returns:
            str: Template file content.
        """
        template_path = os.path.join(
            os.path.dirname(__file__),
            os.pardir, os.pardir, os.pardir,
            "apps", "ui", "templates", "index.html",
        )
        template_path = os.path.normpath(template_path)
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_uses_content_field_priority(self, template_content):
        """Verify template prioritizes article.content over article.summary.

        验证模板中 stripHtml 调用优先使用 article.content。
        """
        # The fix changes: stripHtml(article.summary || '')
        # To: stripHtml(article.content || article.summary || '')
        assert "article.content || article.summary" in template_content

    def test_does_not_use_summary_only(self, template_content):
        """Verify template does not use summary-only pattern for content display.

        验证模板不再使用只用 summary 的旧模式来展示文章内容。
        """
        # The old pattern was: stripHtml(article.summary || '')
        # After fix, this should NOT appear for content display
        # (Check that the specific line using stripHtml uses content first)
        import re
        # Find all stripHtml calls — the content display one should include article.content
        strip_html_calls = re.findall(r"stripHtml\([^)]+\)", template_content)
        # At least one call should reference article.content
        has_content_priority = any("article.content" in call for call in strip_html_calls)
        assert has_content_priority, (
            f"No stripHtml call references article.content. Found: {strip_html_calls}"
        )

    def test_striphtml_function_exists(self, template_content):
        """Verify stripHtml utility function is defined in the template.

        验证模板中定义了 stripHtml 工具函数。
        """
        assert "function stripHtml" in template_content

    def test_render_article_function_exists(self, template_content):
        """Verify renderArticle function is defined in the template.

        验证模板中定义了 renderArticle 函数。
        """
        assert "function renderArticle" in template_content
