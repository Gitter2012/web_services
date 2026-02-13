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

# HTTP Bearer token scheme
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(http_bearer)
    ] = None,
) -> int | None:
    """Extract user ID from JWT token without requiring authentication."""
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

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
    """Get the current authenticated user.

    Raises HTTPException if not authenticated.
    """
    from core.models.user import User

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await session.execute(select(User).where(User.id == user_id_int))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_active_user(
    user: "User" = Depends(get_current_user),
) -> "User":
    """Get current active user (alias for clarity)."""
    return user


async def get_superuser(
    user: "User" = Depends(get_current_user),
) -> "User":
    """Require superuser privileges."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return user


def require_permissions(*required_permissions: str):
    """Create a dependency that requires specific permissions.

    Usage:
        @router.get("/admin/users")
        async def list_users(user: User = Depends(require_permissions("user:manage"))):
            ...
    """

    async def permission_checker(
        user: "User" = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> "User":
        # Superusers have all permissions
        if user.is_superuser:
            return user

        # Get user's permissions through roles
        from core.models.permission import RolePermission

        # Build permission query
        result = await session.execute(
            select(RolePermission.permission_id)
            .join(RolePermission.role)
            .join(RolePermission.role.users)
            .where(RolePermission.role.users.any(id=user.id))
        )
        user_permission_ids = [row[0] for row in result.all()]

        # Get permission names
        from core.models.permission import Permission

        result = await session.execute(
            select(Permission.name).where(Permission.id.in_(user_permission_ids))
        )
        user_permissions = {row[0] for row in result.all()}

        # Check required permissions
        missing = set(required_permissions) - user_permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {', '.join(missing)}",
            )

        return user

    return Depends(permission_checker)


# Type aliases for dependency injection
CurrentUser = Annotated["User", Depends(get_current_user)]
CurrentActiveUser = Annotated["User", Depends(get_current_active_user)]
Superuser = Annotated["User", Depends(get_superuser)]
OptionalUserId = Annotated[int | None, Depends(get_current_user_id)]
