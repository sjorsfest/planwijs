import asyncio
import json
import logging
import traceback
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.agents.lesplan_agent import (
    GeneratedLesplanOverview,
    LesplanContext,
    LessonOutlineItem,
    generate_lessons,
    stream_overview,
    stream_revision,
)
from app.database import SessionLocal, get_session, run_read_with_retry
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.classroom import Class
from app.models.enums import LesplanStatus
from app.models.lesplan import LesplanFeedbackMessage, LesplanOverview, LesplanRequest, LessonPlan
from app.models.method import Method
from app.models.subject import Subject as SubjectModel
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lesplan", tags=["lesplan"])


class CreateLesplanRequest(BaseModel):
    user_id: str
    class_id: str
    book_id: str
    selected_paragraph_ids: list[str] = Field(min_length=1)
    num_lessons: int = Field(ge=1)
    lesson_duration_minutes: int = Field(ge=1)


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=1)


class FeedbackMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class TimeSectionResponse(BaseModel):
    start_min: int
    end_min: int
    activity: str
    description: str
    activity_type: str


class LessonPlanResponse(BaseModel):
    id: str
    lesson_number: int
    title: str
    learning_objectives: list[str]
    time_sections: list[TimeSectionResponse]
    required_materials: list[str]
    covered_paragraph_ids: list[str]
    teacher_notes: str
    created_at: datetime


class LessonOutlineItemResponse(BaseModel):
    lesson_number: int
    subject_focus: str
    description: str
    builds_on: str


class LesplanOverviewResponse(BaseModel):
    id: str
    title: str
    learning_goals: str
    key_knowledge: list[str]
    recommended_approach: str
    learning_progression: str
    lesson_outline: list[LessonOutlineItemResponse]
    didactic_approach: str
    lessons: list[LessonPlanResponse]


class LesplanResponse(BaseModel):
    id: str
    user_id: str
    class_id: str
    book_id: str
    selected_paragraph_ids: list[str]
    num_lessons: int
    lesson_duration_minutes: int
    status: LesplanStatus
    created_at: datetime
    updated_at: datetime
    overview: Optional[LesplanOverviewResponse]
    feedback_messages: list[FeedbackMessageResponse]


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


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

    return LesplanOverviewResponse(
        id=overview.id,
        title=overview.title,
        learning_goals=overview.learning_goals,
        key_knowledge=overview.key_knowledge,
        recommended_approach=overview.recommended_approach,
        learning_progression=overview.learning_progression,
        lesson_outline=[LessonOutlineItemResponse(**item) for item in overview.lesson_outline if isinstance(item, dict)],
        didactic_approach=overview.didactic_approach,
        lessons=[
            LessonPlanResponse(
                id=lesson.id,
                lesson_number=lesson.lesson_number,
                title=lesson.title,
                learning_objectives=lesson.learning_objectives,
                time_sections=[TimeSectionResponse(**item) for item in lesson.time_sections if isinstance(item, dict)],
                required_materials=lesson.required_materials,
                covered_paragraph_ids=lesson.covered_paragraph_ids,
                teacher_notes=lesson.teacher_notes,
                created_at=lesson.created_at,
            )
            for lesson in lessons
        ],
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
            learning_goals=data["learning_goals"],
            key_knowledge=data["key_knowledge"],
            recommended_approach=data["recommended_approach"],
            learning_progression=data["learning_progression"],
            lesson_outline=data["lesson_outline"],
            didactic_approach=data["didactic_approach"],
        )
        session.add(overview)
    else:
        overview.title = data["title"]
        overview.learning_goals = data["learning_goals"]
        overview.key_knowledge = data["key_knowledge"]
        overview.recommended_approach = data["recommended_approach"]
        overview.learning_progression = data["learning_progression"]
        overview.lesson_outline = data["lesson_outline"]
        overview.didactic_approach = data["didactic_approach"]
    return overview


def _overview_payload_from_row(overview: LesplanOverview) -> dict[str, Any]:
    return {
        "title": overview.title,
        "learning_goals": overview.learning_goals,
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
                learning_goals=overview.learning_goals,
                key_knowledge=overview.key_knowledge,
                recommended_approach=overview.recommended_approach,
                learning_progression=overview.learning_progression,
                lesson_outline=[LessonOutlineItem(**item) for item in overview.lesson_outline if isinstance(item, dict)],
                didactic_approach=overview.didactic_approach,
            )
            generated_lessons = await generate_lessons(ctx, approved_overview)

            for lesson in generated_lessons:
                covered_ids = [
                    req.selected_paragraph_ids[idx]
                    for idx in lesson.covered_paragraph_indices
                    if 0 <= idx < len(req.selected_paragraph_ids)
                ]
                session.add(
                    LessonPlan(
                        overview_id=overview.id,
                        lesson_number=lesson.lesson_number,
                        title=lesson.title,
                        learning_objectives=lesson.learning_objectives,
                        time_sections=[section.model_dump(mode="json") for section in lesson.time_sections],
                        required_materials=lesson.required_materials,
                        covered_paragraph_ids=covered_ids,
                        teacher_notes=lesson.teacher_notes,
                    )
                )

            req.status = LesplanStatus.COMPLETED
            await session.commit()
            logger.info("Lesson generation completed for request %s", request_id)
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


