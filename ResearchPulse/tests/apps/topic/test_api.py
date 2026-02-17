"""Tests for apps/topic/api.py -- RBAC permission + ownership enforcement.

Topic API permission and ownership tests.

Run with: pytest tests/apps/topic/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestTopicAuth:
    """Test topic write endpoints require authentication."""

    def test_create_topic_unauthenticated(self, client: TestClient):
        """POST /topics requires authentication."""
        response = client.post(
            "/researchpulse/api/topics",
            json={"name": "Test Topic", "description": "desc"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_topic_unauthenticated(self, client: TestClient):
        """PUT /topics/{id} requires authentication."""
        response = client.put(
            "/researchpulse/api/topics/1",
            json={"name": "Updated"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_topic_unauthenticated(self, client: TestClient):
        """DELETE /topics/{id} requires authentication."""
        response = client.delete("/researchpulse/api/topics/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_discover_unauthenticated(self, client: TestClient):
        """POST /topics/discover requires authentication."""
        response = client.post("/researchpulse/api/topics/discover")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTopicPermissions:
    """Test topic endpoints enforce RBAC permissions.

    user role has topic:read but NOT topic:manage or topic:discover.
    """

    def test_create_topic_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /topics forbidden without topic:manage permission."""
        response = client.post(
            "/researchpulse/api/topics",
            json={"name": "Test", "description": "desc"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_topic_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """PUT /topics/{id} forbidden without topic:manage permission."""
        response = client.put(
            "/researchpulse/api/topics/1",
            json={"name": "Updated"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_topic_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """DELETE /topics/{id} forbidden without topic:manage permission."""
        response = client.delete(
            "/researchpulse/api/topics/1",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_discover_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /topics/discover forbidden without topic:discover permission."""
        response = client.post(
            "/researchpulse/api/topics/discover",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestTopicAdminAccess:
    """Test topic write endpoints with admin permissions."""

    def test_create_topic_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """POST /topics allowed for admin (has topic:manage)."""
        response = client.post(
            "/researchpulse/api/topics",
            json={"name": "Admin Topic", "description": "desc"},
            headers=admin_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_discover_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """POST /topics/discover allowed for admin (has topic:discover)."""
        response = client.post(
            "/researchpulse/api/topics/discover",
            headers=admin_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_topic_allowed_for_superuser(
        self, client: TestClient, superuser_headers: dict
    ):
        """POST /topics allowed for superuser (all permissions bypass)."""
        response = client.post(
            "/researchpulse/api/topics",
            json={"name": "SU Topic", "description": "desc"},
            headers=superuser_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]
