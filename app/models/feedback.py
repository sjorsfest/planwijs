from typing import Optional

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import FeedbackTargetType


class Feedback(BaseModel, table=True):
    __tablename__ = "feedback"  # type: ignore[assignment]

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    target_type: FeedbackTargetType = Field(
        sa_column=Column(
            SAEnum(FeedbackTargetType, name="feedback_target_type", create_type=False),
            nullable=False,
        ),
    )
    target_id: str = Field(
        sa_column=Column(String, nullable=False, index=True)
    )
    field_name: str = Field(
        sa_column=Column(String, nullable=False)
    )
    original_text: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    feedback_text: str = Field(
        sa_column=Column(Text, nullable=False)
    )
    organization_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("organization.id", ondelete="SET NULL"), nullable=True, index=True),
    )
