from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from redis.asyncio import Redis


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStep(BaseModel):
    name: str
    status: TaskStatus = TaskStatus.QUEUED
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskState(BaseModel):
    task_id: str
    task_type: str
    resource_id: str
    status: TaskStatus = TaskStatus.QUEUED
    current_step: str | None = None
    steps: list[TaskStep] = Field(default_factory=list)
    progress_pct: int = 0
    error: str | None = None
    created_at: datetime
    updated_at: datetime


def _redis_key(task_id: str) -> str:
    return f"task:{task_id}"


async def set_task_state(redis: Redis, state: TaskState, ttl: int) -> None:
    key = _redis_key(state.task_id)
    state.updated_at = datetime.now(timezone.utc)
    await redis.set(key, state.model_dump_json(), ex=ttl)


async def get_task_state(redis: Redis, task_id: str) -> TaskState | None:
    key = _redis_key(task_id)
    data = await redis.get(key)
    if data is None:
        return None
    return TaskState.model_validate_json(data)


async def update_task_progress(
    redis: Redis,
    task_id: str,
    *,
    current_step: str | None = None,
    progress_pct: int | None = None,
    status: TaskStatus | None = None,
    step_name: str | None = None,
    step_status: TaskStatus | None = None,
    error: str | None = None,
    ttl: int | None = None,
) -> None:
    state = await get_task_state(redis, task_id)
    if state is None:
        return

    if status is not None:
        state.status = status
    if current_step is not None:
        state.current_step = current_step
    if progress_pct is not None:
        state.progress_pct = progress_pct
    if error is not None:
        state.error = error

    if step_name is not None:
        now = datetime.now(timezone.utc)
        found = False
        for step in state.steps:
            if step.name == step_name:
                if step_status is not None:
                    step.status = step_status
                if step_status == TaskStatus.RUNNING:
                    step.started_at = now
                if step_status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    step.completed_at = now
                found = True
                break
        if not found:
            state.steps.append(
                TaskStep(
                    name=step_name,
                    status=step_status or TaskStatus.RUNNING,
                    started_at=now,
                )
            )

    await set_task_state(redis, state, ttl or 3600)
