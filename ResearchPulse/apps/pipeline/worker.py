"""Pipeline task queue worker.

Polls the ``pipeline_tasks`` table and executes pending tasks by delegating
to the existing scheduler job functions.  Registered as an APScheduler
interval job in ``apps/scheduler/tasks.py``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from core.database import get_session_factory
from apps.pipeline.models import PipelineTask

logger = logging.getLogger(__name__)

# Stage → job function mapping (lazy imports inside _execute_stage)
_STAGE_JOB_MAP = {
    "ai": "apps.scheduler.jobs.ai_process_job:run_ai_process_job",
    "embedding": "apps.scheduler.jobs.embedding_job:run_embedding_job",
    "event": "apps.scheduler.jobs.event_cluster_job:run_event_cluster_job",
    "action": "apps.scheduler.jobs.action_extract_job:run_action_extract_job",
    "topic": "apps.scheduler.jobs.topic_match_job:run_topic_match_job",
}


async def _execute_stage(stage: str, payload: dict | None) -> dict:
    """Execute a pipeline stage by delegating to its job function.

    Args:
        stage: The pipeline stage name.
        payload: Optional payload (currently unused by job functions).

    Returns:
        Result dict from the job function.

    Raises:
        ValueError: If the stage name is not recognized.
    """
    entry = _STAGE_JOB_MAP.get(stage)
    if not entry:
        raise ValueError(f"Unknown pipeline stage: {stage}")

    module_path, func_name = entry.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    job_func = getattr(module, func_name)
    return await job_func()


async def run_pipeline_worker() -> dict:
    """Poll and execute pending pipeline tasks.

    This function is designed to be called by APScheduler on an interval.
    It loops through pending tasks one at a time using SELECT ... FOR UPDATE
    SKIP LOCKED to allow safe concurrent execution.

    Returns:
        dict with counts of completed, failed, and total tasks processed.
    """
    session_factory = get_session_factory()
    completed_count = 0
    failed_count = 0

    while True:
        # --- Claim one pending task ---
        async with session_factory() as session:
            # Use raw SQL for FOR UPDATE SKIP LOCKED (not all SQLAlchemy
            # dialects expose SKIP LOCKED via the ORM).
            row = (
                await session.execute(
                    text(
                        "SELECT id FROM pipeline_tasks "
                        "WHERE status = 'pending' "
                        "ORDER BY priority DESC, created_at ASC "
                        "LIMIT 1 "
                        "FOR UPDATE SKIP LOCKED"
                    )
                )
            ).first()

            if row is None:
                break

            task_id = row[0]

            # Mark as running
            await session.execute(
                text(
                    "UPDATE pipeline_tasks "
                    "SET status = 'running', started_at = :now "
                    "WHERE id = :id"
                ),
                {"id": task_id, "now": datetime.now(timezone.utc)},
            )
            await session.commit()

        # --- Load task details and execute ---
        async with session_factory() as session:
            task = await session.get(PipelineTask, task_id)
            if task is None:
                continue

            stage = task.stage
            payload = task.payload

        try:
            result = await _execute_stage(stage, payload)

            # Check for "skipped" results (feature disabled) – treat as success
            if result.get("skipped"):
                logger.info(
                    "Pipeline task %s stage=%s skipped (feature disabled)",
                    task_id,
                    stage,
                )

            # Mark completed
            async with session_factory() as session:
                await session.execute(
                    text(
                        "UPDATE pipeline_tasks "
                        "SET status = 'completed', result = :result, "
                        "    completed_at = :now "
                        "WHERE id = :id"
                    ),
                    {
                        "id": task_id,
                        "result": _json_dumps(result),
                        "now": datetime.now(timezone.utc),
                    },
                )
                await session.commit()

            completed_count += 1

            # NOTE: downstream enqueue is handled inside each job function
            # (ai_process_job, embedding_job), so we do NOT enqueue again here
            # to avoid duplicate tasks.

        except Exception as exc:
            logger.error(
                "Pipeline task %s stage=%s failed: %s",
                task_id,
                stage,
                exc,
                exc_info=True,
            )
            failed_count += 1

            async with session_factory() as session:
                task = await session.get(PipelineTask, task_id)
                if task is None:
                    continue

                task.retry_count += 1
                task.error_message = str(exc)[:2000]

                if task.retry_count < task.max_retries:
                    task.status = "pending"
                    task.started_at = None
                else:
                    task.status = "failed"
                    task.completed_at = datetime.now(timezone.utc)

                await session.commit()

    total = completed_count + failed_count
    if total > 0:
        logger.info(
            "Pipeline worker finished: %d completed, %d failed out of %d",
            completed_count,
            failed_count,
            total,
        )
    return {
        "completed": completed_count,
        "failed": failed_count,
        "total": total,
    }


def _json_dumps(obj: dict) -> str:
    """Serialize a dict to a JSON string for storage."""
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
