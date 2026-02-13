"""User model for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from core.models.permission import Role


class User(Base, TimestampMixin):
    """User model for authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Email notification settings
    email_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether user wants to receive email notifications",
    )
    email_digest_frequency: Mapped[str] = mapped_column(
        String(20),
        default="daily",
        nullable=False,
        comment="Email digest frequency: daily, weekly, or none",
    )

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"

    def set_password(self, password: str) -> None:
        """Set the user's password hash."""
        from core.security import hash_password

        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        """Check if the provided password is correct."""
        from core.security import verify_password

        return verify_password(password, self.password_hash)

    def update_last_login(self) -> None:
        """Update the last login timestamp."""
        self.last_login_at = datetime.now(timezone.utc)

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission (requires loaded roles)."""
        if self.is_superuser:
            return True
        for role in self.roles:
            for perm in role.permissions:
                if perm.name == permission:
                    return True
        return False

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return any(role.name == role_name for role in self.roles)


class UserRole(Base):
    """Association table for User and Role."""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        primary_key=True,
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id"),
        primary_key=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