@router.post("/", response_model=LesplanResponse, status_code=201)
async def create_lesplan(
    data: CreateLesplanRequest,
    session: AsyncSession = Depends(get_session),
) -> LesplanResponse:
    if await session.get(User, data.user_id) is None:
        raise HTTPException(status_code=422, detail="Invalid user_id")
    if await session.get(Class, data.class_id) is None:
        raise HTTPException(status_code=422, detail="Invalid class_id")
    if await session.get(Book, data.book_id) is None:
        raise HTTPException(status_code=422, detail="Invalid book_id")

    chapter_ids = select(BookChapter.id).where(BookChapter.book_id == data.book_id)
    paragraph_results = await session.execute(
        select(BookChapterParagraph.id)
        .where(BookChapterParagraph.chapter_id.in_(chapter_ids))  # type: ignore[union-attr]
        .where(BookChapterParagraph.id.in_(data.selected_paragraph_ids))  # type: ignore[union-attr]
    )
    found_ids = set(paragraph_results.scalars().all())
    missing = [paragraph_id for paragraph_id in data.selected_paragraph_ids if paragraph_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Paragraph IDs do not belong to this book or do not exist: {missing}",
        )

    req = LesplanRequest(
        user_id=data.user_id,
        class_id=data.class_id,
        book_id=data.book_id,
        selected_paragraph_ids=data.selected_paragraph_ids,
        num_lessons=data.num_lessons,
        lesson_duration_minutes=data.lesson_duration_minutes,
        status=LesplanStatus.PENDING,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    logger.info("Created lesplan request %s", req.id)
    return await _build_response(session, req)


@router.post("/{request_id}/feedback", response_model=LesplanResponse)
async def submit_feedback(
    request_id: str,
    data: FeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> LesplanResponse:
    req = await session.get(LesplanRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Lesplan not found")
    if req.status != LesplanStatus.OVERVIEW_READY:
        raise HTTPException(
            status_code=409,
            detail=f"Feedback can only be given when the overview is ready (current status: {req.status.value})",
        )

    session.add(
        LesplanFeedbackMessage(
            request_id=request_id,
            role="teacher",
            content=data.message,
        )
    )
    req.status = LesplanStatus.REVISING_OVERVIEW
    await session.commit()
    await session.refresh(req)

    logger.info("Feedback received for lesplan %s", request_id)
    return await _build_response(session, req)


@router.post("/{request_id}/approve", response_model=LesplanResponse)
async def approve_lesplan(
    request_id: str,
    session: AsyncSession = Depends(get_session),
) -> LesplanResponse:
    req = await session.get(LesplanRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Lesplan not found")
    if req.status != LesplanStatus.OVERVIEW_READY:
        raise HTTPException(
            status_code=409,
            detail=f"Lesplan is not awaiting approval (current status: {req.status.value})",
        )

    req.status = LesplanStatus.GENERATING_LESSONS
    await session.commit()
    await session.refresh(req)

    asyncio.create_task(_run_lessons_generation(req.id))
    logger.info("Lesplan %s approved, lesson generation started", req.id)
    return await _build_response(session, req)


@router.get("/{request_id}/stream-overview")
async def stream_overview_endpoint(request_id: str) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is None:
                    yield _sse("error", {"message": "Lesplan not found"})
                    return

                existing_overview = await _fetch_overview(session, request_id)
                if req.status == LesplanStatus.OVERVIEW_READY and existing_overview is not None:
                    yield _sse(
                        "done",
                        {
                            "status": req.status.value,
                            "overview": _overview_payload_from_row(existing_overview),
                        },
                    )
                    return

                if req.status != LesplanStatus.PENDING:
                    yield _sse("error", {"message": f"Cannot stream overview from status {req.status.value}"})
                    return

                req.status = LesplanStatus.GENERATING_OVERVIEW
                await session.commit()
                ctx = await _build_context(session, req)

            final_payload: dict[str, Any] | None = None
            yield _sse("status", {"status": LesplanStatus.GENERATING_OVERVIEW.value})
            async for partial_payload, is_final in stream_overview(ctx):
                if is_final:
                    final_payload = partial_payload
                    continue
                yield _sse("partial", partial_payload)

            if final_payload is None:
                raise RuntimeError("Overview stream finished without a final payload")

            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is None:
                    return
                overview = await _persist_overview(session, request_id, final_payload)
                req.status = LesplanStatus.OVERVIEW_READY
                await session.commit()
                yield _sse(
                    "done",
                    {
                        "status": req.status.value,
                        "overview": _overview_payload_from_row(overview),
                    },
                )
        except asyncio.CancelledError:
            try:
                async with SessionLocal() as session:
                    req = await session.get(LesplanRequest, request_id)
                    if req is not None and req.status == LesplanStatus.GENERATING_OVERVIEW:
                        req.status = LesplanStatus.PENDING
                        await session.commit()
            except Exception:
                logger.error("Failed to reset lesplan %s after overview stream disconnect", request_id)
            raise
        except Exception:
            logger.error("Overview stream failed for %s:\n%s", request_id, traceback.format_exc())
            try:
                async with SessionLocal() as session:
                    req = await session.get(LesplanRequest, request_id)
                    if req is not None:
                        req.status = LesplanStatus.FAILED
                        await session.commit()
            except Exception:
                logger.error("Failed to mark lesplan %s as FAILED after overview stream error", request_id)
            yield _sse("error", {"message": "Overview generation failed"})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/{request_id}/stream-revision")
async def stream_revision_endpoint(request_id: str) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is None:
                    yield _sse("error", {"message": "Lesplan not found"})
                    return

                overview = await _fetch_overview(session, request_id)
                if overview is None:
                    yield _sse("error", {"message": "Overview not found"})
                    return

                if req.status == LesplanStatus.OVERVIEW_READY:
                    yield _sse(
                        "done",
                        {
                            "status": req.status.value,
                            "overview": _overview_payload_from_row(overview),
                        },
                    )
                    return

                if req.status != LesplanStatus.REVISING_OVERVIEW:
                    yield _sse("error", {"message": f"Cannot stream revision from status {req.status.value}"})
                    return

                current_overview = GeneratedLesplanOverview(
                    title=overview.title,
                    learning_goals=overview.learning_goals,
                    key_knowledge=overview.key_knowledge,
                    recommended_approach=overview.recommended_approach,
                    learning_progression=overview.learning_progression,
                    lesson_outline=[LessonOutlineItem(**item) for item in overview.lesson_outline if isinstance(item, dict)],
                    didactic_approach=overview.didactic_approach,
                )
                history = await _fetch_feedback_history(session, request_id)
                ctx = await _build_context(session, req)

            final_payload: dict[str, Any] | None = None
            yield _sse("status", {"status": LesplanStatus.REVISING_OVERVIEW.value})
            async for partial_payload, is_final in stream_revision(ctx, current_overview, history):
                if is_final:
                    final_payload = partial_payload
                    continue
                yield _sse("partial", partial_payload)

            if final_payload is None:
                raise RuntimeError("Revision stream finished without a final payload")

            revised_overview = final_payload["overview"]
            assistant_message = final_payload["assistant_message"]
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is None:
                    return
                overview = await _persist_overview(session, request_id, revised_overview)
                session.add(
                    LesplanFeedbackMessage(
                        request_id=request_id,
                        role="assistant",
                        content=assistant_message,
                    )
                )
                req.status = LesplanStatus.OVERVIEW_READY
                await session.commit()
                yield _sse(
                    "done",
                    {
                        "status": req.status.value,
                        "overview": _overview_payload_from_row(overview),
                        "assistant_message": assistant_message,
                    },
                )
        except asyncio.CancelledError:
            try:
                async with SessionLocal() as session:
                    req = await session.get(LesplanRequest, request_id)
                    if req is not None and req.status == LesplanStatus.REVISING_OVERVIEW:
                        req.status = LesplanStatus.OVERVIEW_READY
                        await session.commit()
            except Exception:
                logger.error("Failed to reset lesplan %s after revision stream disconnect", request_id)
            raise
        except Exception:
            logger.error("Revision stream failed for %s:\n%s", request_id, traceback.format_exc())
            try:
                async with SessionLocal() as session:
                    req = await session.get(LesplanRequest, request_id)
                    if req is not None:
                        req.status = LesplanStatus.FAILED
                        await session.commit()
            except Exception:
                logger.error("Failed to mark lesplan %s as FAILED after revision stream error", request_id)
            yield _sse("error", {"message": "Overview revision failed"})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/{request_id}", response_model=LesplanResponse)
async def get_lesplan(request_id: str) -> LesplanResponse:
    async def operation(session: AsyncSession) -> LesplanResponse:
        req = await session.get(LesplanRequest, request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Lesplan not found")
        return await _build_response(session, req)

    return await run_read_with_retry(operation)


@router.get("/", response_model=list[LesplanResponse])
async def list_lespannen(user_id: Optional[str] = Query(default=None)) -> list[LesplanResponse]:
    async def operation(session: AsyncSession) -> list[LesplanResponse]:
        stmt = select(LesplanRequest).order_by(LesplanRequest.created_at.desc())  # type: ignore[union-attr]
        if user_id is not None:
            stmt = stmt.where(LesplanRequest.user_id == user_id)
        result = await session.execute(stmt)
        return [await _build_response(session, req) for req in result.scalars().all()]

    return await run_read_with_retry(operation)
