"""Pipeline task queue trigger helpers.

Functions for enqueuing downstream pipeline tasks.  The caller is responsible
for committing the session after calling these helpers.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.pipeline.models import PipelineTask

logger = logging.getLogger(__name__)


async def enqueue_task(
    db: AsyncSession,
    stage: str,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
) -> PipelineTask:
    """Insert a new pipeline task and return it with its generated ID.

    Args:
        db: Async database session (caller must commit).
        stage: Pipeline stage name (ai, embedding, event, action).
        payload: Optional JSON payload for the task.
        priority: Task priority (higher = executed first).

    Returns:
        The newly created PipelineTask instance.
    """
    task = PipelineTask(
        stage=stage,
        status="pending",
        priority=priority,
        payload=payload,
    )
    db.add(task)
    await db.flush()
    logger.info("Enqueued pipeline task id=%s stage=%s priority=%s", task.id, stage, priority)
    return task


async def enqueue_downstream_after_ai(
    db: AsyncSession,
    ai_result: dict[str, Any],
    trigger_source: str = "ai_process_job",
) -> list[PipelineTask]:
    """Enqueue embedding and action tasks after AI processing completes.

    Only enqueues when there were actually processed articles (processed > 0).

    Args:
        db: Async database session (caller must commit).
        ai_result: Result dict from the AI processing job.
        trigger_source: Identifier for the trigger origin.

    Returns:
        List of created PipelineTask instances (may be empty).
    """
    processed = ai_result.get("processed", 0)
    if processed <= 0:
        return []

    payload = {"trigger_source": trigger_source, "ai_processed_count": processed}
    tasks = []
    tasks.append(await enqueue_task(db, "embedding", payload=payload, priority=1))
    tasks.append(await enqueue_task(db, "action", payload=payload, priority=0))
    return tasks


async def enqueue_downstream_after_embedding(
    db: AsyncSession,
    embedding_result: dict[str, Any],
    trigger_source: str = "embedding_job",
) -> list[PipelineTask]:
    """Enqueue event clustering task after embedding computation completes.

    Only enqueues when there were actually computed embeddings (computed > 0).

    Args:
        db: Async database session (caller must commit).
        embedding_result: Result dict from the embedding job.
        trigger_source: Identifier for the trigger origin.

    Returns:
        List of created PipelineTask instances (may be empty).
    """
    computed = embedding_result.get("computed", 0)
    if computed <= 0:
        return []

    payload = {"trigger_source": trigger_source, "embedding_computed_count": computed}
    tasks = []
    tasks.append(await enqueue_task(db, "event", payload=payload, priority=1))
    return tasks
