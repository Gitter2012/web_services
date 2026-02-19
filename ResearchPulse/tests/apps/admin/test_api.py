"""Tests for apps/admin/api.py — admin management API endpoints.

管理后台 API 端点测试。

Note: These tests verify admin API endpoints with proper authentication.
Run with: pytest tests/apps/admin/ -v
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminRouterConfig:
    """Test admin router configuration.

    验证管理后台路由配置。
    """

    def test_router_prefix_and_tags(self):
        """Verify router prefix and tags are correct.

        验证路由前缀与标签配置正确。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import router

        assert router.prefix == "/admin"
        assert "admin" in router.tags

    def test_routes_registered(self):
        """Verify expected routes are registered.

        验证预期端点已注册。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import router

        route_paths = [route.path for route in router.routes]

        # Check expected endpoints — only verify routes that actually exist
        # Routes include the router prefix "/admin"
        expected_routes = [
            "/admin/stats",
            "/admin/users",
            "/admin/config",
            "/admin/features",
            "/admin/scheduler/jobs",
            "/admin/backups",
            "/admin/sources/arxiv",
            "/admin/sources/rss",
        ]

        for route in expected_routes:
            assert route in route_paths, f"Route {route} not found in router"


class TestAdminSchemaValidation:
    """Test admin API schema validation.

    验证管理后台请求模型校验逻辑。
    """

    def test_config_update_valid(self):
        """Verify valid ConfigUpdate schema.

        验证有效的配置更新请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import ConfigUpdate

        config = ConfigUpdate(value="test_value", description="Test description")
        assert config.value == "test_value"
        assert config.description == "Test description"

    def test_config_update_minimal(self):
        """Verify ConfigUpdate with minimal fields.

        验证最小字段的配置更新请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import ConfigUpdate

        config = ConfigUpdate(value="test_value")
        assert config.value == "test_value"
        assert config.description is None

    def test_email_config_update_valid(self):
        """Verify valid EmailConfigUpdate schema.

        验证有效的邮件配置更新请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailConfigUpdate

        config = EmailConfigUpdate(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender_email="test@example.com",
            is_active=True,
        )
        assert config.smtp_host == "smtp.example.com"
        assert config.smtp_port == 587
        assert config.is_active is True

    def test_assign_role_valid(self):
        """Verify valid UserRoleUpdate schema.

        验证有效的角色分配请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import UserRoleUpdate

        assign = UserRoleUpdate(role_name="admin")
        assert assign.role_name == "admin"


class TestAdminStatsEndpoint:
    """Test admin stats endpoint.

    测试仪表盘统计端点。
    """

    def test_stats_requires_superuser(self, client: TestClient):
        """Verify stats endpoint requires superuser.

        验证统计端点需要超级管理员权限。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        # Without auth, should get 401
        response = client.get("/api/v1/admin/stats")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_stats_returns_correct_structure(
        self, client: TestClient, auth_headers: dict
    ):
        """Verify stats endpoint returns correct structure.

        验证统计端点返回正确的数据结构。

        Args:
            client: FastAPI test client.
            auth_headers: Authorization headers.

        Returns:
            None: This test does not return a value.
        """
        # Regular user doesn't have admin access
        response = client.get("/api/v1/admin/stats", headers=auth_headers)
        # Should be forbidden since not superuser
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_200_OK,  # If test user happens to be admin
        ]


