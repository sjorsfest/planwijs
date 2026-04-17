import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.config import settings
from app.database import get_session, run_read_with_retry
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.visibility import get_user_org_id, visible_filter
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.classroom import Classroom
from app.models.file import File
from app.models.organization_membership import OrganizationMembership
from app.models.school_class import Class
from app.models.school_config import SchoolConfig
from app.models.enums import LesplanStatus
from app.models.lesplan import LesplanRequest
from app.models.user import User
from app.constants import DEFAULT_LESSON_DURATION_MINUTES
from app.redis import get_redis_pool
from app.task_state import TaskState, TaskStatus, TaskStep, set_task_state

from .types import (
    CreateLesplanRequest,
    FeedbackRequest,
    LesplanResponse,
    TaskSubmittedResponse,
)
from .util import (
    _build_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lesplan", tags=["lesplan"])


async def _get_user_lesplan_or_404(
    session: AsyncSession, request_id: str, user_id: str
) -> LesplanRequest:
    req = await session.get(LesplanRequest, request_id)
    if req is None or req.user_id != user_id:
        raise NotFoundError("Lesplan not found")
    return req


async def _enqueue_task(
    request: Request,
    task_type: str,
    resource_id: str,
    func_name: str,
    steps: list[str],
    extra_args: tuple[object, ...] = (),
) -> TaskSubmittedResponse:
    task_id = str(uuid4())
    now = datetime.now(timezone.utc)

    state = TaskState(
        task_id=task_id,
        task_type=task_type,
        resource_id=resource_id,
        status=TaskStatus.QUEUED,
        steps=[TaskStep(name=step) for step in steps],
        created_at=now,
        updated_at=now,
    )

    redis = await get_redis_pool()
    await set_task_state(redis, state, settings.redis_task_ttl_seconds)
    await request.app.state.arq_pool.enqueue_job(func_name, task_id, resource_id, *extra_args)

    return TaskSubmittedResponse(
        task_id=task_id,
        resource_id=resource_id,
        task_type=task_type,
        status="queued",
    )


@router.post("/", response_model=LesplanResponse, status_code=201)
async def create_lesplan(
    data: CreateLesplanRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LesplanResponse:
    classroom = await session.get(Class, data.class_id)
    if classroom is None or classroom.user_id != current_user.id:
        raise ValidationError("Invalid class_id")
    if await session.get(Book, data.book_id) is None:
        raise ValidationError("Invalid book_id")

    chapter_ids = select(BookChapter.id).where(BookChapter.book_id == data.book_id)
    paragraph_results = await session.execute(
        select(BookChapterParagraph.id)
        .where(BookChapterParagraph.chapter_id.in_(chapter_ids))  # type: ignore[union-attr]
        .where(BookChapterParagraph.id.in_(data.selected_paragraph_ids))  # type: ignore[union-attr]
    )
    found_ids = set(paragraph_results.scalars().all())
    missing = [paragraph_id for paragraph_id in data.selected_paragraph_ids if paragraph_id not in found_ids]
    if missing:
        raise ValidationError(
            f"Paragraph IDs do not belong to this book or do not exist: {missing}"
        )

    if data.classroom_id is not None:
        classroom_obj = await session.get(Classroom, data.classroom_id)
        if classroom_obj is None or classroom_obj.user_id != current_user.id:
            raise ValidationError("Invalid classroom_id")

    found_files: list[File] = []
    if data.file_ids:
        file_results = await session.execute(
            select(File)
            .where(File.id.in_(data.file_ids))  # type: ignore[union-attr]
            .where(File.user_id == current_user.id)
        )
        found_files = list(file_results.scalars().all())
        missing_file_ids = set(data.file_ids) - {f.id for f in found_files}
        if missing_file_ids:
            raise ValidationError(
                f"File IDs not found or not owned by user: {sorted(missing_file_ids)}"
            )

    # Resolve lesson_duration_minutes from SchoolConfig
    org_result = await session.execute(
        select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == current_user.id
        )
    )
    user_org_id = org_result.scalar_one_or_none()
    if user_org_id:
        cfg_result = await session.execute(
            select(SchoolConfig).where(SchoolConfig.organization_id == user_org_id)
        )
    else:
        cfg_result = await session.execute(
            select(SchoolConfig).where(SchoolConfig.user_id == current_user.id)
        )
    school_config = cfg_result.scalar_one_or_none()
    lesson_duration = (
        school_config.default_lesson_duration_minutes
        if school_config
        else DEFAULT_LESSON_DURATION_MINUTES
    )

    req = LesplanRequest(
        user_id=current_user.id,
        class_id=data.class_id,
        book_id=data.book_id,
        selected_paragraph_ids=data.selected_paragraph_ids,
        num_lessons=data.num_lessons,
        lesson_duration_minutes=lesson_duration,
        classroom_id=data.classroom_id,
        status=LesplanStatus.PENDING,
    )
    session.add(req)
    await session.flush()

    if data.file_ids:
        for file in found_files:
            file.lesplan_request_id = req.id

    await session.commit()
    await session.refresh(req)

    logger.info("Created lesplan request %s", req.id)
    return await _build_response(session, req)


@router.post("/{request_id}/generate-overview", response_model=TaskSubmittedResponse)
async def generate_overview_endpoint(
    request_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskSubmittedResponse:
    req = await _get_user_lesplan_or_404(session, request_id, current_user.id)
    if req.status != LesplanStatus.PENDING:
        raise ConflictError(
            f"Overview can only be generated from PENDING status (current: {req.status.value})"
        )

    req.status = LesplanStatus.GENERATING_OVERVIEW
    await session.commit()

    return await _enqueue_task(
        request,
        task_type="generate_overview",
        resource_id=request_id,
        func_name="generate_overview_task",
        steps=[
            "Loading context",
            "Generating identity",
            "Generating learning goals",
            "Generating sequence",
            "Generating teacher notes",
            "Persisting overview",
        ],
    )


@router.post("/{request_id}/feedback", response_model=TaskSubmittedResponse)
async def submit_feedback(
    request_id: str,
    data: FeedbackRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskSubmittedResponse:
    req = await _get_user_lesplan_or_404(session, request_id, current_user.id)
    if req.status != LesplanStatus.OVERVIEW_READY:
        raise ConflictError(
            f"Feedback can only be given when the overview is ready (current status: {req.status.value})"
        )

    req.status = LesplanStatus.REVISING_OVERVIEW
    await session.commit()

    feedback_items = [
        {
            "field_name": item.field_name,
            "specific_part": item.specific_part,
            "user_feedback": item.user_feedback,
        }
        for item in data.items
    ]

    return await _enqueue_task(
        request,
        task_type="apply_feedback",
        resource_id=request_id,
        func_name="apply_feedback_task",
        steps=[
            "Loading context",
            "Applying feedback",
            "Persisting changes",
        ],
        extra_args=(feedback_items,),
    )


@router.post("/{request_id}/approve", response_model=TaskSubmittedResponse)
async def approve_lesplan(
    request_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskSubmittedResponse:
    req = await _get_user_lesplan_or_404(session, request_id, current_user.id)
    if req.status != LesplanStatus.OVERVIEW_READY:
        raise ConflictError(
            f"Lesplan is not awaiting approval (current status: {req.status.value})"
        )

    req.status = LesplanStatus.GENERATING_LESSONS
    await session.commit()

    return await _enqueue_task(
        request,
        task_type="generate_lessons",
        resource_id=request_id,
        func_name="generate_lessons_task",
        steps=[
            "Loading context",
            "Generating lessons",
            "Generating preparation",
            "Persisting lessons",
        ],
    )


@router.get("/{request_id}", response_model=LesplanResponse)
async def get_lesplan(
    request_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LesplanResponse:
    user_id = current_user.id
    org_id = await get_user_org_id(session, user_id)

    async def operation(read_session: AsyncSession) -> LesplanResponse:
        stmt = select(LesplanRequest).where(
            LesplanRequest.id == request_id,
            visible_filter(LesplanRequest, user_id, org_id),
        )
        result = await read_session.execute(stmt)
        req = result.scalar_one_or_none()
        if req is None:
            raise NotFoundError("Lesplan not found")
        return await _build_response(read_session, req)

    return await run_read_with_retry(operation)


@router.get("/", response_model=list[LesplanResponse])
async def list_lespannen(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[LesplanResponse]:
    user_id = current_user.id
    org_id = await get_user_org_id(session, user_id)

    async def operation(read_session: AsyncSession) -> list[LesplanResponse]:
        stmt = (
            select(LesplanRequest)
            .where(visible_filter(LesplanRequest, user_id, org_id))
            .order_by(LesplanRequest.created_at.desc())  # type: ignore[union-attr]
        )
        result = await read_session.execute(stmt)
        return [await _build_response(read_session, req) for req in result.scalars().all()]

    return await run_read_with_retry(operation)
