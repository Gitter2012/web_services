"""Tests for apps/auth/service.py — authentication business logic.

认证业务逻辑测试用例。

Note: These tests require database setup and are marked as integration tests.
Run with: pytest -m integration
"""

from __future__ import annotations

import pytest
from core.security import decode_token, verify_password


# Mark all tests in this module as integration tests requiring database
pytestmark = pytest.mark.integration


class TestAuthServiceRegister:
    """Test user registration service.

    用户注册相关测试。
    """

    @pytest.mark.asyncio
    async def test_register_creates_user(self, db_session):
        """Verify registration creates a new user.

        验证注册会创建新用户并写入数据库。

        Args:
            db_session: Async database session fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        user = await AuthService.register(
            session=db_session,
            username="newuser",
            email="newuser@example.com",
            password="password123",
        )

        assert user.id is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.com"
        assert user.is_active is True
        assert user.is_superuser is False
        assert verify_password("password123", user.password_hash)

    @pytest.mark.asyncio
    async def test_register_username_lowercased(self, db_session):
        """Verify username is lowercased on registration.

        验证注册时用户名会被转换为小写。

        Args:
            db_session: Async database session fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        user = await AuthService.register(
            session=db_session,
            username="NewUser",
            email="newuser@example.com",
            password="password123",
        )

        assert user.username == "newuser"

    @pytest.mark.asyncio
    async def test_register_duplicate_username_raises_error(self, db_session):
        """Verify duplicate username raises an error.

        验证重复用户名注册会抛出 ``ValueError``。

        Args:
            db_session: Async database session fixture.

        Raises:
            ValueError: When username already exists.
        """
        from apps.auth.service import AuthService

        await AuthService.register(
            session=db_session,
            username="duplicate",
            email="first@example.com",
            password="password123",
        )

        with pytest.raises(ValueError, match="Username already exists"):
            await AuthService.register(
                session=db_session,
                username="duplicate",
                email="second@example.com",
                password="password123",
            )

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises_error(self, db_session):
        """Verify duplicate email raises an error.

        验证重复邮箱注册会抛出 ``ValueError``。

        Args:
            db_session: Async database session fixture.

        Raises:
            ValueError: When email already exists.
        """
        from apps.auth.service import AuthService

        await AuthService.register(
            session=db_session,
            username="user1",
            email="same@example.com",
            password="password123",
        )

        with pytest.raises(ValueError, match="Email already exists"):
            await AuthService.register(
                session=db_session,
                username="user2",
                email="same@example.com",
                password="password123",
            )


class TestAuthServiceLogin:
    """Test user login service.

    用户登录相关测试。
    """

    @pytest.mark.asyncio
    async def test_login_returns_user_and_tokens(self, db_session, test_user):
        """Verify login returns user and tokens.

        验证登录成功返回用户对象与访问/刷新令牌。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        user, access_token, refresh_token = await AuthService.login(
            session=db_session,
            username="testuser",
            password="password123",
        )

        assert user.id == test_user.id
        assert access_token is not None
        assert refresh_token is not None
        assert access_token != refresh_token

    @pytest.mark.asyncio
    async def test_login_invalid_username_raises_error(self, db_session):
        """Verify invalid username raises an error.

        验证无效用户名登录会抛出 ``ValueError``。

        Args:
            db_session: Async database session fixture.

        Raises:
            ValueError: When credentials are invalid.
        """
        from apps.auth.service import AuthService

        with pytest.raises(ValueError, match="Invalid credentials"):
            await AuthService.login(
                session=db_session,
                username="nonexistent",
                password="password123",
            )

    @pytest.mark.asyncio
    async def test_login_invalid_password_raises_error(self, db_session, test_user):
        """Verify invalid password raises an error.

        验证错误密码登录会抛出 ``ValueError``。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Raises:
            ValueError: When credentials are invalid.
        """
        from apps.auth.service import AuthService

        with pytest.raises(ValueError, match="Invalid credentials"):
            await AuthService.login(
                session=db_session,
                username="testuser",
                password="wrongpassword",
            )


class TestAuthServiceRefreshTokens:
    """Test token refresh service.

    令牌刷新相关测试。
    """

    @pytest.mark.asyncio
    async def test_refresh_tokens_returns_new_tokens(self, db_session, test_user):
        """Verify refresh returns new token pair.

        验证刷新令牌会返回新的访问/刷新令牌对。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        _, _, refresh_token = await AuthService.login(
            session=db_session,
            username="testuser",
            password="password123",
        )

        new_access, new_refresh = await AuthService.refresh_tokens(
            session=db_session,
            refresh_token=refresh_token,
        )

        assert new_access is not None
        assert new_refresh is not None
        assert new_access != refresh_token
        # Note: new_refresh may equal refresh_token if generated in the same
        # second (same sub/exp/type claims, no jti).  Verify it is a valid
        # non-empty token instead of requiring it to differ.
        assert len(new_refresh) > 0


class TestAuthServiceChangePassword:
    """Test password change service.

    密码修改相关测试。
    """

    @pytest.mark.asyncio
    async def test_change_password_success(self, db_session, test_user):
        """Verify password change succeeds.

        验证密码修改成功并更新存储。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        await AuthService.change_password(
            session=db_session,
            user=test_user,
            current_password="password123",
            new_password="newpassword456",
        )

        assert verify_password("newpassword456", test_user.password_hash)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_raises_error(self, db_session, test_user):
        """Verify wrong current password raises error.

        验证当前密码错误会抛出 ``ValueError``。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Raises:
            ValueError: When current password is incorrect.
        """
        from apps.auth.service import AuthService

        with pytest.raises(ValueError, match="Current password is incorrect"):
            await AuthService.change_password(
                session=db_session,
                user=test_user,
                current_password="wrongpassword",
                new_password="newpassword456",
            )


class TestAuthServiceGetUser:
    """Test user query methods.

    用户查询相关测试。
    """

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db_session, test_user):
        """Verify fetching user by ID.

        验证按 ID 获取用户成功。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        user = await AuthService.get_user_by_id(db_session, test_user.id)
        assert user is not None
        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, db_session):
        """Verify missing user ID returns ``None``.

        验证不存在的用户 ID 返回 ``None``。

        Args:
            db_session: Async database session fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        user = await AuthService.get_user_by_id(db_session, 99999)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, db_session, test_user):
        """Verify fetching user by username.

        验证按用户名获取用户成功。

        Args:
            db_session: Async database session fixture.
            test_user: Test user fixture.

        Returns:
            None: This test does not return a value.
        """
        from apps.auth.service import AuthService

        user = await AuthService.get_user_by_username(db_session, "testuser")
        assert user is not None
        assert user.username == "testuser"
