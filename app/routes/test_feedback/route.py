from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.enums import TestFeedbackType
from app.models.user import User
from app.services import test_feedback as svc

router = APIRouter(prefix="/test-feedback", tags=["test-feedback"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class FeedbackCreate(PydanticBaseModel):
    route: str
    name: str
    description: str
    type: TestFeedbackType


class FeedbackRead(PydanticBaseModel):
    id: str
    user_id: str
    user_name: str
    route: str
    name: str
    description: str
    type: TestFeedbackType
    vote_count: int
    has_voted: bool
    comment_count: int
    created_at: datetime


class CommentCreate(PydanticBaseModel):
    text: str


class CommentRead(PydanticBaseModel):
    id: str
    user_id: str
    user_name: str
    text: str
    created_at: datetime


class VoteResponse(PydanticBaseModel):
    voted: bool
    vote_count: int


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _enrich_feedback(
    session: AsyncSession, fb: object, user_id: str
) -> FeedbackRead:
    from app.models.test_feedback import TestFeedback

    assert isinstance(fb, TestFeedback)
    vote_count = await svc.get_vote_count(session, fb.id)
    has_voted = await svc.has_user_voted(session, fb.id, user_id)
    comments = await svc.list_comments(session, fb.id)

    user = await session.get(User, fb.user_id)
    user_name = user.name if user and user.name else "Unknown"

    return FeedbackRead(
        id=fb.id,
        user_id=fb.user_id,
        user_name=user_name,
        route=fb.route,
        name=fb.name,
        description=fb.description,
        type=fb.type,
        vote_count=vote_count,
        has_voted=has_voted,
        comment_count=len(comments),
        created_at=fb.created_at,
    )


# ── Feedback endpoints ───────────────────────────────────────────────────────


@router.post("/", response_model=FeedbackRead, status_code=201)
async def create_feedback(
    data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FeedbackRead:
    fb = await svc.create_feedback(
        session,
        user=current_user,
        route=data.route,
        name=data.name,
        description=data.description,
        feedback_type=data.type,
    )
    return await _enrich_feedback(session, fb, current_user.id)


@router.get("/", response_model=list[FeedbackRead])
async def list_feedback(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FeedbackRead]:
    items = await svc.list_feedback(session)
    return [await _enrich_feedback(session, fb, current_user.id) for fb in items]


@router.get("/{feedback_id}", response_model=FeedbackRead)
async def get_feedback(
    feedback_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FeedbackRead:
    fb = await svc.get_feedback(session, feedback_id)
    return await _enrich_feedback(session, fb, current_user.id)


@router.delete("/{feedback_id}", status_code=204)
async def delete_feedback(
    feedback_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await svc.delete_feedback(session, feedback_id, current_user)


# ── Vote endpoints ───────────────────────────────────────────────────────────


@router.post("/{feedback_id}/vote", response_model=VoteResponse)
async def toggle_vote(
    feedback_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> VoteResponse:
    voted = await svc.toggle_vote(session, feedback_id, current_user)
    vote_count = await svc.get_vote_count(session, feedback_id)
    return VoteResponse(voted=voted, vote_count=vote_count)


# ── Comment endpoints ────────────────────────────────────────────────────────


@router.get("/{feedback_id}/comments", response_model=list[CommentRead])
async def list_comments(
    feedback_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CommentRead]:
    comments = await svc.list_comments(session, feedback_id)
    reads: list[CommentRead] = []
    for c in comments:
        user = await session.get(User, c.user_id)
        user_name = user.name if user and user.name else "Unknown"
        reads.append(
            CommentRead(
                id=c.id,
                user_id=c.user_id,
                user_name=user_name,
                text=c.text,
                created_at=c.created_at,
            )
        )
    return reads


@router.post("/{feedback_id}/comments", response_model=CommentRead, status_code=201)
async def add_comment(
    feedback_id: str,
    data: CommentCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentRead:
    comment = await svc.add_comment(session, feedback_id, current_user, data.text)
    return CommentRead(
        id=comment.id,
        user_id=comment.user_id,
        user_name=current_user.name or "Unknown",
        text=comment.text,
        created_at=comment.created_at,
    )


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await svc.delete_comment(session, comment_id, current_user)
