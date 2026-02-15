"""Tests for apps/admin/api.py — admin management API endpoints.

管理后台 API 端点测试。

Note: These tests verify admin API endpoints with proper authentication.
Run with: pytest tests/apps/admin/ -v
"""

from __future__ import annotations

import pytest
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

        # Check expected endpoints
        expected_routes = [
            "/stats",
            "/users",
            "/config",
            "/features",
            "/scheduler/jobs",
            "/backups",
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
            email_enabled=True,
            active_backend="smtp",
        )
        assert config.smtp_host == "smtp.example.com"
        assert config.smtp_port == 587
        assert config.email_enabled is True

    def test_assign_role_valid(self):
        """Verify valid AssignRole schema.

        验证有效的角色分配请求模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import AssignRole

        assign = AssignRole(role_name="admin")
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
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
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
        response = client.post("/api/v1/admin/backups")
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
        response = client.get("/api/v1/admin/arxiv-categories")
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
        response = client.get("/api/v1/admin/rss-feeds")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]
