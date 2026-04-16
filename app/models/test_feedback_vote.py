from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


class TestFeedbackVote(BaseModel, table=True):
    __tablename__ = "test_feedback_vote"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "feedback_id", name="uq_test_feedback_vote_user_feedback"),
    )

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    feedback_id: str = Field(
        sa_column=Column(String, ForeignKey("test_feedback.id", ondelete="CASCADE"), nullable=False, index=True)
    )
