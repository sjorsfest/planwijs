from typing import List, Optional

from pydantic import field_validator
from sqlalchemy import Column, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import Level, SchoolYear, Subject


class Book(BaseModel, table=True):
    book_id: Optional[int] = None
    slug: str = Field(index=True)
    title: str
    subject: Subject = Field(
        default=Subject.UNKNOWN,
        sa_column=Column(SAEnum(Subject, name="subject", create_type=False), nullable=False),
    )
    method_id: Optional[str] = Field(default=None, foreign_key="method.id")
    edition: Optional[str] = None
    school_years: List[SchoolYear] = Field(
        default_factory=list,
        sa_column=Column("school_years", JSONB, nullable=False, server_default="[]"),
    )
    levels: List[Level] = Field(
        default_factory=list,
        sa_column=Column("levels", JSONB, nullable=False, server_default="[]"),
    )
    cover_url: Optional[str] = None
    url: str = Field(unique=True)

    @field_validator("school_years", mode="before")
    @classmethod
    def coerce_school_years(cls, v: object) -> object:
        if isinstance(v, list):
            return [SchoolYear(item) if isinstance(item, str) else item for item in v]
        return v

    @field_validator("levels", mode="before")
    @classmethod
    def coerce_levels(cls, v: object) -> object:
        if isinstance(v, list):
            return [Level(item) if isinstance(item, str) else item for item in v]
        return v
