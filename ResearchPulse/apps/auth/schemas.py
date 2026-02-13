"""Pydantic schemas for authentication API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    """Request schema for user registration."""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError("Username must contain only alphanumeric characters")
        return v.lower()


class UserLoginRequest(BaseModel):
    """Request schema for user login."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Response schema for token endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Response schema for user data."""

    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    roles: list[str] = []
    created_at: datetime
    last_login_at: datetime | None = None

    class Config:
        from_attributes = True


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Request schema for password change."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)
