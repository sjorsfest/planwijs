from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


class UserSubject(BaseModel, table=True):
    __tablename__ = "user_subject"
    __table_args__ = (
        UniqueConstraint("user_id", "subject_id", name="uq_user_subject"),
    )

    user_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    subject_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
