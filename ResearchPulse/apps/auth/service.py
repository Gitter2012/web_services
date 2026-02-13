"""Authentication service for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.permission import Role
from core.models.user import User
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Service class for authentication operations."""

    @staticmethod
    async def register(
        session: AsyncSession,
        username: str,
        email: str,
        password: str,
        assign_default_role: bool = True,
    ) -> User:
        """Register a new user."""
        # Check if username or email already exists
        result = await session.execute(
            select(User).where(
                or_(User.username == username.lower(), User.email == email.lower())
            )
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            if existing_user.username == username.lower():
                raise ValueError("Username already exists")
            raise ValueError("Email already exists")

        # Create new user
        user = User(
            username=username.lower(),
            email=email.lower(),
            is_active=True,
            is_superuser=False,
        )
        user.set_password(password)

        # Assign default 'user' role
        if assign_default_role:
            result = await session.execute(select(Role).where(Role.name == "user"))
            default_role = result.scalar_one_or_none()
            if default_role:
                user.roles.append(default_role)

        session.add(user)
        await session.flush()
        await session.refresh(user)

        logger.info(f"User registered: {username}")
        return user

    @staticmethod
    async def login(
        session: AsyncSession,
        username: str,
        password: str,
    ) -> tuple[User, str, str]:
        """Authenticate user and return tokens.

        Returns:
            Tuple of (user, access_token, refresh_token)
        """
        # Find user by username or email
        result = await session.execute(
            select(User).where(
                or_(
                    User.username == username.lower(),
                    User.email == username.lower(),
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError("Invalid credentials")

        if not user.is_active:
            raise ValueError("Account is disabled")

        if not user.check_password(password):
            raise ValueError("Invalid credentials")

        # Update last login
        user.update_last_login()

        # Generate tokens
        token_data = {"sub": str(user.id)}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        logger.info(f"User logged in: {user.username}")
        return user, access_token, refresh_token

    @staticmethod
    async def refresh_tokens(
        session: AsyncSession,
        refresh_token: str,
    ) -> tuple[str, str]:
        """Refresh access token using refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token)
        """
        payload = decode_token(refresh_token)
        if not payload:
            raise ValueError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")

        # Get user
        result = await session.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise ValueError("User not found or inactive")

        # Generate new tokens
        token_data = {"sub": str(user.id)}
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)

        return new_access_token, new_refresh_token

    @staticmethod
    async def change_password(
        session: AsyncSession,
        user: User,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change user's password."""
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect")

        user.set_password(new_password)
        logger.info(f"Password changed for user: {user.username}")

    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
        """Get user by ID."""
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(
        session: AsyncSession, username: str
    ) -> User | None:
        """Get user by username."""
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_superuser(
        session: AsyncSession,
        username: str,
        email: str,
        password: str,
    ) -> User:
        """Create a superuser account."""
        user = User(
            username=username.lower(),
            email=email.lower(),
            is_active=True,
            is_superuser=True,
        )
        user.set_password(password)

        # Assign superuser role
        result = await session.execute(select(Role).where(Role.name == "superuser"))
        superuser_role = result.scalar_one_or_none()
        if superuser_role:
            user.roles.append(superuser_role)

        session.add(user)
        await session.flush()
        await session.refresh(user)

        logger.info(f"Superuser created: {username}")
        return user
