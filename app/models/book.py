from typing import TYPE_CHECKING, List, Optional

from pydantic import ConfigDict, computed_field, field_validator
from sqlalchemy import Column, ForeignKey, String, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import attributes
from sqlmodel import Field, Relationship

from app.config import settings
from app.models.base import BaseModel
from app.models.enums import Level, SchoolYear

if TYPE_CHECKING:
    from app.models.subject import Subject


def _coerce_school_year(item: object) -> SchoolYear:
    if isinstance(item, SchoolYear):
        return item
    if isinstance(item, str):
        try:
            return SchoolYear(item)
        except ValueError:
            return SchoolYear.UNKNOWN
    return SchoolYear.UNKNOWN


def _coerce_level(item: object) -> Level:
    if isinstance(item, Level):
        return item
    if isinstance(item, str):
        try:
            return Level(item)
        except ValueError:
            return Level.UNKNOWN
    return Level.UNKNOWN


def _coerce_school_years(values: object) -> list[SchoolYear]:
    if not isinstance(values, list):
        return []
    return [_coerce_school_year(item) for item in values]


def _coerce_levels(values: object) -> list[Level]:
    if not isinstance(values, list):
        return []
    return [_coerce_level(item) for item in values]


class Book(BaseModel, table=True):
    model_config = ConfigDict(validate_assignment=True)
    book_id: Optional[int] = None
    slug: str = Field(index=True)
    title: str
    subject_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    method_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("method.id", ondelete="SET NULL"), nullable=True),
    )
    edition: Optional[str] = None
    school_years: List[SchoolYear] = Field(
        default_factory=list,
        sa_column=Column("school_years", JSONB, nullable=False, server_default="[]"),
    )
    levels: List[Level] = Field(
        default_factory=list,
        sa_column=Column("levels", JSONB, nullable=False, server_default="[]"),
    )
    cover_path: Optional[str] = Field(default=None, sa_column=Column("cover_url", nullable=True))
    url: str = Field(unique=True)
    subject_ref: Optional["Subject"] = Relationship(back_populates="books")

    @computed_field
    @property
    def cover_url(self) -> Optional[str]:
        if self.cover_path and settings.cloudflare_r2_public_url:
            base = settings.cloudflare_r2_public_url.rstrip("/")
            path = self.cover_path.lstrip("/")
            return f"{base}/{path}"
        return self.cover_path

    @field_validator("school_years", mode="before")
    @classmethod
    def coerce_school_years(cls, v: object) -> object:
        if isinstance(v, list):
            return _coerce_school_years(v)
        return v

    @field_validator("levels", mode="before")
    @classmethod
    def coerce_levels(cls, v: object) -> object:
        if isinstance(v, list):
            return _coerce_levels(v)
        return v


@event.listens_for(Book, "load")
def _coerce_book_enums_on_load(target: Book, _context: object) -> None:
    # JSONB columns come back as list[str]; coerce to enum lists for Pydantic serialization.
    attributes.set_committed_value(target, "school_years", _coerce_school_years(target.school_years))
    attributes.set_committed_value(target, "levels", _coerce_levels(target.levels))


@event.listens_for(Book, "refresh")
def _coerce_book_enums_on_refresh(target: Book, _context: object, attrs: object) -> None:
    fields = set(attrs) if isinstance(attrs, (list, tuple, set)) else None
    if fields is None or "school_years" in fields:
        attributes.set_committed_value(target, "school_years", _coerce_school_years(target.school_years))
    if fields is None or "levels" in fields:
        attributes.set_committed_value(target, "levels", _coerce_levels(target.levels))
