"""System configuration and audit models for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class SystemConfig(Base, TimestampMixin):
    """System configuration stored in database."""

    __tablename__ = "system_config"

    config_key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Configuration key",
    )
    config_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Configuration value",
    )
    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )
    is_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this config contains sensitive data",
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<SystemConfig(key={self.config_key})>"


class BackupRecord(Base, TimestampMixin):
    """Backup record for data retention."""

    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backup_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        unique=True,
        nullable=False,
        index=True,
    )
    backup_file: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    backup_size: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Backup file size in bytes",
    )
    article_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="Status: pending, completed, failed",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<BackupRecord(date={self.backup_date}, status={self.status})>"


class AuditLog(Base):
    """Audit log for user actions."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    resource_id: Mapped[str] = mapped_column(
        String(100),
        default="",
        nullable=False,
    )
    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    ip_address: Mapped[str] = mapped_column(
        String(45),
        default="",
        nullable=False,
    )
    user_agent: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<AuditLog(action={self.action}, resource={self.resource_type})>"
