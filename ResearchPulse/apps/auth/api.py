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
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from .service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: UserRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Register a new user account."""
    try:
        user = await AuthService.register(
            session=session,
            username=request.username,
            email=request.email,
            password=request.password,
        )
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: UserLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Login and receive access and refresh tokens."""
    try:
        user, access_token, refresh_token = await AuthService.login(
            session=session,
            username=request.username,
            password=request.password,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Refresh access token using refresh token."""
    try:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user),
) -> dict:
    """Get current authenticated user information."""
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


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Change the current user's password."""
    try:
        await AuthService.change_password(
            session=session,
            user=user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
        return {"status": "ok", "message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user),
) -> dict:
    """Logout current user.

    Note: With JWT, actual logout is handled client-side by removing tokens.
    This endpoint exists for API consistency and future token blacklist support.
    """
    return {"status": "ok", "message": "Logged out successfully"}
