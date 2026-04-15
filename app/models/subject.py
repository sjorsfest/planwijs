from typing import TYPE_CHECKING

from sqlalchemy import Column, Enum as SAEnum
from sqlmodel import Field, Relationship

from app.models.base import BaseModel
from app.models.enums import SubjectCategory

if TYPE_CHECKING:
    from app.models.book import Book


class Subject(BaseModel, table=True):
    __tablename__ = "subjects"  # type: ignore[assignment]

    slug: str = Field(unique=True, index=True)
    name: str = Field(unique=True)
    category: SubjectCategory = Field(
        sa_column=Column(SAEnum(SubjectCategory, name="subject_category", create_type=False), nullable=False),
    )

    books: list["Book"] = Relationship(back_populates="subject_ref")
