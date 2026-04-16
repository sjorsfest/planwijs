from typing import Optional

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field

from app.models.base import BaseModel


class BookChapterParagraph(BaseModel, table=True):
    __tablename__ = "book_chapter_paragraph"

    index: int
    title: str
    synopsis: Optional[str] = None
    chapter_id: str = Field(
        sa_column=Column(String, ForeignKey("book_chapter.id", ondelete="CASCADE"), nullable=False, index=True)
    )
