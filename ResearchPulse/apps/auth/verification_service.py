# =============================================================================
# 邮箱验证服务模块
# =============================================================================
# 本模块提供用户注册前的邮箱验证功能，包括：
#   1. 发送验证码 - 生成6位数字验证码并通过邮件发送
#   2. 验证邮箱 - 校验用户输入的验证码
#   3. 频率限制 - 防止验证码滥发
#   4. 验证令牌 - 用于注册时的二次验证
#
# 设计决策：
#   - 使用 Redis 缓存存储验证码，支持 TTL 自动过期
#   - 6位数字验证码，有效期5分钟
#   - 发送频率限制：120秒内只能发送一次
#   - 验证成功后生成临时令牌，用于注册时验证
#   - 支持无 Redis 环境的降级处理
# =============================================================================

"""Email verification service for ResearchPulse user registration."""

from __future__ import annotations

import logging
import random
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache
from core.models.user import User

logger = logging.getLogger(__name__)


class VerificationService:
    """Service class for email verification operations.

    邮箱验证业务逻辑服务类，提供验证码发送、验证、频率限制等功能。

    Attributes:
        CODE_LENGTH: 验证码长度（6位）
        CODE_EXPIRY_SECONDS: 验证码有效期（300秒 = 5分钟）
        RATE_LIMIT_SECONDS: 发送频率限制（120秒）
        TOKEN_EXPIRY_SECONDS: 验证令牌有效期（600秒 = 10分钟）
        MAX_ATTEMPTS: 最大尝试次数（3次）
    """

    # 验证码配置
    CODE_LENGTH = 6
    CODE_EXPIRY_SECONDS = 300  # 5分钟
    RATE_LIMIT_SECONDS = 120   # 2分钟
    TOKEN_EXPIRY_SECONDS = 600  # 10分钟
    MAX_ATTEMPTS = 3  # 最大尝试次数

    # 缓存键前缀 - 注册验证
    CODE_KEY_PREFIX = "email_verification:code:"
    RATE_KEY_PREFIX = "email_verification:rate:"
    TOKEN_KEY_PREFIX = "email_verification:token:"
    ATTEMPTS_KEY_PREFIX = "email_verification:attempts:"

    # 缓存键前缀 - 密码重置验证
    RESET_CODE_KEY_PREFIX = "password_reset:code:"
    RESET_RATE_KEY_PREFIX = "password_reset:rate:"
    RESET_TOKEN_KEY_PREFIX = "password_reset:token:"
    RESET_ATTEMPTS_KEY_PREFIX = "password_reset:attempts:"

    @staticmethod
    def _generate_code() -> str:
        """Generate a random 6-digit numeric verification code.

        生成随机6位数字验证码。

        Returns:
            str: 6位数字字符串，如 "123456"
        """
        return f"{random.randint(0, 999999):06d}"

    @staticmethod
    def _generate_token() -> str:
        """Generate a cryptographically secure verification token.

        生成加密安全的验证令牌，用于注册时的二次验证。

        Returns:
            str: URL安全的随机令牌字符串
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def _get_code_key(email: str) -> str:
        """Get cache key for verification code.

        获取验证码的缓存键。
        """
        return f"{VerificationService.CODE_KEY_PREFIX}{email.lower()}"

    @staticmethod
    def _get_rate_key(email: str) -> str:
        """Get cache key for rate limiting.

        获取频率限制的缓存键。
        """
        return f"{VerificationService.RATE_KEY_PREFIX}{email.lower()}"

    @staticmethod
    def _get_token_key(email: str) -> str:
        """Get cache key for verification token.

        获取验证令牌的缓存键。
        """
        return f"{VerificationService.TOKEN_KEY_PREFIX}{email.lower()}"

    @staticmethod
    def _get_attempts_key(email: str) -> str:
        """Get cache key for attempt count.

        获取尝试次数的缓存键。
        """
        return f"{VerificationService.ATTEMPTS_KEY_PREFIX}{email.lower()}"

    @staticmethod
    async def send_verification_code(
        email: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Send verification code to the specified email.

        发送验证码到指定邮箱。

        流程：
        1. 检查发送频率限制
        2. 检查邮箱是否已注册
        3. 生成验证码
        4. 存储到缓存
        5. 发送邮件
        6. 返回结果

        Args:
            email: Target email address.
            session: Async database session.

        Returns:
            dict: Result containing:
                - success: bool - 是否成功
                - message: str - 结果消息
                - retry_after: int | None - 需要等待的秒数（频率限制时）
        """
        email = email.lower()

        # 1. 检查频率限制
        rate_key = VerificationService._get_rate_key(email)
        if cache.exists(rate_key):
            # 获取剩余等待时间
            remaining = cache.get(rate_key)
            retry_after = int(remaining) if remaining else VerificationService.RATE_LIMIT_SECONDS
            logger.warning(f"Rate limited for email: {email}, retry after {retry_after}s")
            return {
                "success": False,
                "message": f"请等待 {retry_after} 秒后再请求验证码",
                "retry_after": retry_after,
            }

        # 2. 检查邮箱是否已注册
        result = await session.execute(
            select(User).where(User.email == email)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            # 为了防止邮箱枚举，返回成功消息但实际不发送
            # 这样攻击者无法通过此接口判断邮箱是否已注册
            logger.info(f"Email already registered, silent reject: {email}")
            return {
                "success": True,
                "message": "如果该邮箱未注册，验证码将在几分钟内送达",
                "retry_after": None,
            }

        # 3. 生成验证码
        code = VerificationService._generate_code()

        # 4. 存储到缓存
        code_key = VerificationService._get_code_key(email)
        cache.set(code_key, code, ttl=VerificationService.CODE_EXPIRY_SECONDS)

        # 设置频率限制标记
        cache.set(rate_key, str(VerificationService.RATE_LIMIT_SECONDS), ttl=VerificationService.RATE_LIMIT_SECONDS)

        # 重置尝试次数
        attempts_key = VerificationService._get_attempts_key(email)
        cache.delete(attempts_key)

        # 5. 发送邮件（使用数据库配置）
        from apps.auth.email_templates import get_verification_email_content

        plain_text, html_body = get_verification_email_content(code)

        try:
            from common.email import send_email_with_priority

            sent, error_msg = await send_email_with_priority(
                to_addrs=[email],
                subject="ResearchPulse - 邮箱验证码",
                body=plain_text,
                session=session,
                html_body=html_body,
            )

            if sent:
                logger.info(f"Verification code sent to: {email}")
                return {
                    "success": True,
                    "message": "验证码已发送，请查收邮件",
                    "retry_after": None,
                }
            else:
                # 邮件发送失败，清理缓存
                cache.delete(code_key)
                cache.delete(rate_key)
                logger.error(f"Failed to send verification email to: {email}, error: {error_msg}")
                return {
                    "success": False,
                    "message": "邮件发送失败，请稍后重试",
                    "retry_after": None,
                }
        except Exception as e:
            # 发送异常，清理缓存
            cache.delete(code_key)
            cache.delete(rate_key)
            logger.error(f"Error sending verification email to {email}: {e}")
            return {
                "success": False,
                "message": "邮件发送失败，请稍后重试",
                "retry_after": None,
            }

    @staticmethod
    async def verify_email(email: str, code: str) -> dict[str, Any]:
        """Verify email with the provided code.

        使用验证码验证邮箱。

        流程：
        1. 验证码格式校验
        2. 检查尝试次数
        3. 从缓存获取存储的验证码
        4. 比对验证码
        5. 生成验证令牌
        6. 返回结果

        Args:
            email: Email address to verify.
            code: 6-digit verification code.

        Returns:
            dict: Result containing:
                - success: bool - 是否成功
                - message: str - 结果消息
                - verification_token: str | None - 验证令牌（成功时）
        """
        email = email.lower()

        # 1. 验证码格式校验
        if not code or len(code) != 6 or not code.isdigit():
            return {
                "success": False,
                "message": "验证码格式错误，请输入6位数字",
                "verification_token": None,
            }

        # 2. 检查尝试次数
        attempts_key = VerificationService._get_attempts_key(email)
        attempts = cache.get(attempts_key)
        if attempts and int(attempts) >= VerificationService.MAX_ATTEMPTS:
            logger.warning(f"Max attempts exceeded for email: {email}")
            return {
                "success": False,
                "message": f"验证码错误次数过多，请重新获取验证码",
                "verification_token": None,
            }

        # 3. 从缓存获取存储的验证码
        code_key = VerificationService._get_code_key(email)
        stored_code = cache.get(code_key)

        if not stored_code:
            logger.warning(f"No verification code found for email: {email}")
            return {
                "success": False,
                "message": "验证码已过期，请重新获取",
                "verification_token": None,
            }

        # 4. 比对验证码
        if stored_code != code:
            # 增加尝试次数
            current_attempts = int(attempts) + 1 if attempts else 1
            cache.set(attempts_key, str(current_attempts), ttl=VerificationService.CODE_EXPIRY_SECONDS)

            remaining = VerificationService.MAX_ATTEMPTS - current_attempts
            if remaining > 0:
                message = f"验证码错误，还剩 {remaining} 次尝试机会"
            else:
                message = "验证码错误次数过多，请重新获取验证码"

            logger.warning(f"Invalid verification code for email: {email}, attempts: {current_attempts}")
            return {
                "success": False,
                "message": message,
                "verification_token": None,
            }

        # 5. 验证成功，生成验证令牌
        token = VerificationService._generate_token()
        token_key = VerificationService._get_token_key(email)
        cache.set(token_key, token, ttl=VerificationService.TOKEN_EXPIRY_SECONDS)

        # 删除验证码和尝试次数
        cache.delete(code_key)
        cache.delete(attempts_key)

        logger.info(f"Email verified successfully: {email}")
        return {
            "success": True,
            "message": "邮箱验证成功",
            "verification_token": token,
        }

    @staticmethod
    def validate_verification_token(email: str, token: str) -> bool:
        """Validate verification token during registration.

        在注册时验证令牌的有效性。

        Args:
            email: Email address.
            token: Verification token from email verification step.

        Returns:
            bool: True if token is valid, False otherwise.
        """
        if not email or not token:
            return False

        email = email.lower()
        token_key = VerificationService._get_token_key(email)
        stored_token = cache.get(token_key)

        if not stored_token or stored_token != token:
            logger.warning(f"Invalid verification token for email: {email}")
            return False

        return True

    @staticmethod
    def cleanup_verification_data(email: str) -> None:
        """Clean up all verification data for an email.

        清理指定邮箱的所有验证数据。

        应在注册成功后调用，清理验证令牌等临时数据。

        Args:
            email: Email address to clean up.
        """
        email = email.lower()

        keys_to_delete = [
            VerificationService._get_code_key(email),
            VerificationService._get_rate_key(email),
            VerificationService._get_token_key(email),
            VerificationService._get_attempts_key(email),
        ]

        for key in keys_to_delete:
            cache.delete(key)

        logger.debug(f"Cleaned up verification data for: {email}")

    # =========================================================================
    # 密码重置相关方法
    # =========================================================================

    @staticmethod
    def _get_reset_code_key(email: str) -> str:
        """Get cache key for password reset verification code."""
        return f"{VerificationService.RESET_CODE_KEY_PREFIX}{email.lower()}"

    @staticmethod
    def _get_reset_rate_key(email: str) -> str:
        """Get cache key for password reset rate limiting."""
        return f"{VerificationService.RESET_RATE_KEY_PREFIX}{email.lower()}"

    @staticmethod
    def _get_reset_token_key(email: str) -> str:
        """Get cache key for password reset token."""
        return f"{VerificationService.RESET_TOKEN_KEY_PREFIX}{email.lower()}"

    @staticmethod
    def _get_reset_attempts_key(email: str) -> str:
        """Get cache key for password reset attempt count."""
        return f"{VerificationService.RESET_ATTEMPTS_KEY_PREFIX}{email.lower()}"

    @staticmethod
    async def send_password_reset_code(
        email: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Send password reset verification code to the specified email.

        发送密码重置验证码到指定邮箱。

        流程：
        1. 检查发送频率限制
        2. 检查邮箱是否已注册（必须已注册才能重置密码）
        3. 生成验证码
        4. 存储到缓存
        5. 发送邮件
        6. 返回结果

        Args:
            email: Target email address.
            session: Async database session.

        Returns:
            dict: Result containing:
                - success: bool - 是否成功
                - message: str - 结果消息
                - retry_after: int | None - 需要等待的秒数（频率限制时）
        """
        email = email.lower()

        # 1. 检查频率限制
        rate_key = VerificationService._get_reset_rate_key(email)
        if cache.exists(rate_key):
            remaining = cache.get(rate_key)
            retry_after = int(remaining) if remaining else VerificationService.RATE_LIMIT_SECONDS
            logger.warning(f"Password reset rate limited for email: {email}, retry after {retry_after}s")
            return {
                "success": False,
                "message": f"请等待 {retry_after} 秒后再请求验证码",
                "retry_after": retry_after,
            }

        # 2. 检查邮箱是否已注册
        result = await session.execute(
            select(User).where(User.email == email)
        )
        existing_user = result.scalar_one_or_none()
        if not existing_user:
            # 为了防止邮箱枚举，返回成功消息但实际不发送
            logger.info(f"Email not registered, silent reject for password reset: {email}")
            return {
                "success": True,
                "message": "如果该邮箱已注册，验证码将在几分钟内送达",
                "retry_after": None,
            }

        # 3. 生成验证码
        code = VerificationService._generate_code()

        # 4. 存储到缓存
        code_key = VerificationService._get_reset_code_key(email)
        cache.set(code_key, code, ttl=VerificationService.CODE_EXPIRY_SECONDS)

        # 设置频率限制标记
        cache.set(rate_key, str(VerificationService.RATE_LIMIT_SECONDS), ttl=VerificationService.RATE_LIMIT_SECONDS)

        # 重置尝试次数
        attempts_key = VerificationService._get_reset_attempts_key(email)
        cache.delete(attempts_key)

        # 5. 发送邮件（使用数据库配置）
        from apps.auth.email_templates import get_password_reset_email_content

        plain_text, html_body = get_password_reset_email_content(code)

        try:
            from common.email import send_email_with_priority

            sent, error_msg = await send_email_with_priority(
                to_addrs=[email],
                subject="ResearchPulse - 密码重置验证码",
                body=plain_text,
                session=session,
                html_body=html_body,
            )

            if sent:
                logger.info(f"Password reset code sent to: {email}")
                return {
                    "success": True,
                    "message": "验证码已发送，请查收邮件",
                    "retry_after": None,
                }
            else:
                # 邮件发送失败，清理缓存
                cache.delete(code_key)
                cache.delete(rate_key)
                logger.error(f"Failed to send password reset email to: {email}, error: {error_msg}")
                return {
                    "success": False,
                    "message": "邮件发送失败，请稍后重试",
                    "retry_after": None,
                }
        except Exception as e:
            # 发送异常，清理缓存
            cache.delete(code_key)
            cache.delete(rate_key)
            logger.error(f"Error sending password reset email to {email}: {e}")
            return {
                "success": False,
                "message": "邮件发送失败，请稍后重试",
                "retry_after": None,
            }

    @staticmethod
    async def verify_password_reset_code(email: str, code: str) -> dict[str, Any]:
        """Verify password reset code and return a reset token.

        验证密码重置验证码，成功后返回重置令牌。

        Args:
            email: Email address.
            code: 6-digit verification code.

        Returns:
            dict: Result containing:
                - success: bool - 是否成功
                - message: str - 结果消息
                - reset_token: str | None - 重置令牌（成功时）
        """
        email = email.lower()

        # 1. 验证码格式校验
        if not code or len(code) != 6 or not code.isdigit():
            return {
                "success": False,
                "message": "验证码格式错误，请输入6位数字",
                "reset_token": None,
            }

        # 2. 检查尝试次数
        attempts_key = VerificationService._get_reset_attempts_key(email)
        attempts = cache.get(attempts_key)
        if attempts and int(attempts) >= VerificationService.MAX_ATTEMPTS:
            logger.warning(f"Password reset max attempts exceeded for email: {email}")
            return {
                "success": False,
                "message": "验证码错误次数过多，请重新获取验证码",
                "reset_token": None,
            }

        # 3. 从缓存获取存储的验证码
        code_key = VerificationService._get_reset_code_key(email)
        stored_code = cache.get(code_key)

        if not stored_code:
            logger.warning(f"No password reset code found for email: {email}")
            return {
                "success": False,
                "message": "验证码已过期，请重新获取",
                "reset_token": None,
            }

        # 4. 比对验证码
        if stored_code != code:
            # 增加尝试次数
            current_attempts = int(attempts) + 1 if attempts else 1
            cache.set(attempts_key, str(current_attempts), ttl=VerificationService.CODE_EXPIRY_SECONDS)

            remaining = VerificationService.MAX_ATTEMPTS - current_attempts
            if remaining > 0:
                message = f"验证码错误，还剩 {remaining} 次尝试机会"
            else:
                message = "验证码错误次数过多，请重新获取验证码"

            logger.warning(f"Invalid password reset code for email: {email}, attempts: {current_attempts}")
            return {
                "success": False,
                "message": message,
                "reset_token": None,
            }

        # 5. 验证成功，生成重置令牌
        token = VerificationService._generate_token()
        token_key = VerificationService._get_reset_token_key(email)
        cache.set(token_key, token, ttl=VerificationService.TOKEN_EXPIRY_SECONDS)

        # 删除验证码和尝试次数
        cache.delete(code_key)
        cache.delete(attempts_key)

        logger.info(f"Password reset code verified successfully: {email}")
        return {
            "success": True,
            "message": "验证成功，请设置新密码",
            "reset_token": token,
        }

    @staticmethod
    def validate_reset_token(email: str, token: str) -> bool:
        """Validate password reset token.

        验证密码重置令牌的有效性。

        Args:
            email: Email address.
            token: Reset token from verification step.

        Returns:
            bool: True if token is valid, False otherwise.
        """
        if not email or not token:
            return False

        email = email.lower()
        token_key = VerificationService._get_reset_token_key(email)
        stored_token = cache.get(token_key)

        if not stored_token or stored_token != token:
            logger.warning(f"Invalid password reset token for email: {email}")
            return False

        return True

    @staticmethod
    def cleanup_reset_data(email: str) -> None:
        """Clean up all password reset data for an email.

        清理指定邮箱的所有密码重置数据。

        应在密码重置成功后调用。

        Args:
            email: Email address to clean up.
        """
        email = email.lower()

        keys_to_delete = [
            VerificationService._get_reset_code_key(email),
            VerificationService._get_reset_rate_key(email),
            VerificationService._get_reset_token_key(email),
            VerificationService._get_reset_attempts_key(email),
        ]

        for key in keys_to_delete:
            cache.delete(key)

        logger.debug(f"Cleaned up password reset data for: {email}")
