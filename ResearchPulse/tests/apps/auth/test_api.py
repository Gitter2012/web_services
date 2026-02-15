"""Tests for apps/auth/api.py — authentication API endpoints.

认证 API 端点与数据模型测试。

Note: These tests are functional tests that verify API endpoints.
Run with: pytest tests/apps/auth/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status


class TestAuthSchemasValidation:
    """Test schema validation at API level (without database).

    验证认证相关请求模型的校验逻辑。
    """

    def test_register_invalid_email_format(self):
        """Verify invalid email format is rejected.

        验证无效邮箱格式会触发校验错误。

        Raises:
            pydantic.ValidationError: When email format is invalid.
        """
        from apps.auth.schemas import UserRegisterRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="testuser",
                email="not-an-email",
                password="password123",
            )

    def test_register_short_username(self):
        """Verify short username is rejected.

        验证过短用户名会触发校验错误。

        Raises:
            pydantic.ValidationError: When username is too short.
        """
        from apps.auth.schemas import UserRegisterRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="ab",  # Too short
                email="test@example.com",
                password="password123",
            )

    def test_register_short_password(self):
        """Verify short password is rejected.

        验证过短密码会触发校验错误。

        Raises:
            pydantic.ValidationError: When password is too short.
        """
        from apps.auth.schemas import UserRegisterRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="12345",  # Too short
            )

    def test_login_empty_username(self):
        """Verify empty username is rejected.

        验证空用户名会触发校验错误。

        Raises:
            pydantic.ValidationError: When username is empty.
        """
        from apps.auth.schemas import UserLoginRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserLoginRequest(username="", password="password123")

    def test_login_empty_password(self):
        """Verify empty password is rejected.

        验证空密码会触发校验错误。

        Raises:
            pydantic.ValidationError: When password is empty.
        """
        from apps.auth.schemas import UserLoginRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserLoginRequest(username="testuser", password="")


class TestAuthAPIRoutes:
    """Test that auth API routes are properly registered.

    验证认证 API 路由注册情况。
    """

    def test_auth_router_exists(self):
        """Verify auth router configuration.

        验证认证路由前缀与标签配置正确。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.api import router

        # Check that router has expected prefix and tags
        assert router.prefix == "/auth"
        assert "authentication" in router.tags

    def test_auth_routes_registered(self):
        """Verify auth routes are registered.

        验证认证相关端点已注册。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.api import router

        # Get all route paths
        route_paths = [route.path for route in router.routes]

        # Check expected endpoints (paths include the router prefix)
        # Routes are stored without the router prefix
        assert "/register" in route_paths or "/auth/register" in route_paths
        assert "/login" in route_paths or "/auth/login" in route_paths
        assert "/refresh" in route_paths or "/auth/refresh" in route_paths
        assert "/me" in route_paths or "/auth/me" in route_paths


class TestAuthAPIResponses:
    """Test auth API response models.

    验证认证响应模型行为。
    """

    def test_token_response_model(self):
        """Verify ``TokenResponse`` model.

        验证令牌响应模型字段与默认值。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import TokenResponse

        resp = TokenResponse(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=1800,
        )

        assert resp.access_token == "test_access_token"
        assert resp.refresh_token == "test_refresh_token"
        assert resp.expires_in == 1800
        assert resp.token_type == "bearer"

    def test_user_response_model(self):
        """Verify ``UserResponse`` model.

        验证用户响应模型字段映射。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import UserResponse
        from datetime import datetime

        now = datetime.now()
        resp = UserResponse(
            id=1,
            username="testuser",
            email="test@example.com",
            is_active=True,
            is_superuser=False,
            roles=["user"],
            created_at=now,
            last_login_at=None,
        )

        assert resp.id == 1
        assert resp.username == "testuser"
        assert resp.is_active is True
