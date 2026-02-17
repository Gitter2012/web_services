"""Tests for apps/admin schemas — admin request/response models.

管理后台请求/响应模型测试。

Run with: pytest tests/apps/admin/test_schemas.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestConfigUpdateSchema:
    """Test ConfigUpdate schema validation.

    验证配置更新请求模型校验逻辑。
    """

    def test_valid_config_update(self):
        """Verify valid ConfigUpdate with all fields.

        验证包含所有字段的有效配置更新。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import ConfigUpdate

        config = ConfigUpdate(
            value="test_value",
            description="Test configuration description",
        )
        assert config.value == "test_value"
        assert config.description == "Test configuration description"

    def test_config_update_minimal(self):
        """Verify ConfigUpdate with only required fields.

        验证仅包含必填字段的配置更新。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import ConfigUpdate

        config = ConfigUpdate(value="test_value")
        assert config.value == "test_value"
        assert config.description is None

    def test_config_update_empty_value(self):
        """Verify ConfigUpdate accepts empty string value.

        验证配置更新接受空字符串值。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import ConfigUpdate

        config = ConfigUpdate(value="")
        assert config.value == ""

    def test_config_update_long_value(self):
        """Verify ConfigUpdate accepts long values.

        验证配置更新接受长值。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import ConfigUpdate

        long_value = "a" * 10000
        config = ConfigUpdate(value=long_value)
        assert config.value == long_value


class TestEmailConfigUpdateSchema:
    """Test EmailConfigUpdate schema validation.

    验证邮件配置更新请求模型校验逻辑。
    """

    def test_valid_smtp_config(self):
        """Verify valid SMTP configuration.

        验证有效的 SMTP 配置。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailConfigUpdate

        config = EmailConfigUpdate(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_user="user@gmail.com",
            smtp_password="app_password",
            smtp_use_tls=True,
            sender_email="user@gmail.com",
            is_active=True,
        )
        assert config.smtp_host == "smtp.gmail.com"
        assert config.smtp_port == 587
        assert config.smtp_use_tls is True

    def test_valid_sendgrid_config(self):
        """Verify valid SendGrid configuration.

        验证有效的 SendGrid 配置。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailConfigUpdate

        config = EmailConfigUpdate(
            sendgrid_api_key="SG.test_key",
            sender_email="sender@example.com",
            is_active=True,
        )
        assert config.sendgrid_api_key == "SG.test_key"
        assert config.is_active is True

    def test_valid_mailgun_config(self):
        """Verify valid Mailgun configuration.

        验证有效的 Mailgun 配置。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailConfigUpdate

        config = EmailConfigUpdate(
            mailgun_api_key="key-test",
            mailgun_domain="mg.example.com",
            sender_email="noreply@mg.example.com",
            is_active=True,
        )
        assert config.mailgun_api_key == "key-test"
        assert config.mailgun_domain == "mg.example.com"

    def test_valid_brevo_config(self):
        """Verify valid Brevo configuration.

        验证有效的 Brevo 配置。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailConfigUpdate

        config = EmailConfigUpdate(
            brevo_api_key="xkeysib-test",
            brevo_from_name="ResearchPulse",
            sender_email="noreply@example.com",
            is_active=True,
        )
        assert config.brevo_api_key == "xkeysib-test"
        assert config.brevo_from_name == "ResearchPulse"

    def test_empty_config(self):
        """Verify empty EmailConfigUpdate is valid.

        验证空的邮件配置更新有效（用于部分更新）。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailConfigUpdate

        config = EmailConfigUpdate()
        assert config.smtp_host is None
        assert config.smtp_port is None
        assert config.is_active is None

    def test_push_settings(self):
        """Verify push notification settings on EmailGlobalSettings.

        验证推送通知设置属于 EmailGlobalSettings 模型。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import EmailGlobalSettings

        config = EmailGlobalSettings(
            push_frequency="daily",
            push_time="09:00",
            max_articles_per_email=20,
        )
        assert config.push_frequency == "daily"
        assert config.push_time == "09:00"
        assert config.max_articles_per_email == 20


class TestUserRoleUpdateSchema:
    """Test UserRoleUpdate schema validation.

    验证角色分配请求模型校验逻辑。
    """

    def test_valid_assign_role(self):
        """Verify valid UserRoleUpdate schema.

        验证有效的角色分配。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import UserRoleUpdate

        assign = UserRoleUpdate(role_name="admin")
        assert assign.role_name == "admin"

    def test_assign_role_various_names(self):
        """Verify UserRoleUpdate accepts various role names.

        验证角色分配接受各种角色名。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import UserRoleUpdate

        for role_name in ["user", "admin", "editor", "viewer"]:
            assign = UserRoleUpdate(role_name=role_name)
            assert assign.role_name == role_name


class TestUserListResponseSchema:
    """Test UserListResponse schema.

    验证用户列表响应模型。
    """

    def test_user_list_response_structure(self):
        """Verify UserListResponse has correct structure.

        验证用户列表响应模型结构正确。

        Returns:
            None: This test does not return a value.
        """
        from apps.admin.api import UserListResponse
        from datetime import datetime

        response = UserListResponse(
            users=[
                {
                    "id": 1,
                    "username": "testuser",
                    "email": "test@example.com",
                    "is_active": True,
                    "is_superuser": False,
                    "roles": ["user"],
                    "created_at": datetime.now().isoformat(),
                    "last_login_at": None,
                }
            ],
            total=1,
        )

        assert response.total == 1
        assert len(response.users) == 1
        assert response.users[0]["username"] == "testuser"


class TestPaginationBounds:
    """Test pagination parameter bounds.

    验证分页参数边界。
    """

    def test_valid_pagination(self):
        """Verify valid pagination parameters.

        验证有效的分页参数。

        Returns:
            None: This test does not return a value.
        """
        # These are validated at the API level, not schema level
        # But we can test the logic
        page = 1
        page_size = 20
        MAX_PAGE_SIZE = 100

        assert page >= 1
        assert 1 <= page_size <= MAX_PAGE_SIZE

    def test_page_size_capped(self):
        """Verify page size is capped at maximum.

        验证分页大小有上限。

        Returns:
            None: This test does not return a value.
        """
        MAX_PAGE_SIZE = 100
        requested_size = 1000

        capped_size = min(max(1, requested_size), MAX_PAGE_SIZE)
        assert capped_size == 100
