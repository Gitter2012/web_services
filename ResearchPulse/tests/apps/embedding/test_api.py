"""Tests for apps/embedding/api.py — RBAC permission enforcement.

嵌入计算模块 API 端点权限测试。

Run with: pytest tests/apps/embedding/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestEmbeddingAuth:
    """Test embedding endpoints require authentication.

    验证嵌入计算端点需要认证。
    """

    def test_compute_unauthenticated(self, client: TestClient):
        """POST /compute requires authentication."""
        response = client.post(
            "/researchpulse/api/embedding/compute",
            json={"article_id": 1},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_batch_unauthenticated(self, client: TestClient):
        """POST /batch requires authentication."""
        response = client.post(
            "/researchpulse/api/embedding/batch",
            json={"article_ids": [1, 2]},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_stats_unauthenticated(self, client: TestClient):
        """GET /stats requires authentication."""
        response = client.get("/researchpulse/api/embedding/stats")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_rebuild_unauthenticated(self, client: TestClient):
        """POST /rebuild requires authentication (H2 fix).

        未认证访问 /rebuild 应返回 401（H2 修复验证）。
        """
        response = client.post("/researchpulse/api/embedding/rebuild")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestEmbeddingPermissions:
    """Test embedding endpoints enforce RBAC permissions.

    验证嵌入计算端点执行权限检查。
    user 角色缺少 embedding:compute 和 embedding:rebuild 权限。
    """

    def test_compute_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /compute forbidden without embedding:compute permission."""
        response = client.post(
            "/researchpulse/api/embedding/compute",
            json={"article_id": 1},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /batch forbidden without embedding:compute permission."""
        response = client.post(
            "/researchpulse/api/embedding/batch",
            json={"article_ids": [1, 2]},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_stats_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /stats forbidden without embedding:compute permission."""
        response = client.get(
            "/researchpulse/api/embedding/stats",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_rebuild_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /rebuild forbidden without embedding:rebuild permission (H2).

        user 角色缺少 embedding:rebuild 权限，高危操作应被拒绝。
        """
        response = client.post(
            "/researchpulse/api/embedding/rebuild",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestEmbeddingAdminAccess:
    """Test embedding endpoints with admin/superuser permissions.

    验证 admin/superuser 角色可访问嵌入计算端点。
    """

    def test_compute_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """POST /compute allowed for admin (has embedding:compute)."""
        response = client.post(
            "/researchpulse/api/embedding/compute",
            json={"article_id": 99999},
            headers=admin_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_rebuild_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """POST /rebuild allowed for admin (has embedding:rebuild).

        admin 角色拥有 embedding:rebuild 权限（H2 修复验证）。
        """
        response = client.post(
            "/researchpulse/api/embedding/rebuild",
            headers=admin_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_rebuild_allowed_for_superuser(
        self, client: TestClient, superuser_headers: dict
    ):
        """POST /rebuild allowed for superuser (all permissions bypass)."""
        response = client.post(
            "/researchpulse/api/embedding/rebuild",
            headers=superuser_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]