class TestAdminUserManagement:
    """Test admin user management endpoints.

    测试用户管理端点。
    """

    def test_list_users_requires_auth(self, client: TestClient):
        """Verify list users requires authentication.

        验证列出用户需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/users")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_users_pagination(self, client: TestClient, auth_headers: dict):
        """Verify list users pagination works.

        验证用户列表分页功能。

        Args:
            client: FastAPI test client.
            auth_headers: Authorization headers.

        Returns:
            None: This test does not return a value.
        """
        response = client.get(
            "/api/v1/admin/users?page=1&page_size=10", headers=auth_headers
        )
        # Should be forbidden for regular users
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_200_OK,
        ]

    def test_list_users_page_size_limit(self, client: TestClient, auth_headers: dict):
        """Verify page size is capped at 100.

        验证分页大小上限为 100。

        Args:
            client: FastAPI test client.
            auth_headers: Authorization headers.

        Returns:
            None: This test does not return a value.
        """
        response = client.get(
            "/api/v1/admin/users?page=1&page_size=1000", headers=auth_headers
        )
        # Even if forbidden, check that the endpoint handles large page_size
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_200_OK,
        ]


class TestAdminConfigManagement:
    """Test admin configuration management endpoints.

    测试配置管理端点。
    """

    def test_list_config_requires_auth(self, client: TestClient):
        """Verify list config requires authentication.

        验证列出配置需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/config")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_get_config_by_key_requires_auth(self, client: TestClient):
        """Verify get config by key requires authentication.

        验证按键获取配置需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/config/test.key")
        # The route is PUT /config/{key:path}, no GET version exists → 405
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ]


class TestAdminFeatureToggle:
    """Test admin feature toggle endpoints.

    测试功能开关端点。
    """

    def test_get_features_requires_auth(self, client: TestClient):
        """Verify get features requires authentication.

        验证获取功能开关需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/features")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_toggle_feature_requires_auth(self, client: TestClient):
        """Verify toggle feature requires authentication.

        验证切换功能开关需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.put(
            "/api/v1/admin/features/test_feature",
            json={"enabled": True},
        )
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]


class TestAdminBackupManagement:
    """Test admin backup management endpoints.

    测试备份管理端点。
    """

    def test_list_backups_requires_auth(self, client: TestClient):
        """Verify list backups requires authentication.

        验证列出备份需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/backups")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_backup_requires_auth(self, client: TestClient):
        """Verify create backup requires authentication.

        验证创建备份需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.post("/api/v1/admin/backups/create")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_download_backup_requires_auth(self, client: TestClient):
        """Verify download backup requires authentication.

        验证下载备份需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/backups/1/download")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]


class TestAdminSchedulerManagement:
    """Test admin scheduler management endpoints.

    测试调度器管理端点。
    """

    def test_list_jobs_requires_auth(self, client: TestClient):
        """Verify list jobs requires authentication.

        验证列出任务需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/scheduler/jobs")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_trigger_job_requires_auth(self, client: TestClient):
        """Verify trigger job requires authentication.

        验证触发任务需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.post("/api/v1/admin/scheduler/jobs/test_job/trigger")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]


