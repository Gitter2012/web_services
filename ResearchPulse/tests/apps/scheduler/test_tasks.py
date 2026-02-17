"""Tests for apps/scheduler/tasks.py — scheduler management.

调度器管理测试。

Run with: pytest tests/apps/scheduler/ -v
"""

from __future__ import annotations

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _reset_scheduler():
    """Stop any running scheduler and reset the singleton."""
    import apps.scheduler.tasks as tasks_module
    if tasks_module._scheduler is not None:
        if tasks_module._scheduler.running:
            tasks_module._scheduler.shutdown()
        tasks_module._scheduler = None


class TestSchedulerSingleton:
    """Test scheduler singleton pattern.

    验证调度器单例模式。
    """

    def test_get_scheduler_returns_singleton(self):
        """Verify get_scheduler returns same instance.

        验证 get_scheduler 返回相同实例。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.tasks import get_scheduler, _scheduler
        import apps.scheduler.tasks as tasks_module

        # Reset the singleton for testing
        _reset_scheduler()

        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2

    def test_get_scheduler_creates_async_scheduler(self):
        """Verify scheduler is AsyncIOScheduler.

        验证调度器是 AsyncIOScheduler 类型。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.tasks import get_scheduler
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        import apps.scheduler.tasks as tasks_module

        # Reset the singleton for testing
        _reset_scheduler()

        scheduler = get_scheduler()
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_get_scheduler_uses_configured_timezone(self):
        """Verify scheduler uses configured timezone.

        验证调度器使用配置的时区。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.tasks import get_scheduler
        import apps.scheduler.tasks as tasks_module

        # Reset the singleton for testing
        _reset_scheduler()

        scheduler = get_scheduler()
        # Timezone should be set from settings
        assert scheduler.timezone is not None


class TestSchedulerLifecycle:
    """Test scheduler start and stop lifecycle.

    验证调度器启动和停止生命周期。
    """

    @pytest.mark.asyncio
    async def test_start_scheduler_registers_jobs(self):
        """Verify start_scheduler registers expected jobs.

        验证 start_scheduler 注册预期任务。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module

        # Reset singleton
        _reset_scheduler()

        # Mock the feature_config
        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = False  # Disable optional features
            mock_feature.get_int.return_value = 1
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()

        # Check that basic jobs are registered
        job_ids = [job.id for job in scheduler.get_jobs()]

        assert "crawl_job" in job_ids
        assert "cleanup_job" in job_ids
        assert "backup_job" in job_ids
        assert "dedup_job" in job_ids

        # notification_job should not be registered when feature.email_notification is False
        assert "notification_job" not in job_ids

        # Stop scheduler
        await tasks_module.stop_scheduler()

    @pytest.mark.asyncio
    async def test_start_scheduler_conditional_jobs_disabled(self):
        """Verify conditional jobs are not registered when features disabled.

        验证功能禁用时条件任务不注册。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module

        # Reset singleton
        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            # All optional features disabled
            mock_feature.get_bool.return_value = False
            mock_feature.get_int.return_value = 1
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()
        job_ids = [job.id for job in scheduler.get_jobs()]

        # Optional jobs should NOT be registered
        assert "ai_process_job" not in job_ids
        assert "embedding_job" not in job_ids
        assert "event_cluster_job" not in job_ids
        assert "topic_discovery_job" not in job_ids
        assert "notification_job" not in job_ids

        await tasks_module.stop_scheduler()

    @pytest.mark.asyncio
    async def test_start_scheduler_conditional_jobs_enabled(self):
        """Verify conditional jobs are registered when features enabled.

        验证功能启用时条件任务注册。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module

        # Reset singleton
        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            # All optional features enabled
            mock_feature.get_bool.return_value = True
            mock_feature.get_int.return_value = 1
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()
        job_ids = [job.id for job in scheduler.get_jobs()]

        # Optional jobs should be registered
        assert "ai_process_job" in job_ids
        assert "embedding_job" in job_ids
        assert "event_cluster_job" in job_ids
        assert "topic_discovery_job" in job_ids
        assert "notification_job" in job_ids

        await tasks_module.stop_scheduler()

    @pytest.mark.asyncio
    async def test_stop_scheduler_gracefully(self):
        """Verify stop_scheduler shuts down gracefully.

        验证 stop_scheduler 优雅关闭。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module

        # Reset singleton
        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = False
            mock_feature.get_int.return_value = 1
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()
        assert scheduler.running is True

        # stop_scheduler should shut down without error
        await tasks_module.stop_scheduler()
        # AsyncIOScheduler.shutdown() defers actual state change to the event
        # loop, so yield control briefly before checking the running flag.
        await asyncio.sleep(0.1)
        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_stop_scheduler_when_not_running(self):
        """Verify stop_scheduler handles not running case.

        验证 stop_scheduler 处理未运行情况。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module

        # Reset singleton
        _reset_scheduler()

        # Should not raise exception when scheduler not running
        await tasks_module.stop_scheduler()


