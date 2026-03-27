import json
import logging
import traceback
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.agents.lesplan_agent import GeneratedLesplanOverview, LesplanContext, LessonOutlineItem, generate_lessons
from app.agents.preparation_agent import PreparationContext, generate_preparation_todos
from app.database import SessionLocal
from app.models.book import Book
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.classroom import Class
from app.models.enums import LesplanStatus
from app.models.lesplan import LesplanFeedbackMessage, LesplanOverview, LesplanRequest, LessonPlan, LessonPreparationTodo
from app.models.method import Method
from app.models.subject import Subject as SubjectModel

from .types import (
    FeedbackMessageResponse,
    LesplanOverviewResponse,
    LesplanResponse,
    LessonOutlineItemResponse,
    LessonPlanResponse,
    LessonPreparationTodoResponse,
    TimeSectionResponse,
)

logger = logging.getLogger(__name__)

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _todo_response(todo: LessonPreparationTodo) -> LessonPreparationTodoResponse:
    return LessonPreparationTodoResponse(
        id=todo.id,
        title=todo.title,
        description=todo.description,
        why=todo.why,
        status=todo.status.value,
        due_date=todo.due_date,
        created_at=todo.created_at,
    )


async def _get_lesson_or_404(session: AsyncSession, lesson_id: str) -> LessonPlan:
    lesson = await session.get(LessonPlan, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


async def _get_preparation_todo_or_404(session: AsyncSession, todo_id: str) -> LessonPreparationTodo:
    todo = await session.get(LessonPreparationTodo, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Preparation todo not found")
    return todo


def _normalize_learning_goals(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        lines = []
        for line in value.splitlines():
            line = line.strip()
            if line.startswith("- "):
                line = line[2:].strip()
            numbered_prefix, separator, remainder = line.partition(" ")
            if (
                separator
                and len(numbered_prefix) > 1
                and numbered_prefix[-1] in {".", ")"}
                and numbered_prefix[:-1].isdigit()
            ):
                line = remainder.strip()
            if line:
                lines.append(line)

        if lines:
            return lines
        return [text]

    if value is None:
        return []

    text = str(value).strip()
    return [text] if text else []


async def _build_context(session: AsyncSession, req: LesplanRequest) -> LesplanContext:
    classroom = await session.get(Class, req.class_id)
    book = await session.get(Book, req.book_id)
    if classroom is None or book is None:
        raise ValueError(f"Class {req.class_id} or Book {req.book_id} not found")

    method: Optional[Method] = None
    if book.method_id:
        method = await session.get(Method, book.method_id)

    subject_name = ""
    if book.subject_id:
        subject = await session.get(SubjectModel, book.subject_id)
        if subject is not None:
            subject_name = subject.name

    paragraph_results = await session.execute(
        select(BookChapterParagraph).where(
            BookChapterParagraph.id.in_(req.selected_paragraph_ids)  # type: ignore[union-attr]
        )
    )
    paragraphs_by_id = {p.id: p for p in paragraph_results.scalars().all()}
    ordered_paragraphs = [
        {
            "index": paragraphs_by_id[pid].index,
            "title": paragraphs_by_id[pid].title,
            "synopsis": paragraphs_by_id[pid].synopsis,
        }
        for pid in req.selected_paragraph_ids
        if pid in paragraphs_by_id
    ]

    if len(ordered_paragraphs) != len(req.selected_paragraph_ids):
        raise ValueError("Some selected paragraphs could not be loaded")

    return LesplanContext(
        book_title=book.title,
        book_subject=subject_name,
        method_name=method.title if method else "",
        paragraphs=ordered_paragraphs,
        level=classroom.level.value,
        school_year=classroom.school_year.value,
        class_size=classroom.size,
        difficulty=classroom.difficulty.value if classroom.difficulty else None,
        num_lessons=req.num_lessons,
        lesson_duration_minutes=req.lesson_duration_minutes,
    )


async def _fetch_feedback_history(session: AsyncSession, request_id: str) -> list[dict[str, str]]:
    result = await session.execute(
        select(LesplanFeedbackMessage)
        .where(LesplanFeedbackMessage.request_id == request_id)
        .order_by(LesplanFeedbackMessage.created_at.asc())  # type: ignore[union-attr]
    )
    return [{"role": msg.role, "content": msg.content} for msg in result.scalars().all()]


async def _fetch_feedback_responses(session: AsyncSession, request_id: str) -> list[FeedbackMessageResponse]:
    result = await session.execute(
        select(LesplanFeedbackMessage)
        .where(LesplanFeedbackMessage.request_id == request_id)
        .order_by(LesplanFeedbackMessage.created_at.asc())  # type: ignore[union-attr]
    )
    return [
        FeedbackMessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )
        for msg in result.scalars().all()
    ]


async def _fetch_overview(session: AsyncSession, request_id: str) -> Optional[LesplanOverview]:
    result = await session.execute(select(LesplanOverview).where(LesplanOverview.request_id == request_id))
    return result.scalars().first()


async def _fetch_overview_response(
    session: AsyncSession,
    request_id: str,
) -> Optional[LesplanOverviewResponse]:
    overview = await _fetch_overview(session, request_id)
    if overview is None:
        return None

    lessons_result = await session.execute(
        select(LessonPlan)
        .where(LessonPlan.overview_id == overview.id)
        .order_by(LessonPlan.lesson_number.asc())  # type: ignore[union-attr]
    )
    lessons = lessons_result.scalars().all()

    lesson_responses = []
    for lesson in lessons:
        todos_result = await session.execute(
            select(LessonPreparationTodo)
            .where(LessonPreparationTodo.lesson_plan_id == lesson.id)
            .order_by(LessonPreparationTodo.created_at.asc())  # type: ignore[union-attr]
        )
        todos = todos_result.scalars().all()
        lesson_responses.append(
            LessonPlanResponse(
                id=lesson.id,
                lesson_number=lesson.lesson_number,
                planned_date=lesson.planned_date,
                title=lesson.title,
                learning_objectives=lesson.learning_objectives,
                time_sections=[TimeSectionResponse(**item) for item in lesson.time_sections if isinstance(item, dict)],
                required_materials=lesson.required_materials,
                covered_paragraph_ids=lesson.covered_paragraph_ids,
                teacher_notes=lesson.teacher_notes,
                created_at=lesson.created_at,
                preparation_todos=[_todo_response(todo) for todo in todos],
            )
        )

    return LesplanOverviewResponse(
        id=overview.id,
        title=overview.title,
        learning_goals=_normalize_learning_goals(overview.learning_goals),
        key_knowledge=overview.key_knowledge,
        recommended_approach=overview.recommended_approach,
        learning_progression=overview.learning_progression,
        lesson_outline=[LessonOutlineItemResponse(**item) for item in overview.lesson_outline if isinstance(item, dict)],
        didactic_approach=overview.didactic_approach,
        lessons=lesson_responses,
    )


async def _build_response(session: AsyncSession, req: LesplanRequest) -> LesplanResponse:
    return LesplanResponse(
        id=req.id,
        user_id=req.user_id,
        class_id=req.class_id,
        book_id=req.book_id,
        selected_paragraph_ids=req.selected_paragraph_ids,
        num_lessons=req.num_lessons,
        lesson_duration_minutes=req.lesson_duration_minutes,
        status=req.status,
        created_at=req.created_at,
        updated_at=req.updated_at,
        overview=await _fetch_overview_response(session, req.id),
        feedback_messages=await _fetch_feedback_responses(session, req.id),
    )


async def _persist_overview(
    session: AsyncSession,
    request_id: str,
    data: dict[str, Any],
) -> LesplanOverview:
    overview = await _fetch_overview(session, request_id)
    if overview is None:
        overview = LesplanOverview(
            request_id=request_id,
            title=data["title"],
            learning_goals=_normalize_learning_goals(data["learning_goals"]),
            key_knowledge=data["key_knowledge"],
            recommended_approach=data["recommended_approach"],
            learning_progression=data["learning_progression"],
            lesson_outline=data["lesson_outline"],
            didactic_approach=data["didactic_approach"],
        )
        session.add(overview)
    else:
        overview.title = data["title"]
        overview.learning_goals = _normalize_learning_goals(data["learning_goals"])
        overview.key_knowledge = data["key_knowledge"]
        overview.recommended_approach = data["recommended_approach"]
        overview.learning_progression = data["learning_progression"]
        overview.lesson_outline = data["lesson_outline"]
        overview.didactic_approach = data["didactic_approach"]
    return overview


def _overview_payload_from_row(overview: LesplanOverview) -> dict[str, Any]:
    return {
        "title": overview.title,
        "learning_goals": _normalize_learning_goals(overview.learning_goals),
        "key_knowledge": overview.key_knowledge,
        "recommended_approach": overview.recommended_approach,
        "learning_progression": overview.learning_progression,
        "lesson_outline": overview.lesson_outline,
        "didactic_approach": overview.didactic_approach,
    }


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_lessons_generation(request_id: str) -> None:
    async with SessionLocal() as session:
        try:
            req = await session.get(LesplanRequest, request_id)
            if req is None:
                logger.error("LesplanRequest %s not found for lesson generation", request_id)
                return

            overview = await _fetch_overview(session, request_id)
            if overview is None:
                raise ValueError(f"No overview found for request {request_id}")

            ctx = await _build_context(session, req)
            approved_overview = GeneratedLesplanOverview(
                title=overview.title,
                learning_goals=_normalize_learning_goals(overview.learning_goals),
                key_knowledge=overview.key_knowledge,
                recommended_approach=overview.recommended_approach,
                learning_progression=overview.learning_progression,
                lesson_outline=[LessonOutlineItem(**item) for item in overview.lesson_outline if isinstance(item, dict)],
                didactic_approach=overview.didactic_approach,
            )
            generated_lessons = await generate_lessons(ctx, approved_overview)

            saved_lesson_plans: list[tuple[LessonPlan, Any]] = []
            for lesson in generated_lessons:
                covered_ids = [
                    req.selected_paragraph_ids[idx]
                    for idx in lesson.covered_paragraph_indices
                    if 0 <= idx < len(req.selected_paragraph_ids)
                ]
                lesson_plan = LessonPlan(
                    overview_id=overview.id,
                    lesson_number=lesson.lesson_number,
                    title=lesson.title,
                    learning_objectives=lesson.learning_objectives,
                    time_sections=[section.model_dump(mode="json") for section in lesson.time_sections],
                    required_materials=lesson.required_materials,
                    covered_paragraph_ids=covered_ids,
                    teacher_notes=lesson.teacher_notes,
                )
                session.add(lesson_plan)
                saved_lesson_plans.append((lesson_plan, lesson))

            req.status = LesplanStatus.COMPLETED
            await session.commit()
            logger.info("Lesson generation completed for request %s", request_id)

            for lesson_plan, generated_lesson in saved_lesson_plans:
                try:
                    prep_ctx = PreparationContext(
                        lesson_number=generated_lesson.lesson_number,
                        title=generated_lesson.title,
                        learning_objectives=generated_lesson.learning_objectives,
                        time_sections=[s.model_dump(mode="json") for s in generated_lesson.time_sections],
                        required_materials=generated_lesson.required_materials,
                        teacher_notes=generated_lesson.teacher_notes,
                    )
                    todos = await generate_preparation_todos(prep_ctx)
                    for todo in todos:
                        session.add(
                            LessonPreparationTodo(
                                lesson_plan_id=lesson_plan.id,
                                title=todo.title,
                                description=todo.description,
                                why=todo.why,
                            )
                        )
                except Exception:
                    logger.error(
                        "Preparation todo generation failed for lesson %s:\n%s",
                        lesson_plan.id,
                        traceback.format_exc(),
                    )
            await session.commit()
            logger.info("Preparation todos generated for request %s", request_id)
        except Exception:
            logger.error(
                "Lesson generation failed for request %s:\n%s",
                request_id,
                traceback.format_exc(),
            )
            try:
                req = await session.get(LesplanRequest, request_id)
                if req is not None:
                    req.status = LesplanStatus.FAILED
                    await session.commit()
            except Exception:
                logger.error("Failed to mark lesplan %s as FAILED", request_id)