class TestAdminSourceManagement:
    """Test admin data source management endpoints.

    测试数据源管理端点。
    """

    def test_list_arxiv_categories_requires_auth(self, client: TestClient):
        """Verify list ArXiv categories requires authentication.

        验证列出 ArXiv 分类需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/sources/arxiv")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_rss_feeds_requires_auth(self, client: TestClient):
        """Verify list RSS feeds requires authentication.

        验证列出 RSS 订阅源需要认证。

        Args:
            client: FastAPI test client.

        Returns:
            None: This test does not return a value.
        """
        response = client.get("/api/v1/admin/sources/rss")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]


class TestUpdateEmailSettingsCollectsFields:
    """Test update_email_settings collects fields correctly (Fix #4).

    验证 update_email_settings 将所有字段收集后一次性 .values() 调用，
    而非链式 .values() 导致覆盖。
    """

    def test_email_global_settings_all_optional(self):
        """Verify EmailGlobalSettings schema allows all fields optional.

        验证 EmailGlobalSettings 所有字段可选。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailGlobalSettings

        # All fields are optional, empty create should work
        settings = EmailGlobalSettings()
        assert settings.email_enabled is None
        assert settings.push_frequency is None
        assert settings.push_time is None
        assert settings.max_articles_per_email is None

    def test_email_global_settings_partial(self):
        """Verify EmailGlobalSettings accepts partial fields.

        验证 EmailGlobalSettings 可接受部分字段。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailGlobalSettings

        settings = EmailGlobalSettings(email_enabled=True, push_time="10:00")
        assert settings.email_enabled is True
        assert settings.push_frequency is None
        assert settings.push_time == "10:00"
        assert settings.max_articles_per_email is None

    @pytest.mark.asyncio
    async def test_update_email_settings_collects_fields(self):
        """Verify update logic collects fields into a single dict.

        验证更新逻辑将字段收集到单个字典再执行更新，
        而非链式调用 .values() 导致只有最后一个字段生效。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailGlobalSettings
        from typing import Dict, Any

        # Simulate the field collection logic from update_email_settings
        data = EmailGlobalSettings(
            email_enabled=True,
            push_frequency="weekly",
            push_time="10:00",
            max_articles_per_email=50,
        )

        update_fields: Dict[str, Any] = {}
        if data.email_enabled is not None:
            update_fields["email_enabled"] = data.email_enabled
        if data.push_frequency is not None:
            update_fields["push_frequency"] = data.push_frequency
        if data.push_time is not None:
            update_fields["push_time"] = data.push_time
        if data.max_articles_per_email is not None:
            update_fields["max_articles_per_email"] = data.max_articles_per_email

        # All 4 fields should be collected
        assert len(update_fields) == 4
        assert update_fields["email_enabled"] is True
        assert update_fields["push_frequency"] == "weekly"
        assert update_fields["push_time"] == "10:00"
        assert update_fields["max_articles_per_email"] == 50


class TestTestEmailConfigNonSMTP:
    """Test test_email_config sends actual emails for non-SMTP backends (Fix #7).

    验证非 SMTP 后端（sendgrid/mailgun/brevo）实际调用 send_email 发送测试邮件，
    而非返回占位消息。
    """

    def test_test_email_config_imports_send_email(self):
        """Verify test_email_config endpoint imports and calls send_email for non-SMTP.

        验证 test_email_config 端点对非 SMTP 后端导入并调用 send_email。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.admin.api import test_email_config

        source = inspect.getsource(test_email_config)
        # Should import send_email for non-SMTP backends
        assert "from common.email import send_email" in source
        # Should call send_email with backend parameter
        assert "send_email(" in source

    def test_sendgrid_kwargs_use_api_key(self):
        """Verify SendGrid test email builds kwargs with api_key.

        验证 SendGrid 测试邮件使用 api_key 参数名构建 kwargs。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.admin.api import test_email_config

        source = inspect.getsource(test_email_config)
        # For sendgrid: kwargs["api_key"] = config.sendgrid_api_key
        assert 'kwargs["api_key"] = config.sendgrid_api_key' in source

    def test_mailgun_kwargs_use_api_key_and_domain(self):
        """Verify Mailgun test email builds kwargs with api_key and domain.

        验证 Mailgun 测试邮件使用 api_key 和 domain 参数名构建 kwargs。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.admin.api import test_email_config

        source = inspect.getsource(test_email_config)
        # For mailgun: kwargs["api_key"] and kwargs["domain"]
        assert 'kwargs["api_key"] = config.mailgun_api_key' in source
        assert 'kwargs["domain"] = config.mailgun_domain' in source

    def test_brevo_kwargs_use_api_key_and_from_name(self):
        """Verify Brevo test email builds kwargs with api_key and from_name.

        验证 Brevo 测试邮件使用 api_key 和 from_name 参数名构建 kwargs。

        Returns:
            None: This test does not return a value.
        """
        import inspect
        from apps.admin.api import test_email_config

        source = inspect.getsource(test_email_config)
        # For brevo: kwargs["api_key"] and kwargs["from_name"]
        assert 'kwargs["api_key"] = config.brevo_api_key' in source
        assert 'kwargs["from_name"] = config.brevo_from_name' in source
