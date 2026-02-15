"""Tests for core/security.py — password hashing and JWT tokens.

安全工具（密码与 JWT）相关测试。
"""

from __future__ import annotations

from datetime import timedelta

import pytest


class TestPasswordHashing:
    """Verify bcrypt password hashing and verification.

    验证密码哈希与校验逻辑。
    """

    def test_hash_returns_string(self):
        """Verify hash output is a non-empty string.

        验证哈希输出为非空字符串。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password

        h = hash_password("my_password_123")
        assert isinstance(h, str)
        assert len(h) > 0

    def test_hash_is_bcrypt_format(self):
        """Verify hash string uses bcrypt format.

        验证哈希字符串使用 bcrypt 前缀格式。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password

        h = hash_password("test")
        # bcrypt hashes start with $2b$ (or $2a$)
        assert h.startswith("$2")

    def test_different_inputs_produce_different_hashes(self):
        """Verify different inputs yield different hashes.

        验证不同输入产生不同哈希。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password

        h1 = hash_password("password_a")
        h2 = hash_password("password_b")
        assert h1 != h2

    def test_same_input_different_salts(self):
        """Verify same input uses different salts.

        验证相同输入由于盐不同而产生不同哈希。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password

        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        # bcrypt uses random salt, so hashes should differ
        assert h1 != h2

    def test_verify_correct_password(self):
        """Verify correct password passes verification.

        验证正确密码可通过校验。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password, verify_password

        plain = "correct_horse_battery_staple"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        """Verify wrong password fails verification.

        验证错误密码无法通过校验。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password, verify_password

        hashed = hash_password("real_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_empty_password(self):
        """Verify empty password fails verification.

        验证空密码无法通过校验。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password, verify_password

        hashed = hash_password("notempty")
        assert verify_password("", hashed) is False

    def test_long_password_truncation(self):
        """Verify long password truncation behavior.

        验证 bcrypt 72 字节限制下的截断逻辑。

        Returns:
            None: This test does not return a value.
        """
        from core.security import hash_password, verify_password

        long_pw = "a" * 100
        hashed = hash_password(long_pw)
        # Should still verify successfully (both hash and verify truncate)
        assert verify_password(long_pw, hashed) is True


class TestJWTTokens:
    """Verify JWT access and refresh token creation/decoding.

    验证 JWT 访问/刷新令牌创建与解析。
    """

    def test_create_access_token(self):
        """Verify access token creation.

        验证访问令牌可以创建。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_access_token

        token = create_access_token({"sub": "testuser"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self):
        """Verify access token decoding.

        验证访问令牌解码结果包含必要字段。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_access_token, decode_token

        token = create_access_token({"sub": "testuser"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token(self):
        """Verify refresh token creation.

        验证刷新令牌可以创建。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_refresh_token

        token = create_refresh_token({"sub": "testuser"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_refresh_token(self):
        """Verify refresh token decoding.

        验证刷新令牌解码结果包含必要字段。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_refresh_token, decode_token

        token = create_refresh_token({"sub": "testuser"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_access_and_refresh_differ(self):
        """Verify access and refresh tokens differ.

        验证访问令牌与刷新令牌不同。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_access_token, create_refresh_token

        data = {"sub": "testuser"}
        access = create_access_token(data)
        refresh = create_refresh_token(data)
        assert access != refresh

    def test_custom_expiry(self):
        """Verify custom expiry is accepted.

        验证自定义过期时间参数可生效。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_access_token, decode_token

        token = create_access_token(
            {"sub": "testuser"}, expires_delta=timedelta(hours=2)
        )
        payload = decode_token(token)
        assert payload is not None

    def test_decode_invalid_token_returns_none(self):
        """Verify invalid token returns ``None``.

        验证无效令牌解码返回 ``None``。

        Returns:
            None: This test does not return a value.
        """
        from core.security import decode_token

        assert decode_token("not.a.valid.jwt") is None
        assert decode_token("") is None

    def test_decode_tampered_token_returns_none(self):
        """Verify tampered token returns ``None``.

        验证被篡改的令牌无法解码。

        Returns:
            None: This test does not return a value.
        """
        from core.security import create_access_token, decode_token

        token = create_access_token({"sub": "testuser"})
        # Flip a character in the signature part
        parts = token.rsplit(".", 1)
        tampered = parts[0] + ".TAMPERED"
        assert decode_token(tampered) is None

    def test_get_token_expiry(self):
        """Verify token expiry extraction.

        验证可从令牌中提取过期时间。

        Returns:
            None: This test does not return a value.
        """
        from datetime import datetime, timezone

        from core.security import create_access_token, get_token_expiry

        token = create_access_token({"sub": "testuser"})
        expiry = get_token_expiry(token)
        assert expiry is not None
        assert isinstance(expiry, datetime)
        # Expiry should be in the future
        assert expiry > datetime.now(timezone.utc)

    def test_get_token_expiry_invalid(self):
        """Verify invalid token expiry returns ``None``.

        验证无效令牌过期时间返回 ``None``。

        Returns:
            None: This test does not return a value.
        """
        from core.security import get_token_expiry

        assert get_token_expiry("invalid") is None
