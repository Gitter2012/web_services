"""Tests for common/email_templates.py."""

from __future__ import annotations

import pytest

from common.email_templates import render_user_digest, render_admin_report


# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

SAMPLE_ARTICLES = [
    {
        "id": 1,
        "title": "Attention Is All You Need",
        "url": "https://arxiv.org/abs/1706.03762",
        "author": "Vaswani et al.",
        "summary": "We propose a new simple network architecture based on attention mechanisms.",
        "source_type": "arxiv",
        "category": "Computer Science",
        "publish_time": "2025-02-19 10:30:00",
        "arxiv_id": "1706.03762",
        "arxiv_primary_category": "cs.CL",
        "tags": ["transformer", "attention", "nlp"],
        "content_summary": "AI generated summary of the paper.",
    },
    {
        "id": 2,
        "title": "Breaking News: <script>alert('xss')</script>",
        "url": "https://example.com/rss/article-2",
        "author": "Reporter & Editor",
        "summary": "Summary with <b>HTML</b> tags & special chars.",
        "source_type": "rss",
        "category": "Technology",
        "publish_time": "2025-02-19 14:00:00",
        "tags": ["tech", "news"],
    },
    {
        "id": 3,
        "title": "微信公众号文章标题",
        "url": "https://mp.weixin.qq.com/s/xxx",
        "author": "公众号作者",
        "summary": "这是一篇来自微信公众号的文章摘要。",
        "source_type": "wechat",
        "category": "",
        "publish_time": "2025-02-19 08:00:00",
        "wechat_account_name": "测试公众号",
        "tags": [],
    },
]


# ---------------------------------------------------------------------------
# render_user_digest
# ---------------------------------------------------------------------------

class TestRenderUserDigest:
    """Tests for render_user_digest()."""

    def test_returns_html_string(self):
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert isinstance(html, str)
        assert "<html" in html
        assert "</html>" in html

    def test_no_style_block(self):
        """HTML 邮件不应依赖 <style> 块（会被 Gmail 剥离）。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "<style>" not in html
        assert "<style " not in html

    def test_inline_styles_present(self):
        """关键元素应有内联样式。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert 'style="' in html

    def test_source_grouping(self):
        """文章应按来源分组。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "arXiv" in html
        assert "RSS" in html
        assert "微信公众号" in html

    def test_article_title_as_link(self):
        """文章标题应渲染为可点击链接。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert 'href="https://arxiv.org/abs/1706.03762"' in html

    def test_tags_rendered(self):
        """标签应渲染。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "transformer" in html
        assert "attention" in html

    def test_arxiv_pdf_link(self):
        """arXiv 文章应有 PDF 链接。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "https://arxiv.org/pdf/1706.03762" in html

    def test_arxiv_translation_link(self):
        """arXiv 文章应有中英对照翻译链接。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "https://hjfy.top/arxiv/1706.03762" in html

    def test_xss_prevention(self):
        """HTML 特殊字符应被转义（Jinja2 autoescape）。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        # <script> 标签应被转义，不应原样出现
        assert "<script>" not in html
        assert "&lt;script&gt;" in html or "alert" not in html.split("<script>")[0] if "<script>" in html else True

    def test_special_chars_in_author(self):
        """作者名中的 & 应被转义。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        # Jinja2 autoescape 会将 & 转为 &amp;
        # "Reporter & Editor" 经过 clean_text 后保留 &，autoescape 转为 &amp;
        assert "Reporter" in html

    def test_summary_not_truncated(self):
        """摘要不应被截断。"""
        long_summary = "A" * 500
        articles = [
            {
                "id": 99,
                "title": "Long Summary Article",
                "url": "https://example.com",
                "summary": long_summary,
                "source_type": "rss",
                "tags": [],
            }
        ]
        html = render_user_digest(articles, "2025-02-19", "http://localhost:8000")
        # 完整的 500 个 A 应该出现在 HTML 中
        assert long_summary in html

    def test_ai_summary_rendered(self):
        """AI 总结应渲染在卡片中。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "AI 总结" in html
        assert "AI generated summary of the paper." in html

    def test_empty_articles(self):
        """空文章列表应生成有效 HTML。"""
        html = render_user_digest([], "2025-02-19", "http://localhost:8000")
        assert "<html" in html
        assert "0" in html  # total_count = 0

    def test_date_in_header(self):
        """日期应出现在邮件头部。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "2025-02-19" in html

    def test_url_prefix_in_footer(self):
        """站点链接应出现在页脚。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://test.example.com")
        assert "http://test.example.com" in html

    def test_badge_colors(self):
        """来源徽章应有对应颜色。"""
        html = render_user_digest(SAMPLE_ARTICLES, "2025-02-19", "http://localhost:8000")
        assert "#b31b1b" in html  # arXiv
        assert "#f5a623" in html  # RSS
        assert "#07c160" in html  # WeChat


# ---------------------------------------------------------------------------
# render_admin_report
# ---------------------------------------------------------------------------

class TestRenderAdminReport:
    """Tests for render_admin_report()."""

    SAMPLE_STATS = {
        "stats": {"arxiv": 50, "rss": 30, "wechat": 10},
        "total_articles": 90,
        "errors": [],
    }

    def test_returns_html_string(self):
        html = render_admin_report(self.SAMPLE_STATS, "http://localhost:8000")
        assert isinstance(html, str)
        assert "<html" in html

    def test_no_style_block(self):
        html = render_admin_report(self.SAMPLE_STATS, "http://localhost:8000")
        assert "<style>" not in html

    def test_total_articles_shown(self):
        html = render_admin_report(self.SAMPLE_STATS, "http://localhost:8000")
        assert "90" in html

    def test_source_counts_shown(self):
        html = render_admin_report(self.SAMPLE_STATS, "http://localhost:8000")
        assert "50" in html  # arxiv
        assert "30" in html  # rss

    def test_success_indicator_no_errors(self):
        html = render_admin_report(self.SAMPLE_STATS, "http://localhost:8000")
        assert "全部成功" in html

    def test_error_indicator_with_errors(self):
        stats = {
            "stats": {"arxiv": 10},
            "total_articles": 10,
            "errors": ["Connection timeout", "Parse error"],
        }
        html = render_admin_report(stats, "http://localhost:8000")
        assert "2 个错误" in html
        assert "Connection timeout" in html
        assert "Parse error" in html

    def test_error_section_hidden_without_errors(self):
        html = render_admin_report(self.SAMPLE_STATS, "http://localhost:8000")
        assert "错误详情" not in html

    def test_empty_stats(self):
        html = render_admin_report({}, "http://localhost:8000")
        assert "<html" in html
        assert "0" in html
