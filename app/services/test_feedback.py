import logging

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.exceptions import NotFoundError
from app.models.enums import TestFeedbackType
from app.models.test_feedback import TestFeedback
from app.models.test_feedback_comment import TestFeedbackComment
from app.models.test_feedback_vote import TestFeedbackVote
from app.models.user import User

logger = logging.getLogger(__name__)


# ── Feedback CRUD ────────────────────────────────────────────────────────────


async def create_feedback(
    session: AsyncSession,
    user: User,
    route: str,
    name: str,
    description: str,
    feedback_type: TestFeedbackType,
) -> TestFeedback:
    fb = TestFeedback(
        user_id=user.id,
        route=route,
        name=name,
        description=description,
        type=feedback_type,
    )
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    logger.info("Created test feedback id=%s by user=%s", fb.id, user.id)
    return fb


async def list_feedback(session: AsyncSession) -> list[TestFeedback]:
    result = await session.execute(
        select(TestFeedback).order_by(TestFeedback.created_at.desc())  # type: ignore[attr-defined]
    )
    return list(result.scalars().all())


async def get_feedback(session: AsyncSession, feedback_id: str) -> TestFeedback:
    fb = await session.get(TestFeedback, feedback_id)
    if fb is None:
        raise NotFoundError("Feedback not found")
    return fb


async def delete_feedback(session: AsyncSession, feedback_id: str, user: User) -> None:
    fb = await get_feedback(session, feedback_id)
    if fb.user_id != user.id:
        raise NotFoundError("Feedback not found")
    await session.delete(fb)
    await session.commit()
    logger.info("Deleted test feedback id=%s by user=%s", feedback_id, user.id)


# ── Votes ────────────────────────────────────────────────────────────────────


async def toggle_vote(session: AsyncSession, feedback_id: str, user: User) -> bool:
    """Toggle vote on feedback. Returns True if voted, False if unvoted."""
    await get_feedback(session, feedback_id)  # ensure exists

    result = await session.execute(
        select(TestFeedbackVote).where(
            TestFeedbackVote.user_id == user.id,
            TestFeedbackVote.feedback_id == feedback_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        await session.delete(existing)
        await session.commit()
        return False

    vote = TestFeedbackVote(user_id=user.id, feedback_id=feedback_id)
    session.add(vote)
    await session.commit()
    return True


async def get_vote_count(session: AsyncSession, feedback_id: str) -> int:
    result = await session.execute(
        select(func.count()).where(TestFeedbackVote.feedback_id == feedback_id)
    )
    return result.scalar_one()


async def has_user_voted(session: AsyncSession, feedback_id: str, user_id: str) -> bool:
    result = await session.execute(
        select(TestFeedbackVote).where(
            TestFeedbackVote.user_id == user_id,
            TestFeedbackVote.feedback_id == feedback_id,
        )
    )
    return result.scalar_one_or_none() is not None


# ── Comments ─────────────────────────────────────────────────────────────────


async def add_comment(
    session: AsyncSession, feedback_id: str, user: User, text: str
) -> TestFeedbackComment:
    await get_feedback(session, feedback_id)  # ensure exists
    comment = TestFeedbackComment(
        user_id=user.id, feedback_id=feedback_id, text=text
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def list_comments(
    session: AsyncSession, feedback_id: str
) -> list[TestFeedbackComment]:
    result = await session.execute(
        select(TestFeedbackComment)
        .where(TestFeedbackComment.feedback_id == feedback_id)
        .order_by(TestFeedbackComment.created_at.asc())  # type: ignore[attr-defined]
    )
    return list(result.scalars().all())


async def delete_comment(
    session: AsyncSession, comment_id: str, user: User
) -> None:
    comment = await session.get(TestFeedbackComment, comment_id)
    if comment is None or comment.user_id != user.id:
        raise NotFoundError("Comment not found")
    await session.delete(comment)
    await session.commit()
