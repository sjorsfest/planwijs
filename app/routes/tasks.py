from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.exceptions import NotFoundError
from app.models.user import User
from app.redis import get_redis_pool
from app.task_state import TaskState, get_task_state

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskState)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> TaskState:
    redis = await get_redis_pool()
    state = await get_task_state(redis, task_id)
    if state is None:
        raise NotFoundError("Task not found or expired")
    return state
