from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field

from app.models.base import BaseModel


class TestFeedbackComment(BaseModel, table=True):
    __tablename__ = "test_feedback_comment"

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    feedback_id: str = Field(
        sa_column=Column(String, ForeignKey("test_feedback.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    text: str = Field(
        sa_column=Column(Text, nullable=False)
    )
