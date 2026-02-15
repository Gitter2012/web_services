# =============================================================================
# 安全工具模块
# =============================================================================
# 本模块提供 ResearchPulse 项目的核心安全功能，包括：
#   1. 密码哈希与验证（基于 bcrypt 算法）
#   2. JWT（JSON Web Token）访问令牌和刷新令牌的创建与解析
#
# 架构角色：
#   - 作为核心安全层，被认证依赖（dependencies.py）和用户模型（user.py）调用
#   - 密码相关函数被 User 模型的 set_password / check_password 方法使用
#   - JWT 相关函数被认证中间件和登录接口使用
#
# 设计决策：
#   - 使用 bcrypt 算法进行密码哈希，它是业界推荐的密码哈希算法，
#     内置盐值（salt）和可配置的计算轮次（rounds），可抵御彩虹表和暴力破解攻击
#   - JWT 令牌分为 access token（短期）和 refresh token（长期）两种类型，
#     通过 payload 中的 "type" 字段区分，实现令牌刷新机制
#   - 延迟导入 settings，避免模块间循环依赖
# =============================================================================

"""Security utilities for ResearchPulse v2.

Provides password hashing and JWT token management.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

# 密码哈希上下文配置
# schemes=["bcrypt"]：指定使用 bcrypt 算法
# deprecated="auto"：自动标记过时的哈希方案
# bcrypt__rounds=12：bcrypt 计算轮次为 12（2^12 = 4096 次迭代），
#   值越大越安全但越慢，12 是安全性与性能之间的良好平衡点
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    The password is truncated to 72 bytes to match bcrypt's input limit,
    ensuring deterministic behavior across different callers.

    Args:
        password: Plaintext password to hash.

    Returns:
        str: Bcrypt hash string including salt.

    Example:
        >>> hashed = hash_password("MySecret123")
        >>> hashed.startswith("$2")
        True
    """
    import bcrypt
    # bcrypt 算法有 72 字节的输入限制，超出部分会被截断
    # 这里显式截断到 72 字节，确保行为一致且可预测
    password_bytes = password.encode('utf-8')[:72]
    # 生成随机盐值，每次哈希都使用不同的盐，即使相同密码也会产生不同的哈希值
    salt = bcrypt.gensalt()
    # 使用盐值对密码进行哈希，返回字符串形式的哈希结果
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Uses constant-time comparison via ``bcrypt.checkpw``. The plaintext
    password is truncated to 72 bytes to align with bcrypt behavior.

    Args:
        plain_password: Password provided by the user.
        hashed_password: Stored bcrypt hash.

    Returns:
        bool: ``True`` if the password matches the hash, otherwise ``False``.
    """
    import bcrypt
    # 与 hash_password 保持一致的截断逻辑
    # bcrypt has a 72 byte limit, truncate if necessary
    password_bytes = plain_password.encode('utf-8')[:72]
    # bcrypt.checkpw 会从哈希值中提取盐值，然后重新计算哈希进行比较
    # 使用恒定时间比较（constant-time comparison），防止时序攻击
    return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Adds the ``exp`` claim and a ``type=access`` marker to the payload.

    Args:
        data: Payload data to embed in the token.
        expires_delta: Optional override for token lifetime.

    Returns:
        str: Encoded JWT access token.

    Raises:
        jose.JWTError: If encoding fails due to invalid configuration.
    """
    # 延迟导入 settings，避免循环依赖
    from settings import settings

    # 复制输入数据，避免修改调用方的原始字典
    to_encode = data.copy()
    # 计算令牌过期时间
    if expires_delta:
        # 如果调用方指定了过期时间间隔，则使用指定值
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # 否则使用配置文件中的默认过期时间（分钟）
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
    # 在 payload 中添加过期时间和令牌类型标识
    # "type": "access" 用于区分访问令牌和刷新令牌，防止令牌误用
    to_encode.update({"exp": expire, "type": "access"})
    # 使用密钥和指定算法对 payload 进行签名编码
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT refresh token.

    Adds the ``exp`` claim and a ``type=refresh`` marker to the payload.

    Args:
        data: Payload data to embed in the token.
        expires_delta: Optional override for token lifetime.

    Returns:
        str: Encoded JWT refresh token.

    Raises:
        jose.JWTError: If encoding fails due to invalid configuration.
    """
    # 延迟导入 settings，避免循环依赖
    from settings import settings

    # 复制输入数据，避免修改调用方的原始字典
    to_encode = data.copy()
    # 计算令牌过期时间
    if expires_delta:
        # 如果调用方指定了过期时间间隔，则使用指定值
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # 否则使用配置文件中的默认刷新令牌过期时间（天）
        # 刷新令牌的有效期通常远长于访问令牌
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
    # "type": "refresh" 标识这是刷新令牌
    # 在验证时会检查此字段，确保刷新令牌不能用作访问令牌
    to_encode.update({"exp": expire, "type": "refresh"})
    # 使用与访问令牌相同的密钥和算法进行签名
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT token.

    Validates signature, algorithm, and expiration. Returns ``None`` on any
    JWT error instead of raising.

    Args:
        token: Encoded JWT string.

    Returns:
        dict[str, Any] | None: Decoded payload if valid, otherwise ``None``.
    """
    # 延迟导入 settings，避免循环依赖
    from settings import settings

    try:
        # 解码并验证 JWT 令牌
        # 此操作会自动验证签名的有效性和令牌是否过期（通过 "exp" 字段）
        # algorithms 参数限定只接受指定的算法，防止算法替换攻击
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        # 捕获所有 JWT 相关错误（签名无效、令牌过期、格式错误等）
        # 统一返回 None，由调用方决定如何处理（通常返回 401 状态码）
        return None


def get_token_expiry(token: str) -> datetime | None:
    """Extract the expiration time from a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        datetime | None: Expiration timestamp in UTC, or ``None`` if invalid.
    """
    # 先解码令牌获取 payload
    payload = decode_token(token)
    if payload and "exp" in payload:
        # 将 Unix 时间戳转换为带时区信息的 datetime 对象
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    # 如果令牌无效或不包含过期时间字段，返回 None
    return None
