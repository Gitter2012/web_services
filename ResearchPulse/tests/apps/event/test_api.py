"""Tests for apps/event/api.py -- RBAC permission enforcement.

Event API permission tests. Previously public endpoints now require auth.

Run with: pytest tests/apps/event/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestEventAuth:
    """Test event endpoints require authentication (breaking change)."""

    def test_list_events_unauthenticated(self, client: TestClient):
        """GET /events requires authentication (was public)."""
        response = client.get("/researchpulse/api/events")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_event_unauthenticated(self, client: TestClient):
        """GET /events/{id} requires authentication (was public)."""
        response = client.get("/researchpulse/api/events/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cluster_unauthenticated(self, client: TestClient):
        """POST /events/cluster requires authentication."""
        response = client.post(
            "/researchpulse/api/events/cluster",
            json={"limit": 10},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_timeline_unauthenticated(self, client: TestClient):
        """GET /events/{id}/timeline requires authentication (was public)."""
        response = client.get("/researchpulse/api/events/1/timeline")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestEventPermissions:
    """Test event endpoints enforce RBAC permissions.

    user role has event:read but NOT event:cluster.
    """

    def test_list_events_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /events allowed for user (has event:read)."""
        response = client.get(
            "/researchpulse/api/events",
            headers=auth_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_get_event_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /events/{id} allowed for user (has event:read).

        Returns 404 (not 403) because auth passes.
        """
        response = client.get(
            "/researchpulse/api/events/99999",
            headers=auth_headers,
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_cluster_forbidden_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /events/cluster forbidden without event:cluster permission."""
        response = client.post(
            "/researchpulse/api/events/cluster",
            json={"limit": 10},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_events_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """GET /events forbidden for guest (no event:read)."""
        response = client.get(
            "/researchpulse/api/events",
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestEventAdminAccess:
    """Test event endpoints with admin permissions."""

    def test_cluster_allowed_for_admin(
        self, client: TestClient, admin_headers: dict
    ):
        """POST /events/cluster allowed for admin (has event:cluster)."""
        response = client.post(
            "/researchpulse/api/events/cluster",
            json={"limit": 10},
            headers=admin_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_cluster_allowed_for_superuser(
        self, client: TestClient, superuser_headers: dict
    ):
        """POST /events/cluster allowed for superuser."""
        response = client.post(
            "/researchpulse/api/events/cluster",
            json={"limit": 10},
            headers=superuser_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]
