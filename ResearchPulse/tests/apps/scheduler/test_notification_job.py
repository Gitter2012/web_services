"""Tests for apps/scheduler/jobs/notification_job.py — email notification fixes.

通知任务修复相关测试，覆盖修复 #5, #6, #8, #9, #10, #12, #14。

Run with: pytest tests/apps/scheduler/test_notification_job.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest


class TestNotificationEnableCheck:
    """Test dual notification enable check (Fix #5).

    验证通知功能同时检查 settings.email_enabled 和 feature_config。
    """

    @pytest.mark.asyncio
    async def test_both_disabled_returns_early(self):
        """Verify returns early when both settings and feature_config disable notifications.

        验证两个配置源都禁用时立即返回。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import send_all_user_notifications

        with patch("apps.scheduler.jobs.notification_job.settings") as mock_settings, \
             patch("common.feature_config.feature_config") as mock_feature:
            mock_settings.email_enabled = False
            mock_feature.get_bool.return_value = False

            result = await send_all_user_notifications()
            assert result["sent"] == 0
            assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_feature_enabled_but_settings_disabled_warns(self):
        """Verify warning when feature_config enables but settings disables.

        验证 feature_config 启用但 settings 禁用时返回警告。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import send_all_user_notifications

        with patch("apps.scheduler.jobs.notification_job.settings") as mock_settings, \
             patch("common.feature_config.feature_config") as mock_feature:
            mock_settings.email_enabled = False
            mock_feature.get_bool.return_value = True

            result = await send_all_user_notifications()
            # Should return without sending when settings.email_enabled is False
            assert result["sent"] == 0


class TestAdminEmailRecipient:
    """Test admin report uses correct recipient (Fix #6).

    验证管理员报告发送到 superuser_email 而非 email_from。
    """

    @pytest.mark.asyncio
    async def test_admin_report_sent_to_superuser_email(self):
        """Verify crawl report uses superuser_email when available.

        验证爬取报告优先使用 superuser_email。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import send_crawl_completion_notification

        with patch("apps.scheduler.jobs.notification_job.settings") as mock_settings, \
             patch("apps.scheduler.jobs.notification_job.send_email") as mock_send:
            mock_settings.email_enabled = True
            mock_settings.email_from = "noreply@example.com"
            mock_settings.superuser_email = "admin@example.com"
            mock_settings.email_backend = "smtp"
            mock_settings.email_template_engine = "jinja2"
            mock_settings.url_prefix = "http://localhost"
            mock_send.return_value = (True, "")

            await send_crawl_completion_notification({
                "stats": {"arxiv": 5},
                "total_articles": 5,
                "errors": [],
            })

            # Verify sent to superuser_email, not email_from
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["to_addrs"] == ["admin@example.com"]

    @pytest.mark.asyncio
    async def test_admin_report_fallback_to_email_from(self):
        """Verify crawl report falls back to email_from when superuser_email is empty.

        验证 superuser_email 为空时回退到 email_from。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import send_crawl_completion_notification

        with patch("apps.scheduler.jobs.notification_job.settings") as mock_settings, \
             patch("apps.scheduler.jobs.notification_job.send_email") as mock_send:
            mock_settings.email_enabled = True
            mock_settings.email_from = "noreply@example.com"
            mock_settings.superuser_email = ""
            mock_settings.email_backend = "smtp"
            mock_settings.email_template_engine = "jinja2"
            mock_settings.url_prefix = "http://localhost"
            mock_send.return_value = (True, "")

            await send_crawl_completion_notification({
                "stats": {},
                "total_articles": 0,
                "errors": [],
            })

            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["to_addrs"] == ["noreply@example.com"]


class TestSubscriptionMatching:
    """Test subscription matching resolves IDs to codes/names (Fix #8).

    验证订阅匹配将 ID 解析为实际的分类代码/公众号名称。
    """

    @pytest.mark.asyncio
    async def test_arxiv_matching_uses_category_codes(self):
        """Verify ArXiv matching resolves category IDs to codes.

        验证 ArXiv 匹配从 ID 解析为分类代码。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import get_user_subscribed_articles

        # Build a mock session
        mock_session = AsyncMock()

        # Create mock subscription
        mock_sub = MagicMock()
        mock_sub.source_type = "arxiv_category"
        mock_sub.source_id = 1  # ID, not code

        # Create mock ArXiv category
        mock_cat_row = (("cs.AI",),)

        # Create mock article matching the category code
        mock_article = MagicMock()
        mock_article.source_type = "arxiv"
        mock_article.arxiv_primary_category = "cs.AI"
        mock_article.source_id = "cs.AI"
        mock_article.is_archived = False
        mock_article.id = 1
        mock_article.title = "Test Article"
        mock_article.url = "https://arxiv.org/abs/1234"
        mock_article.author = "Author"
        mock_article.summary = "Summary"
        mock_article.category = "cs.AI"
        mock_article.publish_time = None
        mock_article.crawl_time = datetime.now(timezone.utc)
        mock_article.arxiv_id = "1234.5678"
        mock_article.arxiv_updated_time = None
        mock_article.wechat_account_name = None
        mock_article.tags = []

        # Mock get_session_factory to return our mock session
        mock_session_factory = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory.return_value = mock_ctx

        # Set up execute return values
        # First call: subscriptions query
        sub_result = MagicMock()
        sub_result.scalars.return_value.all.return_value = [mock_sub]

        # Second call: ArxivCategory.code lookup
        cat_result = MagicMock()
        cat_result.fetchall.return_value = [("cs.AI",)]

        # Third call: articles query
        art_result = MagicMock()
        art_result.scalars.return_value.all.return_value = [mock_article]

        mock_session.execute = AsyncMock(side_effect=[sub_result, cat_result, art_result])

        with patch("apps.scheduler.jobs.notification_job.get_session_factory", return_value=mock_session_factory):
            articles = await get_user_subscribed_articles(user_id=1)

        # Article should be matched because category code "cs.AI" matches
        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"


class TestIsActiveFilter:
    """Test is_active filter on subscription query (Fix #10).

    验证订阅查询包含 is_active == True 过滤条件。
    """

    def test_get_user_subscribed_articles_queries_active_subscriptions(self):
        """Verify get_user_subscribed_articles filters by is_active.

        验证 get_user_subscribed_articles 按 is_active 过滤。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.scheduler.jobs.notification_job import get_user_subscribed_articles

        source = inspect.getsource(get_user_subscribed_articles)
        # Verify the source code contains is_active filter
        assert "is_active == True" in source or "is_active==True" in source

    def test_send_all_user_notifications_queries_active_subscriptions(self):
        """Verify send_all_user_notifications filters by is_active.

        验证 send_all_user_notifications 按 is_active 过滤。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.scheduler.jobs.notification_job import send_all_user_notifications

        source = inspect.getsource(send_all_user_notifications)
        # Verify the source code contains is_active filter on subscription query
        assert "is_active == True" in source or "is_active==True" in source


class TestUserNotificationEmailSendPath:
    """Test send_user_notification_email uses correct send path (Fix #9).

    验证 send_user_notification_email 接受 session 参数并使用
    send_email_with_priority（有 session 时）或 send_email（无 session 时）。
    """

    @pytest.mark.asyncio
    async def test_with_session_uses_priority_send(self):
        """Verify send_user_notification_email uses send_email_with_priority when session provided.

        验证有 session 时使用 send_email_with_priority。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import send_user_notification_email

        mock_session = MagicMock()
        articles = [
            {"id": 1, "title": "Test", "url": "https://example.com",
             "source_type": "arxiv", "author": "Author", "summary": "Summary",
             "category": "cs.AI", "publish_time": None, "crawl_time": None,
             "arxiv_id": None, "arxiv_primary_category": None,
             "arxiv_updated_time": None, "wechat_account_name": None, "tags": []}
        ]

        with patch("apps.scheduler.jobs.notification_job.send_email_with_priority", new_callable=AsyncMock) as mock_priority, \
             patch("apps.scheduler.jobs.notification_job.send_email") as mock_send, \
             patch("apps.scheduler.jobs.notification_job.settings") as mock_settings:
            mock_priority.return_value = (True, "")
            mock_settings.url_prefix = "http://localhost"
            mock_settings.email_template_engine = "jinja2"

            result = await send_user_notification_email(
                user_email="user@example.com",
                user_id=1,
                articles=articles,
                session=mock_session,
            )

            assert result is True
            mock_priority.assert_called_once()
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_without_session_uses_plain_send(self):
        """Verify send_user_notification_email uses send_email when no session.

        验证无 session 时回退到 send_email。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import send_user_notification_email

        articles = [
            {"id": 1, "title": "Test", "url": "https://example.com",
             "source_type": "arxiv", "author": "Author", "summary": "Summary",
             "category": "cs.AI", "publish_time": None, "crawl_time": None,
             "arxiv_id": None, "arxiv_primary_category": None,
             "arxiv_updated_time": None, "wechat_account_name": None, "tags": []}
        ]

        with patch("apps.scheduler.jobs.notification_job.send_email_with_priority", new_callable=AsyncMock) as mock_priority, \
             patch("apps.scheduler.jobs.notification_job.send_email") as mock_send, \
             patch("apps.scheduler.jobs.notification_job.settings") as mock_settings:
            mock_send.return_value = (True, "")
            mock_settings.email_backend = "smtp"
            mock_settings.email_from = "sender@example.com"
            mock_settings.url_prefix = "http://localhost"
            mock_settings.email_template_engine = "jinja2"

            result = await send_user_notification_email(
                user_email="user@example.com",
                user_id=1,
                articles=articles,
                session=None,
            )

            assert result is True
            mock_send.assert_called_once()
            mock_priority.assert_not_called()


class TestPlaceholderURLReplaced:
    """Test hardcoded placeholder URL replaced with settings (Fix #12).

    验证邮件 HTML 中使用 settings.url_prefix 替代硬编码 URL。
    """

    def test_notification_email_uses_settings_url_prefix(self):
        """Verify email HTML contains settings.url_prefix, not hardcoded placeholder.

        验证源代码使用 settings.url_prefix 而非硬编码的 placeholder URL。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.scheduler.jobs.notification_job import send_user_notification_email

        source = inspect.getsource(send_user_notification_email)
        # Should use settings.url_prefix
        assert "settings.url_prefix" in source
        # Should NOT contain hardcoded placeholder URL
        assert "https://your-domain" not in source


class TestConcurrentNotificationSending:
    """Test concurrent notification sending with semaphore (Fix #14).

    验证通知邮件使用 asyncio.gather + Semaphore 并发发送。
    """

    def test_source_code_uses_semaphore_and_gather(self):
        """Verify send_all_user_notifications uses Semaphore + gather.

        验证源码使用 Semaphore 和 asyncio.gather 实现并发发送。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.scheduler.jobs.notification_job import send_all_user_notifications

        source = inspect.getsource(send_all_user_notifications)
        assert "Semaphore" in source
        assert "asyncio.gather" in source

    def test_semaphore_limits_concurrency(self):
        """Verify semaphore limits concurrent sends to 5.

        验证信号量限制并发数为 5。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.scheduler.jobs.notification_job import send_all_user_notifications

        source = inspect.getsource(send_all_user_notifications)
        # Should create semaphore with limit of 5
        assert "Semaphore(5)" in source


class TestRunNotificationJob:
    """Test the top-level run_notification_job entry point.

    验证 run_notification_job 定时任务入口函数。
    """

    @pytest.mark.asyncio
    async def test_run_notification_job_returns_summary(self):
        """Verify run_notification_job returns proper summary.

        验证 run_notification_job 返回正确的摘要信息。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import run_notification_job

        with patch("apps.scheduler.jobs.notification_job.send_all_user_notifications", new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = {
                "sent": 3,
                "failed": 1,
                "total": 5,
                "skipped": 1,
            }

            result = await run_notification_job()

            assert result["status"] == "completed"
            assert result["sent"] == 3
            assert result["failed"] == 1
            assert result["total_users"] == 5
            assert result["skipped"] == 1
            assert "duration_seconds" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_run_notification_job_handles_exception(self):
        """Verify run_notification_job handles exceptions gracefully.

        验证 run_notification_job 异常时返回失败状态。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import run_notification_job

        with patch("apps.scheduler.jobs.notification_job.send_all_user_notifications", new_callable=AsyncMock) as mock_notify:
            mock_notify.side_effect = RuntimeError("Database connection lost")

            result = await run_notification_job()

            assert result["status"] == "failed"
            assert "Database connection lost" in result["error"]


class TestTemplateEngineToggle:
    """Test EMAIL_TEMPLATE_ENGINE config toggle.

    验证邮件模板引擎配置切换。
    """

    @pytest.mark.asyncio
    async def test_jinja2_engine_uses_render_user_digest(self):
        """Verify Jinja2 engine calls render_user_digest.

        验证 jinja2 模式调用 render_user_digest。
        """
        from apps.scheduler.jobs.notification_job import send_user_notification_email

        articles = [
            {"id": 1, "title": "Test", "url": "https://example.com",
             "source_type": "rss", "author": "A", "summary": "S",
             "category": "", "publish_time": None, "crawl_time": None,
             "arxiv_id": None, "arxiv_primary_category": None,
             "arxiv_updated_time": None, "wechat_account_name": None, "tags": []}
        ]

        with patch("apps.scheduler.jobs.notification_job.send_email") as mock_send, \
             patch("apps.scheduler.jobs.notification_job.settings") as mock_settings, \
             patch("apps.scheduler.jobs.notification_job.render_user_digest") as mock_render:
            mock_settings.email_template_engine = "jinja2"
            mock_settings.url_prefix = "http://localhost"
            mock_settings.email_backend = "smtp"
            mock_settings.email_from = "sender@example.com"
            mock_send.return_value = (True, "")
            mock_render.return_value = "<html>jinja2 output</html>"

            await send_user_notification_email("u@x.com", 1, articles, session=None)

            mock_render.assert_called_once()
            # html_body should be from render_user_digest
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["html_body"] == "<html>jinja2 output</html>"

    @pytest.mark.asyncio
    async def test_legacy_engine_skips_render_user_digest(self):
        """Verify legacy engine does NOT call render_user_digest.

        验证 legacy 模式不调用 render_user_digest。
        """
        from apps.scheduler.jobs.notification_job import send_user_notification_email

        articles = [
            {"id": 1, "title": "Test", "url": "https://example.com",
             "source_type": "rss", "author": "A", "summary": "S",
             "category": "", "publish_time": None, "crawl_time": None,
             "arxiv_id": None, "arxiv_primary_category": None,
             "arxiv_updated_time": None, "wechat_account_name": None, "tags": []}
        ]

        with patch("apps.scheduler.jobs.notification_job.send_email") as mock_send, \
             patch("apps.scheduler.jobs.notification_job.settings") as mock_settings, \
             patch("apps.scheduler.jobs.notification_job.render_user_digest") as mock_render:
            mock_settings.email_template_engine = "legacy"
            mock_settings.url_prefix = "http://localhost"
            mock_settings.email_backend = "smtp"
            mock_settings.email_from = "sender@example.com"
            mock_send.return_value = (True, "")

            await send_user_notification_email("u@x.com", 1, articles, session=None)

            mock_render.assert_not_called()
            # html_body should contain <style> (legacy inline)
            call_kwargs = mock_send.call_args[1]
            assert "<style>" in call_kwargs["html_body"]
