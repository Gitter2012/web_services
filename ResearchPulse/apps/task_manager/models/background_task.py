# =============================================================================
# 模块: apps/task_manager/models/background_task.py
# 功能: 后台任务追踪模型
# 架构角色: 数据持久化层，存储长时间运行任务的状态
# =============================================================================

"""Background task tracking model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class BackgroundTask(Base, TimestampMixin):
    """Background task tracking model.

    后台任务追踪模型，用于管理长时间运行的任务状态。

    状态流转：
        pending -> running -> completed / failed / cancelled
    """

    __tablename__ = "background_tasks"

    # 任务主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 任务唯一标识符（用于 API 查询）
    task_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique task identifier (UUID)",
    )

    # 任务类型（如 "daily_report", "ai_pipeline" 等）
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Task type (e.g., daily_report, ai_pipeline)",
    )

    # 任务名称/描述
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Task name/description",
    )

    # 任务状态：pending, running, completed, failed, cancelled
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="Task status: pending, running, completed, failed, cancelled",
    )

    # 进度百分比（0-100）
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Progress percentage (0-100)",
    )

    # 进度消息（如 "正在处理分类 3/6"）
    progress_message: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Progress message",
    )

    # 任务参数（JSON 格式）
    params: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Task parameters",
    )

    # 任务结果（JSON 格式）
    result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Task result",
    )

    # 错误信息
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if task failed",
    )

    # 任务创建者ID
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="User ID who created the task",
    )

    # 任务开始时间
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Task start time",
    )

    # 任务完成时间
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Task completion time",
    )

    # 任务是否已读（用于通知）
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether the task notification has been read",
    )

    def __repr__(self) -> str:
        """Return a readable task representation."""
        return f"<BackgroundTask(task_id={self.task_id}, type={self.task_type}, status={self.status})>"

    def to_dict(self) -> dict:
        """Convert task to dictionary for API response."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "name": self.name,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "result": self.result,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
