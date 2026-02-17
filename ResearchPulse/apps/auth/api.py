# ==========================================================================
# 认证 API 模块
# --------------------------------------------------------------------------
# 本模块是 ResearchPulse 系统的用户认证接口层，负责处理所有与身份认证相关的
# HTTP 请求。采用 JWT（JSON Web Token）无状态认证机制。
#
# 提供以下端点：
#   1. POST /auth/send-verification —— 发送邮箱验证码
#   2. POST /auth/verify-email     —— 验证邮箱
#   3. POST /auth/register         —— 用户注册（需验证令牌）
#   4. POST /auth/login            —— 用户登录，返回 access_token + refresh_token
#   5. POST /auth/refresh          —— 使用 refresh_token 刷新 access_token
#   6. GET  /auth/me               —— 获取当前登录用户信息
#   7. POST /auth/change-password  —— 修改当前用户密码
#   8. POST /auth/logout           —— 用户登出（JWT 模式下为客户端操作）
#
# 架构位置：
#   本模块位于 apps/auth/api.py，属于"认证应用"(auth app) 的路由层。
#   业务逻辑委托给 AuthService（service.py），数据校验由 schemas.py 负责。
#   通过 FastAPI 的 APIRouter 注册到主应用，所有端点统一挂载在 /auth 前缀下。
# ==========================================================================

"""Authentication API endpoints for ResearchPulse v2."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import CurrentUser, get_current_user
from core.security import create_access_token, create_refresh_token
from core.models.user import User
from settings import settings

from .schemas import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SendPasswordResetRequest,
    SendPasswordResetResponse,
    SendVerificationRequest,
    SendVerificationResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
    VerifyPasswordResetRequest,
    VerifyPasswordResetResponse,
)
from .service import AuthService
from .verification_service import VerificationService

# 创建认证路由器，所有端点挂载在 /auth 前缀下，标签为 "authentication"
router = APIRouter(prefix="/auth", tags=["authentication"])


# --------------------------------------------------------------------------
# 发送验证码端点
# --------------------------------------------------------------------------
@router.post("/send-verification", response_model=SendVerificationResponse)
async def send_verification(
    request: SendVerificationRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send verification code to email.

    发送邮箱验证码，用于用户注册前的邮箱验证。

    Args:
        request: Email address to send code to.
        session: Async database session.

    Returns:
        dict: Response with status and retry_after if rate limited.

    Raises:
        HTTPException: If rate limited (429) or other error.
    """
    result = await VerificationService.send_verification_code(
        email=request.email,
        session=session,
    )

    if not result["success"]:
        if result.get("retry_after"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=result["message"],
                headers={"Retry-After": str(result["retry_after"])},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"],
        )

    return {
        "message": result["message"],
        "retry_after": result.get("retry_after"),
    }


# --------------------------------------------------------------------------
# 验证邮箱端点
# --------------------------------------------------------------------------
@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    request: VerifyEmailRequest,
) -> dict:
    """Verify email with the provided code.

    验证邮箱地址，成功后返回用于注册的验证令牌。

    Args:
        request: Email and verification code.

    Returns:
        dict: Response with verification token if successful.

    Raises:
        HTTPException: If verification fails.
    """
    result = await VerificationService.verify_email(
        email=request.email,
        code=request.code,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"],
        )

    return {
        "message": result["message"],
        "verification_token": result["verification_token"],
    }


# --------------------------------------------------------------------------
# 用户注册端点
# --------------------------------------------------------------------------
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: UserRegisterRequest,  # 请求体：经过 Pydantic 校验的注册信息（用户名、邮箱、密码、验证令牌）
    session: AsyncSession = Depends(get_session),  # 异步数据库会话
) -> dict:
    """Register a new user account.

    创建用户账户并返回用户信息。需要先通过邮箱验证获取验证令牌。

    Args:
        request: Registration payload with verification token.
        session: Async database session.

    Returns:
        dict: User response payload.

    Raises:
        HTTPException: If verification token is invalid or username/email already exists.
    """
    # 验证邮箱验证令牌
    if not VerificationService.validate_verification_token(
        email=request.email,
        token=request.verification_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱验证已过期，请重新验证",
        )

    try:
        # 委托 AuthService 执行注册逻辑（用户名/邮箱唯一性检查、密码哈希、角色分配等）
        user = await AuthService.register(
            session=session,
            username=request.username,
            email=request.email,
            password=request.password,
        )

        # 注册成功，清理验证数据
        VerificationService.cleanup_verification_data(request.email)

        # 将 ORM 用户对象转换为响应字典
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "roles": [role.name for role in user.roles],
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
        }
    except ValueError as e:
        # AuthService 用 ValueError 表示业务校验失败（如用户名重复）
        # 转换为 HTTP 400 错误返回给客户端
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# --------------------------------------------------------------------------
# 用户登录端点
# --------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(
    request: UserLoginRequest,  # 请求体：用户名（或邮箱）+ 密码
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Login and receive access and refresh tokens.

    验证用户凭据并返回令牌对。

    Args:
        request: Login payload.
        session: Async database session.

    Returns:
        dict: Token response payload.

    Raises:
        HTTPException: If credentials are invalid or account disabled.
    """
    try:
        # 验证用户凭据，成功后返回用户对象及 JWT 令牌对
        user, access_token, refresh_token = await AuthService.login(
            session=session,
            username=request.username,
            password=request.password,
        )
        # 构造令牌响应，expires_in 以秒为单位（分钟数 * 60）
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    except ValueError as e:
        # 登录失败（凭据错误或账户被禁用）返回 HTTP 401
        # 附带 WWW-Authenticate 头部，符合 OAuth2 / Bearer 规范
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# --------------------------------------------------------------------------
# 令牌刷新端点
# --------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,  # 请求体：包含 refresh_token
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Refresh access token using refresh token.

    使用 refresh_token 生成新的令牌对。

    Args:
        request: Refresh token payload.
        session: Async database session.

    Returns:
        dict: Token response payload.

    Raises:
        HTTPException: If refresh token is invalid or expired.
    """
    try:
        # 使用 refresh_token 换取新的令牌对
        # 旧的 refresh_token 不会被主动失效（无状态 JWT 设计）
        access_token, refresh_token = await AuthService.refresh_tokens(
            session=session,
            refresh_token=request.refresh_token,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    except ValueError as e:
        # refresh_token 无效或已过期时返回 HTTP 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# --------------------------------------------------------------------------
# 获取当前用户信息端点
# --------------------------------------------------------------------------
@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user),  # 依赖注入：从 JWT 中解析并验证当前用户
) -> dict:
    """Get current authenticated user information.

    返回当前登录用户的基础信息与角色列表。

    Args:
        user: Authenticated user injected by dependency.

    Returns:
        dict: User response payload.
    """
    # 直接从已认证的用户对象中提取信息返回
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "roles": [role.name for role in user.roles],
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


