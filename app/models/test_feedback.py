from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import TestFeedbackType


class TestFeedback(BaseModel, table=True):
    __tablename__ = "test_feedback"  # type: ignore[assignment]

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    route: str = Field(
        sa_column=Column(String, nullable=False)
    )
    name: str = Field(
        sa_column=Column(String, nullable=False)
    )
    description: str = Field(
        sa_column=Column(Text, nullable=False)
    )
    type: TestFeedbackType = Field(
        sa_column=Column(
            SAEnum(TestFeedbackType, name="test_feedback_type", create_type=False),
            nullable=False,
        ),
    )
