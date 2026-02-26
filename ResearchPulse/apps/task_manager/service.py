# =============================================================================
# 模块: apps/task_manager/service.py
# 功能: 后台任务管理服务
# 架构角色: 业务逻辑层，负责任务的创建、更新、查询和执行
# =============================================================================

"""Background task manager service."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session_factory
from .models import BackgroundTask

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TaskManager:
    """Background task manager.

    后台任务管理器，负责：
    1. 创建任务记录
    2. 异步执行任务
    3. 更新任务状态和进度
    4. 查询任务状态
    """

    def __init__(self):
        self._session_factory = get_session_factory()

    async def create_task(
        self,
        task_type: str,
        name: str,
        params: Optional[dict] = None,
        created_by: Optional[int] = None,
    ) -> BackgroundTask:
        """Create a new task record.

        创建新的任务记录。

        Args:
            task_type: Task type (e.g., "daily_report").
            name: Task name/description.
            params: Task parameters.
            created_by: User ID who created the task.

        Returns:
            Created BackgroundTask instance.
        """
        task_id = str(uuid.uuid4())

        async with self._session_factory() as db:
            task = BackgroundTask(
                task_id=task_id,
                task_type=task_type,
                name=name,
                params=params or {},
                status="pending",
                created_by=created_by,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)

            logger.info(f"Created task: {task_id} ({task_type})")
            return task

    async def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by task_id.

        根据 task_id 获取任务。
        """
        async with self._session_factory() as db:
            query = select(BackgroundTask).where(BackgroundTask.task_id == task_id)
            result = await db.execute(query)
            return result.scalar_one_or_none()

    async def get_tasks_by_type(
        self,
        task_type: str,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> list[BackgroundTask]:
        """Get tasks by type.

        根据类型获取任务列表。
        """
        async with self._session_factory() as db:
            query = select(BackgroundTask).where(BackgroundTask.task_type == task_type)

            if status:
                query = query.where(BackgroundTask.status == status)

            query = query.order_by(BackgroundTask.created_at.desc()).limit(limit)
            result = await db.execute(query)
            return list(result.scalars().all())

    async def update_progress(
        self,
        task_id: str,
        progress: int,
        progress_message: str = "",
    ) -> None:
        """Update task progress.

        更新任务进度。
        """
        async with self._session_factory() as db:
            await db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.task_id == task_id)
                .values(
                    progress=progress,
                    progress_message=progress_message,
                )
            )
            await db.commit()

    async def start_task(self, task_id: str) -> None:
        """Mark task as started.

        标记任务开始执行。
        """
        async with self._session_factory() as db:
            await db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.task_id == task_id)
                .values(
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    async def complete_task(
        self,
        task_id: str,
        result: Optional[dict] = None,
    ) -> None:
        """Mark task as completed.

        标记任务完成。
        """
        async with self._session_factory() as db:
            await db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.task_id == task_id)
                .values(
                    status="completed",
                    progress=100,
                    result=result,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    async def fail_task(
        self,
        task_id: str,
        error_message: str,
    ) -> None:
        """Mark task as failed.

        标记任务失败。
        """
        async with self._session_factory() as db:
            await db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.task_id == task_id)
                .values(
                    status="failed",
                    error_message=error_message,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    async def run_in_background(
        self,
        task: BackgroundTask,
        coro: Callable[[], Coroutine[Any, Any, T]],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        """Run a coroutine in background with task tracking.

        在后台运行协程，并跟踪任务状态。

        Args:
            task: BackgroundTask instance.
            coro: Coroutine to run.
            progress_callback: Optional callback for progress updates.
        """
        try:
            # 标记任务开始
            await self.start_task(task.task_id)

            # 创建进度更新器
            async def update_progress(progress: int, message: str = ""):
                await self.update_progress(task.task_id, progress, message)
                if progress_callback:
                    progress_callback(progress, message)

            # 执行任务
            result = await coro()

            # 标记完成
            await self.complete_task(task.task_id, result=result if isinstance(result, dict) else {"data": result})

            logger.info(f"Task completed: {task.task_id}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task failed: {task.task_id} - {error_msg}")
            await self.fail_task(task.task_id, error_msg)

    def spawn_background_task(
        self,
        task_type: str,
        name: str,
        coro: Callable[[], Coroutine[Any, Any, T]],
        params: Optional[dict] = None,
        created_by: Optional[int] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """Spawn a background task.

        启动后台任务（立即返回 task_id）。

        Args:
            task_type: Task type.
            name: Task name.
            coro: Coroutine to run.
            params: Task parameters.
            created_by: User ID.
            progress_callback: Optional progress callback.

        Returns:
            Task ID for status querying.
        """

        async def _run():
            # 创建任务记录
            task = await self.create_task(
                task_type=task_type,
                name=name,
                params=params,
                created_by=created_by,
            )

            # 在后台运行
            await self.run_in_background(task, coro, progress_callback)

            return task.task_id

        # 启动后台任务
        task_handle = asyncio.create_task(_run())

        # 返回一个包装器，可以通过 await 获取 task_id
        return task_handle

    async def get_or_create_task_id(
        self,
        task_type: str,
        name: str,
        params: Optional[dict] = None,
        created_by: Optional[int] = None,
    ) -> tuple[str, bool]:
        """Get existing pending/running task or create new one.

        获取现有的待处理/运行中任务，或创建新任务。
        返回 (task_id, is_new) 元组。

        这可以防止用户重复点击创建多个相同任务。
        """
        # 查找最近的待处理或运行中任务
        async with self._session_factory() as db:
            query = (
                select(BackgroundTask)
                .where(BackgroundTask.task_type == task_type)
                .where(BackgroundTask.status.in_(["pending", "running"]))
                .order_by(BackgroundTask.created_at.desc())
                .limit(1)
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                return existing.task_id, False

            # 创建新任务
            task = await self.create_task(
                task_type=task_type,
                name=name,
                params=params,
                created_by=created_by,
            )
            return task.task_id, True


# 全局任务管理器实例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get global task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
