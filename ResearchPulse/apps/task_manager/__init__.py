# =============================================================================
# 模块: apps/task_manager/__init__.py
# 功能: 任务管理模块入口
# =============================================================================

"""Task manager module for background task tracking."""

from .models import BackgroundTask
from .service import TaskManager

__all__ = ["BackgroundTask", "TaskManager"]
