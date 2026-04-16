from typing import Optional

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field

from app.models.base import BaseModel


class BookChapter(BaseModel, table=True):
    __tablename__ = "book_chapter"

    index: int
    title: str
    book_id: str = Field(
        sa_column=Column(String, ForeignKey("book.id", ondelete="CASCADE"), nullable=False, index=True)
    )
