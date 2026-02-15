"""Tests for core/dependencies.py — FastAPI dependency injection.

依赖注入相关测试。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient


class TestGetCurrentUserId:
    """Test get_current_user_id dependency.

    验证获取当前用户 ID 的依赖逻辑。
    """

    def test_no_credentials_returns_none(self):
        """Verify missing credentials return ``None``.

        验证未提供凭据时返回 ``None``。

        Returns:
            None: This test does not return a value.
        """
        from core.dependencies import get_current_user_id

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(user_id: int | None = Depends(get_current_user_id)):
            return {"user_id": user_id}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json()["user_id"] is None

    def test_invalid_token_returns_none(self):
        """Verify invalid token returns ``None``.

        验证无效令牌返回 ``None``。

        Returns:
            None: This test does not return a value.
        """
        from core.dependencies import get_current_user_id

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(user_id: int | None = Depends(get_current_user_id)):
            return {"user_id": user_id}

        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"Authorization": "Bearer invalid.token.here"}
        )

        assert response.status_code == 200
        assert response.json()["user_id"] is None

    def test_valid_token_returns_user_id(self):
        """Verify valid token returns user ID.

        验证有效令牌可解析出用户 ID。

        Returns:
            None: This test does not return a value.
        """
        from core.dependencies import get_current_user_id
        from core.security import create_access_token

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(user_id: int | None = Depends(get_current_user_id)):
            return {"user_id": user_id}

        token = create_access_token({"sub": "42"})
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == 42


class TestRequirePermissions:
    """Test require_permissions dependency factory.

    验证权限依赖工厂函数存在。
    """

    def test_require_permissions_exists(self):
        """Verify require_permissions is callable.

        验证 require_permissions 函数可调用。

        Returns:
            None: This test does not return a value.
        """
        from core.dependencies import require_permissions

        # Just verify the function exists and is callable
        assert callable(require_permissions)


class TestTypeAliases:
    """Test type aliases are properly defined.

    验证类型别名定义存在。
    """

    def test_type_aliases_exist(self):
        """Verify type aliases exist.

        验证依赖模块中的类型别名已定义。

        Returns:
            None: This test does not return a value.
        """
        from core.dependencies import (
            CurrentUser,
            CurrentActiveUser,
            Superuser,
            OptionalUserId,
        )

        # These are Annotated types, just verify they exist
        assert CurrentUser is not None
        assert CurrentActiveUser is not None
        assert Superuser is not None
        assert OptionalUserId is not None
