"""Tests for apps/auth/schemas.py — request/response validation.

认证请求与响应模型校验测试。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestUserRegisterRequest:
    """Validate registration request schema.

    用户注册请求模型校验测试。
    """

    def test_valid_registration(self):
        """Verify valid registration payload passes.

        验证合法注册请求可通过校验。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import UserRegisterRequest

        req = UserRegisterRequest(
            username="testuser",
            email="test@example.com",
            password="password123",
            verification_token="test-token",
        )
        assert req.email == "test@example.com"

    def test_username_lowered(self):
        """Verify username is normalized to lowercase.

        验证用户名会被自动转为小写。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import UserRegisterRequest

        req = UserRegisterRequest(
            username="TestUser",
            email="test@example.com",
            password="password123",
            verification_token="test-token",
        )
        assert req.username == "testuser"

    def test_username_too_short(self):
        """Verify too-short usernames are rejected.

        验证过短用户名会触发校验错误。

        Raises:
            pydantic.ValidationError: When username is too short.
        """
        from apps.auth.schemas import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="ab",
                email="test@example.com",
                password="password123",
            )

    def test_username_too_long(self):
        """Verify too-long usernames are rejected.

        验证过长用户名会触发校验错误。

        Raises:
            pydantic.ValidationError: When username is too long.
        """
        from apps.auth.schemas import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="a" * 51,
                email="test@example.com",
                password="password123",
            )

    def test_username_no_special_chars(self):
        """Verify special characters in username are rejected.

        验证用户名包含特殊字符会触发校验错误。

        Raises:
            pydantic.ValidationError: When username contains invalid characters.
        """
        from apps.auth.schemas import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="test_user",
                email="test@example.com",
                password="password123",
            )

    def test_invalid_email(self):
        """Verify invalid email is rejected.

        验证无效邮箱格式会触发校验错误。

        Raises:
            pydantic.ValidationError: When email format is invalid.
        """
        from apps.auth.schemas import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="testuser",
                email="not-an-email",
                password="password123",
            )

    def test_password_too_short(self):
        """Verify too-short passwords are rejected.

        验证过短密码会触发校验错误。

        Raises:
            pydantic.ValidationError: When password is too short.
        """
        from apps.auth.schemas import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="12345",
            )

    def test_password_too_long(self):
        """Verify too-long passwords are rejected.

        验证过长密码会触发校验错误。

        Raises:
            pydantic.ValidationError: When password is too long.
        """
        from apps.auth.schemas import UserRegisterRequest

        with pytest.raises(ValidationError):
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="a" * 101,
            )


class TestUserLoginRequest:
    """Validate login request schema.

    用户登录请求模型校验测试。
    """

    def test_valid_login(self):
        """Verify valid login payload passes.

        验证合法登录请求可通过校验。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import UserLoginRequest

        req = UserLoginRequest(username="testuser", password="pass123")
        assert req.username == "testuser"

    def test_empty_username_rejected(self):
        """Verify empty username is rejected.

        验证空用户名会触发校验错误。

        Raises:
            pydantic.ValidationError: When username is empty.
        """
        from apps.auth.schemas import UserLoginRequest

        with pytest.raises(ValidationError):
            UserLoginRequest(username="", password="pass123")

    def test_empty_password_rejected(self):
        """Verify empty password is rejected.

        验证空密码会触发校验错误。

        Raises:
            pydantic.ValidationError: When password is empty.
        """
        from apps.auth.schemas import UserLoginRequest

        with pytest.raises(ValidationError):
            UserLoginRequest(username="testuser", password="")


class TestTokenResponse:
    """Validate token response schema.

    令牌响应模型校验测试。
    """

    def test_token_response_defaults(self):
        """Verify token response default fields.

        验证令牌响应模型默认值。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import TokenResponse

        resp = TokenResponse(
            access_token="acc",
            refresh_token="ref",
            expires_in=1800,
        )
        assert resp.token_type == "bearer"
        assert resp.expires_in == 1800


class TestRefreshTokenRequest:
    """Validate refresh token request.

    刷新令牌请求模型校验测试。
    """

    def test_valid_refresh(self):
        """Verify valid refresh token payload passes.

        验证合法刷新令牌请求可通过校验。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import RefreshTokenRequest

        req = RefreshTokenRequest(refresh_token="some.jwt.token")
        assert req.refresh_token == "some.jwt.token"

    def test_missing_refresh_token(self):
        """Verify missing refresh token is rejected.

        验证缺失刷新令牌会触发校验错误。

        Raises:
            pydantic.ValidationError: When refresh token is missing.
        """
        from apps.auth.schemas import RefreshTokenRequest

        with pytest.raises(ValidationError):
            RefreshTokenRequest()


class TestChangePasswordRequest:
    """Validate change-password request.

    修改密码请求模型校验测试。
    """

    def test_valid_change(self):
        """Verify valid change-password payload passes.

        验证合法修改密码请求可通过校验。

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.schemas import ChangePasswordRequest

        req = ChangePasswordRequest(
            current_password="old_pass",
            new_password="new_pass123",
        )
        assert req.current_password == "old_pass"
        assert req.new_password == "new_pass123"

    def test_new_password_too_short(self):
        """Verify too-short new password is rejected.

        验证过短的新密码会触发校验错误。

        Raises:
            pydantic.ValidationError: When new password is too short.
        """
        from apps.auth.schemas import ChangePasswordRequest

        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="old_pass",
                new_password="12345",
            )