class TestJobTriggers:
    """Test job trigger configurations.

    验证任务触发器配置。
    """

    @pytest.mark.asyncio
    async def test_crawl_job_interval_trigger(self):
        """Verify crawl job uses interval trigger.

        验证爬虫任务使用间隔触发器。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module
        from apscheduler.triggers.interval import IntervalTrigger

        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = False
            mock_feature.get_int.return_value = 6  # 6 hour interval
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()
        crawl_job = scheduler.get_job("crawl_job")

        assert crawl_job is not None
        assert isinstance(crawl_job.trigger, IntervalTrigger)

        await tasks_module.stop_scheduler()

    @pytest.mark.asyncio
    async def test_cleanup_job_cron_trigger(self):
        """Verify cleanup job uses cron trigger.

        验证清理任务使用 Cron 触发器。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module
        from apscheduler.triggers.cron import CronTrigger

        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = False
            mock_feature.get_int.return_value = 3  # 3 AM
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()
        cleanup_job = scheduler.get_job("cleanup_job")

        assert cleanup_job is not None
        assert isinstance(cleanup_job.trigger, CronTrigger)

        await tasks_module.stop_scheduler()

    @pytest.mark.asyncio
    async def test_notification_job_cron_trigger(self):
        """Verify notification job uses cron trigger when enabled.

        验证邮件通知任务启用时使用 Cron 触发器。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module
        from apscheduler.triggers.cron import CronTrigger

        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = True  # Enable all features
            mock_feature.get_int.return_value = 9
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()
        notification_job = scheduler.get_job("notification_job")

        assert notification_job is not None
        assert isinstance(notification_job.trigger, CronTrigger)

        await tasks_module.stop_scheduler()


class TestJobReplaceExisting:
    """Test job replace_existing behavior.

    验证任务替换行为。
    """

    @pytest.mark.asyncio
    async def test_jobs_replace_existing(self):
        """Verify jobs have replace_existing=True.

        验证任务设置了 replace_existing=True。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler import tasks as tasks_module

        # Clean up any previously running scheduler
        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = False
            mock_feature.get_int.return_value = 1
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        # Stop the scheduler, then start again to test replace_existing
        _reset_scheduler()

        with patch("common.feature_config.feature_config") as mock_feature:
            mock_feature.get_bool.return_value = False
            mock_feature.get_int.return_value = 1
            mock_feature.get.return_value = "mon"

            await tasks_module.start_scheduler()

        scheduler = tasks_module.get_scheduler()

        # Count jobs by ID - should only have one of each
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert job_ids.count("crawl_job") == 1
        assert job_ids.count("cleanup_job") == 1
        assert job_ids.count("backup_job") == 1

        await tasks_module.stop_scheduler()


class TestJobImports:
    """Test that job modules can be imported.

    验证任务模块可以正确导入。
    """

    def test_crawl_job_import(self):
        """Verify crawl_job module imports correctly.

        验证爬虫任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.crawl_job import run_crawl_job
        assert callable(run_crawl_job)

    def test_cleanup_job_import(self):
        """Verify cleanup_job module imports correctly.

        验证清理任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.cleanup_job import run_cleanup_job
        assert callable(run_cleanup_job)

    def test_backup_job_import(self):
        """Verify backup_job module imports correctly.

        验证备份任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.backup_job import run_backup_job
        assert callable(run_backup_job)

    def test_dedup_job_import(self):
        """Verify dedup_job module imports correctly.

        验证去重任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.dedup_job import run_dedup_job
        assert callable(run_dedup_job)

    def test_ai_process_job_import(self):
        """Verify ai_process_job module imports correctly.

        验证 AI 处理任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.ai_process_job import run_ai_process_job
        assert callable(run_ai_process_job)

    def test_embedding_job_import(self):
        """Verify embedding_job module imports correctly.

        验证嵌入任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.embedding_job import run_embedding_job
        assert callable(run_embedding_job)

    def test_event_cluster_job_import(self):
        """Verify event_cluster_job module imports correctly.

        验证事件聚类任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.event_cluster_job import run_event_cluster_job
        assert callable(run_event_cluster_job)

    def test_topic_discovery_job_import(self):
        """Verify topic_discovery_job module imports correctly.

        验证主题发现任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.topic_discovery_job import run_topic_discovery_job
        assert callable(run_topic_discovery_job)

    def test_notification_job_import(self):
        """Verify notification_job module imports correctly.

        验证通知任务模块可以正确导入。

        Returns:
            None: This test does not return a value.
        """
        from apps.scheduler.jobs.notification_job import (
            send_all_user_notifications,
            run_notification_job,
        )
        assert callable(send_all_user_notifications)
        assert callable(run_notification_job)
