"""Tests for apps/ai_processor/api.py — RBAC permission enforcement.

AI 处理模块 API 端点权限测试。

Run with: pytest tests/apps/ai_processor/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestAIProcessorAuth:
    """Test AI processor endpoints require authentication.

    验证 AI 处理端点需要认证。
    """

    def test_process_unauthenticated(self, client: TestClient):
        """POST /process requires authentication.

        未认证访问 /process 应返回 401。
        """
        response = client.post(
            "/researchpulse/api/ai/process",
            json={"article_id": 1},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_batch_process_unauthenticated(self, client: TestClient):
        """POST /batch-process requires authentication.

        未认证访问 /batch-process 应返回 401。
        """
        response = client.post(
            "/researchpulse/api/ai/batch-process",
            json={"article_ids": [1, 2]},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_status_unauthenticated(self, client: TestClient):
        """GET /status/{article_id} requires authentication (H1 fix).

        未认证访问 /status 应返回 401（H1 修复验证）。
        """
        response = client.get("/researchpulse/api/ai/status/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_stats_unauthenticated(self, client: TestClient):
        """GET /token-stats requires authentication.

        未认证访问 /token-stats 应返回 401。
        """
        response = client.get("/researchpulse/api/ai/token-stats")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAIProcessorPermissions:
    """Test AI processor endpoints enforce require_permissions.

    验证 AI 处理端点执行 RBAC 权限检查。
    user 角色缺少 ai:process 和 ai:view_stats 权限。
    """

    def test_process_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /process forbidden without ai:process permission.

        user 角色缺少 ai:process 权限，应返回 403。
        """
        response = client.post(
            "/researchpulse/api/ai/process",
            json={"article_id": 1},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_process_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /batch-process forbidden without ai:process permission.

        user 角色缺少 ai:process 权限，应返回 403。
        """
        response = client.post(
            "/researchpulse/api/ai/batch-process",
            json={"article_ids": [1, 2]},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_token_stats_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /token-stats forbidden without ai:view_stats permission.

        user 角色缺少 ai:view_stats 权限，应返回 403。
        """
        response = client.get(
            "/researchpulse/api/ai/token-stats",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_status_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /status/{article_id} allowed for any authenticated user.

        /status 端点仅需认证（get_current_user），不需要特定权限。
        返回 404 表示权限通过但文章不存在，这是正确行为。
        """
        response = client.get(
            "/researchpulse/api/ai/status/99999",
            headers=auth_headers,
        )
        # 200 or 404 are both acceptable — means auth passed
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
        ]


class TestAIProcessorAdminAccess:
    """Test AI processor endpoints with admin permissions.

    验证 admin 角色可访问 AI 处理端点。
    """

    def test_process_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """POST /process allowed for admin (has ai:process).

        admin 角色拥有 ai:process 权限，应通过权限检查。
        返回非 401/403 表示权限通过。
        """
        response = client.post(
            "/researchpulse/api/ai/process",
            json={"article_id": 99999},
            headers=admin_headers,
        )
        # Not 401 or 403 — permission passed (may get 404/422/500 from business logic)
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_token_stats_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """GET /token-stats allowed for admin (has ai:view_stats).

        admin 角色拥有 ai:view_stats 权限，应通过权限检查。
        """
        response = client.get(
            "/researchpulse/api/ai/token-stats",
            headers=admin_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_process_allowed_for_superuser(
        self, client: TestClient, superuser_headers: dict
    ):
        """POST /process allowed for superuser (all permissions bypass).

        superuser 跳过所有权限检查。
        """
        response = client.post(
            "/researchpulse/api/ai/process",
            json={"article_id": 99999},
            headers=superuser_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]
