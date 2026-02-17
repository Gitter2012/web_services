"""Tests for apps/report/api.py -- RBAC permission + ownership enforcement.

Report API permission and ownership tests.

Run with: pytest tests/apps/report/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestReportAuth:
    """Test report endpoints require authentication."""

    def test_list_reports_unauthenticated(self, client: TestClient):
        """GET /reports requires authentication."""
        response = client.get("/researchpulse/api/reports")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_report_unauthenticated(self, client: TestClient):
        """GET /reports/{id} requires authentication."""
        response = client.get("/researchpulse/api/reports/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_generate_weekly_unauthenticated(self, client: TestClient):
        """POST /reports/weekly requires authentication."""
        response = client.post("/researchpulse/api/reports/weekly")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_generate_monthly_unauthenticated(self, client: TestClient):
        """POST /reports/monthly requires authentication."""
        response = client.post("/researchpulse/api/reports/monthly")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_report_unauthenticated(self, client: TestClient):
        """DELETE /reports/{id} requires authentication."""
        response = client.delete("/researchpulse/api/reports/1")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestReportPermissions:
    """Test report endpoints enforce RBAC permissions.

    user role has report:read and report:generate.
    guest role does NOT have these permissions.
    """

    def test_list_reports_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /reports allowed for user (has report:read)."""
        response = client.get(
            "/researchpulse/api/reports",
            headers=auth_headers,
        )
        # user has report:read, so should not be 401/403
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_generate_weekly_allowed_for_regular_user(
        self, client: TestClient, auth_headers: dict
    ):
        """POST /reports/weekly allowed for user (has report:generate)."""
        response = client.post(
            "/researchpulse/api/reports/weekly",
            headers=auth_headers,
        )
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_reports_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """GET /reports forbidden for guest (no report:read)."""
        response = client.get(
            "/researchpulse/api/reports",
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_generate_weekly_forbidden_for_guest(
        self, client: TestClient, guest_headers: dict
    ):
        """POST /reports/weekly forbidden for guest (no report:generate)."""
        response = client.post(
            "/researchpulse/api/reports/weekly",
            headers=guest_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestReportOwnership:
    """Test report get/delete ownership checks.

    Only the report owner or superuser can view/delete a specific report.
    """

    def test_get_nonexistent_report_returns_404(
        self, client: TestClient, auth_headers: dict
    ):
        """GET /reports/{id} returns 404 for non-existent report."""
        response = client.get(
            "/researchpulse/api/reports/99999",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_nonexistent_report_returns_404(
        self, client: TestClient, auth_headers: dict
    ):
        """DELETE /reports/{id} returns 404 for non-existent report."""
        response = client.delete(
            "/researchpulse/api/reports/99999",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_superuser_can_access_any_report(
        self, client: TestClient, superuser_headers: dict
    ):
        """Superuser bypasses ownership check (returns 404 not 403)."""
        response = client.get(
            "/researchpulse/api/reports/99999",
            headers=superuser_headers,
        )
        # superuser should get 404 (not found), not 403 (forbidden)
        assert response.status_code == status.HTTP_404_NOT_FOUND
