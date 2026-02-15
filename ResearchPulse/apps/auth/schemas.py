# ==========================================================================
# 认证模块 - Pydantic 数据校验模式 (Schemas)
# --------------------------------------------------------------------------
# 本模块定义了认证相关 API 端点所使用的请求和响应数据模型。
# 使用 Pydantic BaseModel 实现以下功能：
#   1. 请求参数的自动校验（类型检查、长度限制、格式验证等）
#   2. 响应数据的序列化与结构化
#   3. 自动生成 OpenAPI/Swagger 文档中的数据模型描述
#
# 架构位置：
#   本模块位于 apps/auth/schemas.py，属于"认证应用"(auth app) 的数据层。
#   被 api.py 路由层引用，用于请求体解析和响应格式化。
#   与 service.py（业务逻辑）和 core/models/user.py（ORM 模型）分离，
#   遵循关注点分离原则。
#
# 包含的 Schema：
#   - UserRegisterRequest  : 用户注册请求
#   - UserLoginRequest     : 用户登录请求
#   - TokenResponse        : 令牌响应（登录/刷新共用）
#   - UserResponse         : 用户信息响应
#   - RefreshTokenRequest  : 令牌刷新请求
#   - ChangePasswordRequest: 密码修改请求
# ==========================================================================

"""Pydantic schemas for authentication API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# --------------------------------------------------------------------------
# 用户注册请求模型
# --------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    """Request schema for user registration.

    用户注册请求数据模型。

    Attributes:
        username: Username (alphanumeric, 3-50 chars).
        email: Email address.
        password: Plaintext password (6-100 chars).
    """

    # 用户名：3-50 个字符，仅允许字母和数字（通过 validator 进一步校验）
    username: str = Field(..., min_length=3, max_length=50)
    # 邮箱：使用 Pydantic 的 EmailStr 类型自动验证邮箱格式
    email: EmailStr
    # 密码：6-100 个字符，明文传输后由后端进行哈希处理
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate and normalize the username.

        校验用户名仅包含字母与数字，并统一转为小写。

        Args:
            v: Raw username string.

        Returns:
            str: Normalized username.

        Raises:
            ValueError: If username contains non-alphanumeric characters.
        """
        # 校验用户名只包含字母和数字，不允许特殊字符
        # 这可以避免用户名中包含可能导致安全问题的字符（如 SQL 注入、XSS）
        if not v.isalnum():
            raise ValueError("Username must contain only alphanumeric characters")
        # 统一将用户名转为小写存储，确保用户名大小写不敏感
        return v.lower()


# --------------------------------------------------------------------------
# 用户登录请求模型
# --------------------------------------------------------------------------
class UserLoginRequest(BaseModel):
    """Request schema for user login.

    用户登录请求数据模型。

    Attributes:
        username: Username or email.
        password: Plaintext password.
    """

    # 用户名或邮箱：最少 1 个字符，后端会同时匹配 username 和 email 字段
    username: str = Field(..., min_length=1)
    # 密码：最少 1 个字符（长度校验在注册时已完成，登录时仅确保非空）
    password: str = Field(..., min_length=1)


# --------------------------------------------------------------------------
# 令牌响应模型
# --------------------------------------------------------------------------
class TokenResponse(BaseModel):
    """Response schema for token endpoints.

    令牌响应数据模型。

    Attributes:
        access_token: JWT access token.
        refresh_token: JWT refresh token.
        token_type: Token type (bearer).
        expires_in: Access token lifetime in seconds.
    """

    access_token: str          # JWT 访问令牌，用于 API 请求的身份认证
    refresh_token: str         # JWT 刷新令牌，用于在 access_token 过期后获取新令牌
    token_type: str = "bearer" # 令牌类型，固定为 "bearer"，符合 OAuth2 规范
    expires_in: int            # access_token 的有效期（秒），前端可据此设置定时刷新


# --------------------------------------------------------------------------
# 用户信息响应模型
# --------------------------------------------------------------------------
class UserResponse(BaseModel):
    """Response schema for user data.

    用户信息响应数据模型。

    Attributes:
        id: User ID.
        username: Username.
        email: Email address.
        is_active: Whether the account is active.
        is_superuser: Whether the user is a superuser.
        roles: Role names.
        created_at: Account creation time.
        last_login_at: Last login time.
    """

    id: int                              # 用户唯一标识
    username: str                        # 用户名
    email: str                           # 邮箱地址
    is_active: bool                      # 账户是否激活（被禁用的用户无法登录）
    is_superuser: bool                   # 是否为超级管理员
    roles: list[str] = []               # 用户角色名称列表（如 ["user"]、["superuser"]）
    created_at: datetime                 # 账户创建时间
    last_login_at: datetime | None = None  # 最后登录时间，新用户可能为 None

    # Pydantic 配置：允许从 ORM 模型属性直接映射
    class Config:
        from_attributes = True


# --------------------------------------------------------------------------
# 令牌刷新请求模型
# --------------------------------------------------------------------------
class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh.

    刷新令牌请求模型。

    Attributes:
        refresh_token: Refresh token string.
    """

    # 客户端提供的 refresh_token，用于换取新的令牌对
    refresh_token: str


# --------------------------------------------------------------------------
# 密码修改请求模型
# --------------------------------------------------------------------------
class ChangePasswordRequest(BaseModel):
    """Request schema for password change.

    修改密码请求模型。

    Attributes:
        current_password: Current plaintext password.
        new_password: New plaintext password.
    """

    # 当前密码：用于验证用户身份，防止令牌被盗后恶意修改密码
    current_password: str = Field(..., min_length=1)
    # 新密码：6-100 个字符，与注册时的密码要求一致
    new_password: str = Field(..., min_length=6, max_length=100)
