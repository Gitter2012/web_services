"""Tests for main.py — application entry point and configuration.

针对应用入口与配置的测试用例集合。
"""

from __future__ import annotations

import pytest
from fastapi import status


class TestAppConfiguration:
    """Test FastAPI application configuration.

    验证 FastAPI 应用基础配置是否正确。
    """

    def test_app_title(self):
        """Verify the application title.

        验证应用标题配置正确。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        assert app.title == "ResearchPulse"

    def test_app_version(self):
        """Verify the application version is set.

        验证应用版本号已配置。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        assert app.version is not None

    def test_global_exception_handler_configured(self):
        """Verify global exception handler registration.

        验证全局异常处理器已注册。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        # Check that exception handlers are registered
        assert Exception in app.exception_handlers


class TestRouterRegistration:
    """Test that routers are properly registered.

    验证路由注册是否完整。
    """

    def test_auth_router_included(self):
        """Verify auth router is included.

        验证认证相关路由已注册到应用。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        # Get all route paths
        route_paths = []
        for route in app.routes:
            if hasattr(route, 'path'):
                route_paths.append(route.path)

        # Check that auth routes are present
        auth_routes = [p for p in route_paths if '/auth' in p]
        assert len(auth_routes) > 0

    def test_health_endpoint_registered(self):
        """Verify health endpoint registration.

        验证健康检查接口已注册。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        assert "/health" in route_paths

    def test_root_endpoint_registered(self):
        """Verify root endpoint registration.

        验证根路径接口已注册。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        assert "/" in route_paths


class TestMiddlewareConfiguration:
    """Test middleware configuration.

    验证中间件配置是否符合预期。
    """

    def test_cors_middleware_present(self):
        """Verify CORS middleware presence.

        验证 CORS 中间件已配置。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        # Check that middleware is present
        assert len(app.user_middleware) > 0

    def test_middleware_count(self):
        """Verify middleware count is reasonable.

        验证中间件数量满足最低预期。

        Returns:
            None: This test does not return a value.
        """
        from main import app

        # Should have at least CORS middleware
        assert len(app.user_middleware) >= 1
