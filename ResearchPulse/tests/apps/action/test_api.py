"""Tests for apps/action/api.py -- RBAC permission enforcement.

Action items API permission tests.

Run with: pytest tests/apps/action/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestActionAuth:
    """Test action item endpoints require authentication."""

    def test_list_actions_unauthenticated(self, client: TestClient):
        """GET /actions requires authentication."""
        response = client.get("/researchpulse/api/actions")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_action_unauthenticated(self, client: TestClient):
        """POST /actions requires authentication."""
        response = client.post(
            "/researchpulse/api/actions",
            json={
                "article_id": 1,
                "type": "read",
                "description": "Test action",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_action_unauthenticated(self, client: TestClient):
        """GET /actions/{id} requires authentication."""
        response = client.get("/researchpulse/api/actions/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_action_unauthenticated(self, client: TestClient):
        """PUT /actions/{id} requires authentication."""
        response = client.put(
            "/researchpulse/api/actions/1",
            json={"description": "Updated"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_complete_action_unauthenticated(self, client: TestClient):
        """POST /actions/{id}/complete requires authentication."""
        response = client.post("/researchpulse/api/actions/1/complete")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_dismiss_action_unauthenticated(self, client: TestClient):
        """POST /actions/{id}/dismiss requires authentication."""
        response = client.post("/researchpulse/api/actions/1/dismiss")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestActionPermissions:
    """Test action item endpoints enforce RBAC permissions.

    user role has action:read and action:manage.
    guest role does NOT have these permissions.
    """

    def test_list_actions_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /actions allowed for user (has action:read)."""
        response = client.get(
            "/researchpulse/api/actions",
            headers=auth_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_action_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /actions allowed for user (has action:manage)."""
        response = client.post(
            "/researchpulse/api/actions",
            json={
                "article_id": 99999,
                "type": "read",
                "description": "Test",
            },
            headers=auth_headers,
        )
        # Not 401/403 means permission passed
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_actions_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """GET /actions forbidden for guest (no action:read)."""
        response = client.get(
            "/researchpulse/api/actions",
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_action_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """POST /actions forbidden for guest (no action:manage)."""
        response = client.post(
            "/researchpulse/api/actions",
            json={
                "article_id": 1,
                "type": "read",
                "description": "Test",
            },
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_complete_action_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """POST /actions/{id}/complete forbidden for guest."""
        response = client.post(
            "/researchpulse/api/actions/1/complete",
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_dismiss_action_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """POST /actions/{id}/dismiss forbidden for guest."""
        response = client.post(
            "/researchpulse/api/actions/1/dismiss",
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
