# =============================================================================
# FastAPI 依赖注入模块
# =============================================================================
# 本模块提供 ResearchPulse 项目的认证与授权依赖函数，是 FastAPI 依赖注入系统的核心组成部分。
# 主要职责：
#   1. 从 HTTP 请求中提取和验证 JWT 令牌
#   2. 根据令牌获取当前登录用户信息
#   3. 提供不同级别的访问控制依赖（普通用户、活跃用户、超级管理员）
#   4. 提供基于 RBAC（基于角色的访问控制）的细粒度权限检查
#
# 架构角色：
#   - 被各个 API 路由处理函数通过 FastAPI 的 Depends() 机制调用
#   - 依赖 core.security 模块进行 JWT 令牌解码
#   - 依赖 core.database 模块获取数据库会话
#   - 依赖 core.models.user 和 core.models.permission 模块查询用户和权限数据
#
# 设计说明：
#   - 提供了多层认证依赖，从宽松到严格：
#     get_current_user_id（可选认证） → get_current_user（必须认证）
#     → get_current_active_user（必须活跃） → get_superuser（必须超管）
#   - 使用 Annotated 类型别名简化路由函数的类型标注
#   - require_permissions 使用高阶函数（闭包）模式，动态生成权限检查依赖
# =============================================================================

"""FastAPI dependencies for ResearchPulse v2.

Provides authentication and authorization dependencies.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import decode_token

# HTTP Bearer 令牌方案配置
# auto_error=False：当请求中没有携带 Bearer 令牌时不自动抛出 401 错误，
# 而是返回 None，这样可以在依赖函数中自行决定是否强制要求认证
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(http_bearer)
    ] = None,
) -> int | None:
    """Extract a user ID from an optional JWT token.

    This dependency does **not** enforce authentication. If the request does
    not contain a Bearer token or the token is invalid, it returns ``None``.

    Args:
        credentials: Optional HTTP Bearer credentials from the request.

    Returns:
        int | None: User ID if available and valid; otherwise ``None``.
    """
    # 如果请求中没有携带令牌，返回 None（表示匿名用户）
    # 此函数不强制要求认证，适用于"登录可选"的接口
    if not credentials:
        return None

    # 尝试解码令牌，获取 payload
    payload = decode_token(credentials.credentials)
    if not payload:
        return None

    # 从 payload 中提取用户 ID（存储在 "sub" 字段，JWT 标准的 subject 声明）
    user_id = payload.get("sub")
    if not user_id:
        return None

    # 尝试将用户 ID 转换为整数
    # 如果转换失败（格式异常），返回 None 而非抛出异常
    try:
        return int(user_id)
    except (ValueError, TypeError):
        return None


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(http_bearer)
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> "User":
    """Resolve the current authenticated user.

    Validates the access token, verifies token type, and loads the user
    record from the database. Disabled users are rejected.

    Args:
        credentials: HTTP Bearer credentials from the request.
        session: Async database session injected by FastAPI.

    Returns:
        User: Authenticated and active user record.

    Raises:
        HTTPException: If the request is unauthenticated, token is invalid,
            token type is not ``access``, or the user does not exist/is disabled.
    """
    # 延迟导入 User 模型，避免循环依赖
    from core.models.user import User

    # ---- 第一步：验证是否携带了认证凭证 ----
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ---- 第二步：解码并验证 JWT 令牌 ----
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ---- 第三步：检查令牌类型 ----
    # 确保使用的是 access token 而非 refresh token
    # 这是一项重要的安全措施，防止刷新令牌被用于访问受保护的资源
    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ---- 第四步：从 payload 中提取用户 ID ----
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 将 user_id 转换为整数，处理格式异常
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ---- 第五步：从数据库中查询用户记录 ----
    result = await session.execute(select(User).where(User.id == user_id_int))
    user = result.scalar_one_or_none()

    # 用户可能已被删除（令牌仍有效但用户记录不存在）
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ---- 第六步：检查用户是否处于活跃状态 ----
    # 被禁用的用户即使持有有效令牌也不能访问系统
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_active_user(
    user: "User" = Depends(get_current_user),
) -> "User":
    """Alias dependency for active users.

    This is a semantic wrapper around ``get_current_user`` to improve
    readability in route signatures.

    Args:
        user: Authenticated user injected by ``get_current_user``.

    Returns:
        User: Same user instance.
    """
    # 此函数是 get_current_user 的语义化别名
    # get_current_user 内部已经检查了 is_active 状态
    # 此函数的存在是为了在路由定义中更清晰地表达意图
    return user


async def get_superuser(
    user: "User" = Depends(get_current_user),
) -> "User":
    """Require superuser privileges.

    Args:
        user: Authenticated user injected by ``get_current_user``.

    Returns:
        User: The same user if they are a superuser.

    Raises:
        HTTPException: If the user is not a superuser.
    """
    # 检查用户是否拥有超级管理员权限
    # 超级管理员拥有系统中所有操作的权限，不受 RBAC 规则限制
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return user


def require_permissions(*required_permissions: str):
    """Create a dependency enforcing RBAC permissions.

    This factory returns a FastAPI ``Depends`` object that checks whether the
    current user has all required permissions through their roles.

    Args:
        *required_permissions: One or more permission names to require.

    Returns:
        Depends: A dependency that validates the user's permissions.

    Example:
        >>> @router.get("/admin/users")
        ... async def list_users(
        ...     user: User = Depends(require_permissions("user:manage"))
        ... ):
        ...     return {"status": "ok"}
    """
    # 这是一个高阶函数（闭包），接收所需权限列表作为参数，
    # 返回一个 Depends() 对象供 FastAPI 路由使用。
    # 通过闭包捕获 required_permissions 参数，实现动态权限检查。

    async def permission_checker(
        user: "User" = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> "User":
        # 超级管理员拥有全部权限，直接通过检查
        # Superusers have all permissions
        if user.is_superuser:
            return user

        # ---- 查询用户通过角色关联获得的所有权限 ----
        # Get user's permissions through roles
        from core.models.permission import RolePermission

        # 通过关联表（user_roles -> roles -> role_permissions）
        # 查询当前用户所拥有的所有权限 ID
        # Build permission query
        result = await session.execute(
            select(RolePermission.permission_id)
            .join(RolePermission.role)
            .join(RolePermission.role.users)
            .where(RolePermission.role.users.any(id=user.id))
        )
        user_permission_ids = [row[0] for row in result.all()]

        # 根据权限 ID 查询权限名称
        # Get permission names
        from core.models.permission import Permission

        result = await session.execute(
            select(Permission.name).where(Permission.id.in_(user_permission_ids))
        )
        # 将查询结果转换为集合，便于后续进行集合运算
        user_permissions = {row[0] for row in result.all()}

        # ---- 检查是否缺少必需的权限 ----
        # 使用集合差集运算找出用户缺少的权限
        # Check required permissions
        missing = set(required_permissions) - user_permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {', '.join(missing)}",
            )

        return user

    # 返回 Depends 包装的权限检查函数，供 FastAPI 路由使用
    return Depends(permission_checker)


# =============================================================================
# 类型别名定义
# =============================================================================
# 使用 Annotated 类型别名简化路由函数中的依赖注入声明
# 在路由函数中可以直接使用这些类型别名作为参数类型注解，
# FastAPI 会自动解析并执行对应的依赖函数
# 示例：async def my_endpoint(user: CurrentUser): ...

# Type aliases for dependency injection
CurrentUser = Annotated["User", Depends(get_current_user)]  # 当前已认证用户
CurrentActiveUser = Annotated["User", Depends(get_current_active_user)]  # 当前活跃用户
Superuser = Annotated["User", Depends(get_superuser)]  # 超级管理员用户
OptionalUserId = Annotated[int | None, Depends(get_current_user_id)]  # 可选的用户 ID（匿名访问时为 None）
