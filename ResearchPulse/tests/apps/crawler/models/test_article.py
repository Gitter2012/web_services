"""Tests for apps/crawler/models/article.py — Article and UserArticleState models.

文章与用户文章状态模型测试。
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


class TestArticleModel:
    """Test Article model functionality.

    验证 Article 模型字段与辅助方法。
    """

    def test_article_creation(self):
        """Verify Article instance creation.

        验证 Article 实例创建与字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="arxiv",
            source_id="cs.AI",
            external_id="2401.12345",
            title="Test Paper Title",
            url="https://arxiv.org/abs/2401.12345",
            author="John Doe, Jane Smith",
            summary="This is a test abstract.",
            is_archived=False,
            read_count=0,
            like_count=0,
        )

        assert article.source_type == "arxiv"
        assert article.source_id == "cs.AI"
        assert article.external_id == "2401.12345"
        assert article.title == "Test Paper Title"
        assert article.url == "https://arxiv.org/abs/2401.12345"
        assert article.author == "John Doe, Jane Smith"
        assert article.summary == "This is a test abstract."
        assert article.is_archived is False
        assert article.read_count == 0
        assert article.like_count == 0

    def test_article_with_minimal_fields(self):
        """Verify Article creation with minimal fields.

        验证仅填写必填字段时的 Article 创建。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="rss",
            source_id="test-feed",
            title="",
            url="",
            author="",
            summary="",
            is_archived=False,
        )

        assert article.source_type == "rss"
        assert article.source_id == "test-feed"
        assert article.title == ""
        assert article.is_archived is False

    def test_article_repr(self):
        """Verify Article ``__repr__`` output.

        验证 Article 的 ``__repr__`` 字符串内容。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="arxiv",
            source_id="cs.AI",
            title="A" * 50,  # Long title
        )

        repr_str = repr(article)
        assert "<Article(" in repr_str
        assert "id=" in repr_str
        assert "title=" in repr_str

    def test_article_arxiv_fields(self):
        """Verify arXiv-specific fields.

        验证 arXiv 相关字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="arxiv",
            source_id="cs.AI",
            arxiv_id="2401.12345",
            arxiv_primary_category="cs.AI",
            arxiv_comment="10 pages, 5 figures",
        )

        assert article.arxiv_id == "2401.12345"
        assert article.arxiv_primary_category == "cs.AI"
        assert article.arxiv_comment == "10 pages, 5 figures"

    def test_article_wechat_fields(self):
        """Verify WeChat-specific fields.

        验证微信来源相关字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="wechat",
            source_id="test-account",
            wechat_account_name="Test Account",
            wechat_digest="This is a digest",
        )

        assert article.wechat_account_name == "Test Account"
        assert article.wechat_digest == "This is a digest"

    def test_article_ai_processing_fields(self):
        """Verify AI processing result fields.

        验证 AI 处理结果字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="arxiv",
            source_id="cs.AI",
            ai_summary="AI generated summary",
            ai_category="AI",
            importance_score=8,
            one_liner="Important paper about LLMs",
            key_points=[{"type": "技术突破", "value": "New method", "impact": "高"}],
            impact_assessment={"short_term": "高", "long_term": "中", "certainty": "高"},
            actionable_items=[{"type": "跟进", "description": "Read paper", "priority": "高"}],
            ai_provider="ollama",
            ai_model="qwen3:32b",
            processing_method="ai",
        )

        assert article.ai_summary == "AI generated summary"
        assert article.ai_category == "AI"
        assert article.importance_score == 8
        assert article.one_liner == "Important paper about LLMs"
        assert len(article.key_points) == 1
        assert article.ai_provider == "ollama"

    def test_article_with_tags(self):
        """Verify tags field on Article.

        验证 Article 的标签字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        article = Article(
            source_type="arxiv",
            source_id="cs.AI",
            tags=["cs.AI", "cs.LG", "cs.CL"],
        )

        assert article.tags == ["cs.AI", "cs.LG", "cs.CL"]

    def test_article_with_timestamps(self):
        """Verify explicit timestamp fields.

        验证 Article 的时间字段设置。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import Article

        now = datetime.now(timezone.utc)
        article = Article(
            source_type="arxiv",
            source_id="cs.AI",
            crawl_time=now,
            publish_time=now,
        )

        assert article.crawl_time == now
        assert article.publish_time == now


class TestUserArticleStateModel:
    """Test UserArticleState model functionality.

    验证 UserArticleState 模型字段与方法。
    """

    def test_state_creation(self):
        """Verify UserArticleState instance creation.

        验证用户文章状态实例创建与字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import UserArticleState

        state = UserArticleState(
            user_id=1,
            article_id=42,
            is_read=False,
            is_starred=False,
        )

        assert state.user_id == 1
        assert state.article_id == 42
        assert state.is_read is False
        assert state.is_starred is False
        assert state.read_at is None
        assert state.starred_at is None

    def test_mark_read(self):
        """Verify ``mark_read`` behavior.

        验证 ``mark_read`` 会设置已读标记与时间。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import UserArticleState

        state = UserArticleState(user_id=1, article_id=1, is_read=False)
        state.mark_read()

        assert state.is_read is True
        assert state.read_at is not None
        assert isinstance(state.read_at, datetime)

    def test_toggle_star(self):
        """Verify ``toggle_star`` behavior.

        验证 ``toggle_star`` 切换收藏状态。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import UserArticleState

        state = UserArticleState(user_id=1, article_id=1, is_starred=False)

        # First toggle: star
        result = state.toggle_star()
        assert result is True
        assert state.is_starred is True
        assert state.starred_at is not None

        # Second toggle: unstar
        result = state.toggle_star()
        assert result is False
        assert state.is_starred is False
        assert state.starred_at is None

    def test_state_repr(self):
        """Verify UserArticleState ``__repr__`` output.

        验证 UserArticleState 的 ``__repr__`` 字符串内容。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import UserArticleState

        state = UserArticleState(user_id=1, article_id=42)
        repr_str = repr(state)

        assert "<UserArticleState(" in repr_str
        assert "user_id=1" in repr_str
        assert "article_id=42" in repr_str

    def test_state_with_read_status(self):
        """Verify read status fields.

        验证已读状态字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import UserArticleState

        now = datetime.now(timezone.utc)
        state = UserArticleState(
            user_id=1,
            article_id=42,
            is_read=True,
            read_at=now,
        )

        assert state.is_read is True
        assert state.read_at == now

    def test_state_with_starred_status(self):
        """Verify starred status fields.

        验证收藏状态字段赋值。

        Returns:
            None: This test does not return a value.
        """
        from apps.crawler.models.article import UserArticleState

        now = datetime.now(timezone.utc)
        state = UserArticleState(
            user_id=1,
            article_id=42,
            is_starred=True,
            starred_at=now,
        )

        assert state.is_starred is True
        assert state.starred_at == now
