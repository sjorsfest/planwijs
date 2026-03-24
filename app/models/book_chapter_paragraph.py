from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class BookChapterParagraph(BaseModel, table=True):
    __tablename__ = "book_chapter_paragraph"

    index: int
    title: str
    synopsis: Optional[str] = None
    chapter_id: str = Field(foreign_key="book_chapter.id")
