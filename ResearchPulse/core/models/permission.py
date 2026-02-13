"""Permission and Role models for RBAC in ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from core.models.user import User


class Role(Base):
    """Role model for RBAC."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        lazy="selectin",
    )
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name={self.name})>"


class Permission(Base):
    """Permission model for RBAC."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    resource: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, name={self.name})>"


class RolePermission(Base):
    """Association table for Role and Permission."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id"),
        primary_key=True,
        nullable=False,
    )
    permission_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("permissions.id"),
        primary_key=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# Predefined permissions
DEFAULT_PERMISSIONS = [
    # Article permissions
    {"name": "article:read", "resource": "article", "action": "read", "description": "View articles"},
    {"name": "article:list", "resource": "article", "action": "list", "description": "List articles"},
    # Subscription permissions
    {"name": "subscription:create", "resource": "subscription", "action": "create", "description": "Create subscriptions"},
    {"name": "subscription:read", "resource": "subscription", "action": "read", "description": "View own subscriptions"},
    {"name": "subscription:delete", "resource": "subscription", "action": "delete", "description": "Delete subscriptions"},
    # User management permissions
    {"name": "user:manage", "resource": "user", "action": "manage", "description": "Manage users"},
    {"name": "user:list", "resource": "user", "action": "list", "description": "List users"},
    # Role management permissions
    {"name": "role:manage", "resource": "role", "action": "manage", "description": "Manage roles"},
    {"name": "role:list", "resource": "role", "action": "list", "description": "List roles"},
    # Crawler management permissions
    {"name": "crawler:manage", "resource": "crawler", "action": "manage", "description": "Manage crawlers"},
    {"name": "crawler:trigger", "resource": "crawler", "action": "trigger", "description": "Trigger crawl tasks"},
    # Config management permissions
    {"name": "config:manage", "resource": "config", "action": "manage", "description": "Manage system config"},
    {"name": "config:read", "resource": "config", "action": "read", "description": "Read system config"},
    # Backup permissions
    {"name": "backup:manage", "resource": "backup", "action": "manage", "description": "Manage backups"},
    {"name": "backup:restore", "resource": "backup", "action": "restore", "description": "Restore from backup"},
]

# Predefined roles with their default permissions
DEFAULT_ROLES = {
    "superuser": {
        "description": "Superuser with all permissions",
        "permissions": [p["name"] for p in DEFAULT_PERMISSIONS],
    },
    "admin": {
        "description": "Administrator with management permissions",
        "permissions": [
            "article:read", "article:list",
            "user:manage", "user:list",
            "role:list",
            "crawler:manage", "crawler:trigger",
            "config:read", "config:manage",
            "backup:manage",
        ],
    },
    "user": {
        "description": "Regular user with basic permissions",
        "permissions": [
            "article:read", "article:list",
            "subscription:create", "subscription:read", "subscription:delete",
        ],
    },
    "guest": {
        "description": "Guest user with read-only access",
        "permissions": [
            "article:read", "article:list",
        ],
    },
}
