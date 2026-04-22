import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.auth import get_current_user
from app.database import run_read_with_retry
from app.models.lesson_objective import LessonObjective
from app.models.lesson_objective_goal import LessonObjectiveGoal
from app.models.lesplan import (
    LesplanOverview,
    LesplanRequest,
    LessonPlan,
    LessonPreparationTodo,
)
from app.models.user import User
from app.routes.calendar.types import (
    CalendarLessonItem,
    CalendarResponse,
    CalendarTodoItem,
)
from app.routes.lesplan.types import LessonObjectiveResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/", response_model=CalendarResponse)
async def get_calendar(
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(get_current_user),
) -> CalendarResponse:
    user_id = current_user.id

    async def operation(session: AsyncSession) -> CalendarResponse:
        # Fetch lessons with planned_date in range
        lesson_result = await session.execute(
            select(LessonPlan)
            .join(LesplanOverview, LessonPlan.overview_id == LesplanOverview.id)  # type: ignore[arg-type]
            .join(LesplanRequest, LesplanOverview.request_id == LesplanRequest.id)  # type: ignore[arg-type]
            .where(
                and_(
                    LesplanRequest.user_id == user_id,  # type: ignore[arg-type]
                    LessonPlan.planned_date >= start_date,  # type: ignore[operator]
                    LessonPlan.planned_date <= end_date,  # type: ignore[operator]
                )
            )
            .options(
                selectinload(LessonPlan.overview).selectinload(LesplanOverview.request)  # type: ignore[arg-type]
            )
        )
        lessons = lesson_result.scalars().all()

        # Fetch preparation todos with due_date in range
        todo_result = await session.execute(
            select(LessonPreparationTodo)
            .join(LessonPlan, LessonPreparationTodo.lesson_plan_id == LessonPlan.id)  # type: ignore[arg-type]
            .join(LesplanOverview, LessonPlan.overview_id == LesplanOverview.id)  # type: ignore[arg-type]
            .join(LesplanRequest, LesplanOverview.request_id == LesplanRequest.id)  # type: ignore[arg-type]
            .where(
                and_(
                    LesplanRequest.user_id == user_id,  # type: ignore[arg-type]
                    LessonPreparationTodo.due_date >= start_date,  # type: ignore[operator]
                    LessonPreparationTodo.due_date <= end_date,  # type: ignore[operator]
                )
            )
            .options(
                selectinload(LessonPreparationTodo.lesson_plan)  # type: ignore[arg-type]
                .selectinload(LessonPlan.overview)  # type: ignore[arg-type]
                .selectinload(LesplanOverview.request)  # type: ignore[arg-type]
            )
        )
        todos = todo_result.scalars().all()

        items: list[CalendarLessonItem | CalendarTodoItem] = []

        for lesson in lessons:
            overview = lesson.overview
            request = overview.request if overview else None

            # Load lesson objective records
            obj_result = await session.execute(
                select(LessonObjective)
                .where(LessonObjective.lesson_plan_id == lesson.id)
                .order_by(LessonObjective.position.asc())  # type: ignore[union-attr]
            )
            objectives = obj_result.scalars().all()
            obj_responses = []
            for obj in objectives:
                links_result = await session.execute(
                    select(LessonObjectiveGoal).where(
                        LessonObjectiveGoal.lesson_objective_id == obj.id
                    )
                )
                goal_ids = [link.learning_goal_id for link in links_result.scalars().all()]
                obj_responses.append(LessonObjectiveResponse(
                    id=obj.id, text=obj.text, position=obj.position, goal_ids=goal_ids,
                ))

            items.append(
                CalendarLessonItem(
                    id=lesson.id,
                    title=lesson.title,
                    planned_date=lesson.planned_date,  # type: ignore[arg-type]
                    lesson_number=lesson.lesson_number,
                    learning_objectives=lesson.learning_objectives,
                    lesson_objective_records=obj_responses,
                    lesplan_id=request.id if request else "",
                    lesplan_title=overview.title if overview else "",
                    created_at=lesson.created_at,
                )
            )

        for todo in todos:
            lesson_plan = todo.lesson_plan
            overview = lesson_plan.overview if lesson_plan else None
            request = overview.request if overview else None
            items.append(
                CalendarTodoItem(
                    id=todo.id,
                    title=todo.title,
                    description=todo.description,
                    due_date=todo.due_date,  # type: ignore[arg-type]
                    status=todo.status.value,
                    lesson_id=lesson_plan.id if lesson_plan else "",
                    lesson_title=lesson_plan.title if lesson_plan else "",
                    lesplan_id=request.id if request else "",
                    lesplan_title=overview.title if overview else "",
                    created_at=todo.created_at,
                )
            )

        items.sort(key=lambda item: item.planned_date if isinstance(item, CalendarLessonItem) else item.due_date)

        logger.debug(
            "Calendar for user=%s from %s to %s: %d lessons, %d todos",
            user_id, start_date, end_date, len(lessons), len(todos),
        )

        return CalendarResponse(
            start_date=start_date,
            end_date=end_date,
            items=items,
        )

    return await run_read_with_retry(operation)
