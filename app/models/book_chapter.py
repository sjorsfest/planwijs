from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class BookChapter(BaseModel, table=True):
    __tablename__ = "book_chapter"

    index: int
    title: str
    book_id: str = Field(foreign_key="book.id")