# --------------------------------------------------------------------------
# 修改密码端点
# --------------------------------------------------------------------------
@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,  # 请求体：当前密码 + 新密码
    user: User = Depends(get_current_user),  # 必须已登录
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Change the current user's password.

    验证旧密码并更新为新密码。

    Args:
        request: Change password payload.
        user: Authenticated user.
        session: Async database session.

    Returns:
        dict: Status message.

    Raises:
        HTTPException: If current password is incorrect.
    """
    try:
        # 委托 AuthService 校验当前密码并更新为新密码
        await AuthService.change_password(
            session=session,
            user=user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
        return {"status": "ok", "message": "Password changed successfully"}
    except ValueError as e:
        # 当前密码错误时返回 HTTP 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# --------------------------------------------------------------------------
# 用户登出端点
# --------------------------------------------------------------------------
@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user),  # 必须已登录才能执行登出操作
) -> dict:
    """Logout current user.

    JWT 无状态模式下登出由客户端清除令牌完成，此端点保留用于一致性。

    Args:
        user: Authenticated user.

    Returns:
        dict: Status message.
    """
    # JWT 无状态设计下，服务端无法主动使令牌失效
    # 实际登出由客户端清除本地存储的令牌来完成
    # 此端点保留是为了 API 完整性，未来可扩展支持令牌黑名单机制
    return {"status": "ok", "message": "Logged out successfully"}


# --------------------------------------------------------------------------
# 发送密码重置验证码端点
# --------------------------------------------------------------------------
@router.post("/send-password-reset", response_model=SendPasswordResetResponse)
async def send_password_reset(
    request: SendPasswordResetRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send password reset verification code to email.

    发送密码重置验证码到指定邮箱。

    Args:
        request: Email address to send code to.
        session: Async database session.

    Returns:
        dict: Response with status and retry_after if rate limited.

    Raises:
        HTTPException: If rate limited (429) or other error.
    """
    result = await VerificationService.send_password_reset_code(
        email=request.email,
        session=session,
    )

    if not result["success"]:
        if result.get("retry_after"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=result["message"],
                headers={"Retry-After": str(result["retry_after"])},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"],
        )

    return {
        "message": result["message"],
        "retry_after": result.get("retry_after"),
    }


# --------------------------------------------------------------------------
# 验证密码重置码端点
# --------------------------------------------------------------------------
@router.post("/verify-password-reset", response_model=VerifyPasswordResetResponse)
async def verify_password_reset(
    request: VerifyPasswordResetRequest,
) -> dict:
    """Verify password reset code.

    验证密码重置验证码，成功后返回重置令牌。

    Args:
        request: Email and verification code.

    Returns:
        dict: Response with reset token if successful.

    Raises:
        HTTPException: If verification fails.
    """
    result = await VerificationService.verify_password_reset_code(
        email=request.email,
        code=request.code,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"],
        )

    return {
        "message": result["message"],
        "reset_token": result["reset_token"],
    }


# --------------------------------------------------------------------------
# 重置密码端点
# --------------------------------------------------------------------------
@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reset user password.

    重置用户密码。

    Args:
        request: Email, new password, and reset token.
        session: Async database session.

    Returns:
        dict: Status message.

    Raises:
        HTTPException: If reset token is invalid or user not found.
    """
    # 验证重置令牌
    if not VerificationService.validate_reset_token(
        email=request.email,
        token=request.reset_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证已过期，请重新获取验证码",
        )

    # 查找用户
    from sqlalchemy import select
    result = await session.execute(
        select(User).where(User.email == request.email.lower())
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在",
        )

    # 更新密码
    user.set_password(request.new_password)

    # 清理重置数据
    VerificationService.cleanup_reset_data(request.email)

    return {"status": "ok", "message": "密码重置成功"}
