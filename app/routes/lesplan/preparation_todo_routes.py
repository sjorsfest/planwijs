import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.database import get_session, run_read_with_retry
from app.models.lesplan import LesplanOverview, LesplanRequest, LessonPlan, LessonPreparationTodo
from app.models.user import User

from .types import (
    CreateLessonPreparationTodoRequest,
    LessonPlanResponse,
    LessonPreparationTodoResponse,
    UpdateLessonPlannedDateRequest,
    UpdateLessonPreparationTodoRequest,
)
from .util import (
    _get_lesson_or_404,
    _get_preparation_todo_or_404,
    _lesson_response,
    _todo_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lesplan", tags=["lesplan"])


async def _verify_lesson_ownership(session: AsyncSession, lesson_id: str, user_id: str) -> LessonPlan:
    lesson = await _get_lesson_or_404(session, lesson_id)
    overview = await session.get(LesplanOverview, lesson.overview_id)
    if overview is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    request = await session.get(LesplanRequest, overview.request_id)
    if request is None or request.user_id != user_id:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


async def _verify_todo_ownership(session: AsyncSession, todo_id: str, user_id: str) -> LessonPreparationTodo:
    todo = await _get_preparation_todo_or_404(session, todo_id)
    lesson = await session.get(LessonPlan, todo.lesson_plan_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Preparation todo not found")
    overview = await session.get(LesplanOverview, lesson.overview_id)
    if overview is None:
        raise HTTPException(status_code=404, detail="Preparation todo not found")
    request = await session.get(LesplanRequest, overview.request_id)
    if request is None or request.user_id != user_id:
        raise HTTPException(status_code=404, detail="Preparation todo not found")
    return todo


@router.patch("/lessons/{lesson_id}/planned-date", response_model=LessonPlanResponse)
async def update_lesson_planned_date(
    lesson_id: str,
    data: UpdateLessonPlannedDateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LessonPlanResponse:
    lesson = await _verify_lesson_ownership(session, lesson_id, current_user.id)
    old_planned_date = lesson.planned_date
    lesson.planned_date = data.planned_date

    # Update due_date on todos that were either unset or matched the old planned_date
    todos_result = await session.execute(
        select(LessonPreparationTodo).where(LessonPreparationTodo.lesson_plan_id == lesson_id)
    )
    for todo in todos_result.scalars().all():
        if todo.due_date is None or todo.due_date == old_planned_date:
            todo.due_date = data.planned_date

    await session.commit()
    await session.refresh(lesson)
    logger.info("Updated planned_date for lesson %s to %s", lesson_id, data.planned_date)
    return await _lesson_response(session, lesson)


@router.get("/lessons/{lesson_id}/preparation-todos", response_model=list[LessonPreparationTodoResponse])
async def list_lesson_preparation_todos(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
) -> list[LessonPreparationTodoResponse]:
    user_id = current_user.id

    async def operation(session: AsyncSession) -> list[LessonPreparationTodoResponse]:
        await _verify_lesson_ownership(session, lesson_id, user_id)
        result = await session.execute(
            select(LessonPreparationTodo)
            .where(LessonPreparationTodo.lesson_plan_id == lesson_id)
            .order_by(LessonPreparationTodo.created_at.asc())  # type: ignore[union-attr]
        )
        return [_todo_response(todo) for todo in result.scalars().all()]

    return await run_read_with_retry(operation)


@router.get("/preparation-todos/{todo_id}", response_model=LessonPreparationTodoResponse)
async def get_lesson_preparation_todo(
    todo_id: str,
    current_user: User = Depends(get_current_user),
) -> LessonPreparationTodoResponse:
    user_id = current_user.id

    async def operation(session: AsyncSession) -> LessonPreparationTodoResponse:
        todo = await _verify_todo_ownership(session, todo_id, user_id)
        return _todo_response(todo)

    return await run_read_with_retry(operation)


@router.post("/lessons/{lesson_id}/preparation-todos", response_model=LessonPreparationTodoResponse, status_code=201)
async def create_lesson_preparation_todo(
    lesson_id: str,
    data: CreateLessonPreparationTodoRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LessonPreparationTodoResponse:
    await _verify_lesson_ownership(session, lesson_id, current_user.id)
    todo = LessonPreparationTodo(
        lesson_plan_id=lesson_id,
        title=data.title,
        description=data.description,
        why=data.why,
        status=data.status,
        due_date=data.due_date,
    )
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    logger.info("Created preparation todo %s for lesson %s", todo.id, lesson_id)
    return _todo_response(todo)


@router.patch("/preparation-todos/{todo_id}", response_model=LessonPreparationTodoResponse)
async def update_lesson_preparation_todo(
    todo_id: str,
    data: UpdateLessonPreparationTodoRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LessonPreparationTodoResponse:
    todo = await _verify_todo_ownership(session, todo_id, current_user.id)
    update = data.model_dump(exclude_unset=True)
    if update:
        todo.sqlmodel_update(update)
        await session.commit()
        await session.refresh(todo)
        logger.info("Updated preparation todo %s with fields %s", todo_id, list(update.keys()))
    return _todo_response(todo)


@router.delete("/preparation-todos/{todo_id}", status_code=204)
async def delete_lesson_preparation_todo(
    todo_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    todo = await _verify_todo_ownership(session, todo_id, current_user.id)
    await session.delete(todo)
    await session.commit()
    logger.info("Deleted preparation todo %s", todo_id)
