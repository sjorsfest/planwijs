from typing import List, Optional

from pydantic import field_validator
from sqlalchemy import CheckConstraint, Column, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.constants import DEFAULT_LESSON_DURATION_MINUTES
from app.models.base import BaseModel
from app.models.enums import Level, SchoolType


def _coerce_level(item: object) -> Level:
    if isinstance(item, Level):
        return item
    if isinstance(item, str):
        try:
            return Level(item)
        except ValueError:
            return Level.UNKNOWN
    return Level.UNKNOWN


def _coerce_levels(values: object) -> list[Level]:
    if not isinstance(values, list):
        return []
    return [_coerce_level(item) for item in values]


class SchoolConfig(BaseModel, table=True):
    __tablename__ = "school_config"
    __table_args__ = (
        CheckConstraint(
            "(organization_id IS NOT NULL AND user_id IS NULL) OR "
            "(organization_id IS NULL AND user_id IS NOT NULL)",
            name="ck_school_config_exactly_one_owner",
        ),
    )

    organization_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String,
            ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )
    user_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String,
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )
    default_lesson_duration_minutes: int = Field(default=DEFAULT_LESSON_DURATION_MINUTES, ge=1)
    levels: List[Level] = Field(
        default_factory=list,
        sa_column=Column("levels", JSONB, nullable=False, server_default="[]"),
    )
    school_type: Optional[SchoolType] = Field(
        default=None,
        sa_column=Column(SAEnum(SchoolType, name="school_type", create_type=False), nullable=True),
    )
    context_notes: Optional[str] = Field(
        default=None,
        description="Vrije tekst met achtergrondinformatie over de school, wordt meegegeven als context aan de AI-agent.",
    )

    @field_validator("levels", mode="before")
    @classmethod
    def coerce_levels(cls, v: object) -> object:
        if isinstance(v, list):
            return _coerce_levels(v)
        return v
