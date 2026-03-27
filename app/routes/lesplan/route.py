import asyncio
import logging
import traceback
from collections.abc import AsyncGenerator
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.agents.lesplan_agent import GeneratedLesplanOverview, LessonOutlineItem, stream_overview, stream_revision
from app.database import SessionLocal, get_session, run_read_with_retry
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.classroom import Class
from app.models.enums import LesplanStatus
from app.models.lesplan import LesplanFeedbackMessage, LesplanRequest, LessonPreparationTodo
from app.models.user import User

from .types import (
    CreateLesplanRequest,
    CreateLessonPreparationTodoRequest,
    FeedbackRequest,
    LesplanResponse,
    LessonPreparationTodoResponse,
    UpdateLessonPreparationTodoRequest,
)
from .util import (
    _SSE_HEADERS,
    _build_context,
    _build_response,
    _fetch_feedback_history,
    _fetch_overview,
    _get_lesson_or_404,
    _get_preparation_todo_or_404,
    _normalize_learning_goals,
    _overview_payload_from_row,
    _persist_overview,
    _run_lessons_generation,
    _sse,
    _todo_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lesplan", tags=["lesplan"])


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
                    learning_goals=_normalize_learning_goals(overview.learning_goals),
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


@router.get("/lessons/{lesson_id}/preparation-todos", response_model=list[LessonPreparationTodoResponse])
async def list_lesson_preparation_todos(lesson_id: str) -> list[LessonPreparationTodoResponse]:
    async def operation(session: AsyncSession) -> list[LessonPreparationTodoResponse]:
        await _get_lesson_or_404(session, lesson_id)
        result = await session.execute(
            select(LessonPreparationTodo)
            .where(LessonPreparationTodo.lesson_plan_id == lesson_id)
            .order_by(LessonPreparationTodo.created_at.asc())  # type: ignore[union-attr]
        )
        return [_todo_response(todo) for todo in result.scalars().all()]

    return await run_read_with_retry(operation)


@router.get("/preparation-todos/{todo_id}", response_model=LessonPreparationTodoResponse)
async def get_lesson_preparation_todo(todo_id: str) -> LessonPreparationTodoResponse:
    async def operation(session: AsyncSession) -> LessonPreparationTodoResponse:
        todo = await _get_preparation_todo_or_404(session, todo_id)
        return _todo_response(todo)

    return await run_read_with_retry(operation)


@router.post("/lessons/{lesson_id}/preparation-todos", response_model=LessonPreparationTodoResponse, status_code=201)
async def create_lesson_preparation_todo(
    lesson_id: str,
    data: CreateLessonPreparationTodoRequest,
    session: AsyncSession = Depends(get_session),
) -> LessonPreparationTodoResponse:
    await _get_lesson_or_404(session, lesson_id)
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
    session: AsyncSession = Depends(get_session),
) -> LessonPreparationTodoResponse:
    todo = await _get_preparation_todo_or_404(session, todo_id)
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
    session: AsyncSession = Depends(get_session),
) -> None:
    todo = await _get_preparation_todo_or_404(session, todo_id)
    await session.delete(todo)
    await session.commit()
    logger.info("Deleted preparation todo %s", todo_id)


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
