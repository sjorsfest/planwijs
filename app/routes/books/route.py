import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session, run_read_with_retry
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.enums import Level, SchoolYear
from app.models.subject import Subject as SubjectModel

from .types import BookDetailResponse, ChapterResponse, ParagraphResponse
from .util import _subject_exists

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


@router.get("/", response_model=list[Book])
async def list_books(
    method_id: Optional[str] = Query(default=None),
    subject_id: Optional[str] = Query(default=None),
    level: Optional[Level] = Query(default=None),
    school_year: Optional[SchoolYear] = Query(default=None),
):
    async def operation(session: AsyncSession) -> list[Book]:
        stmt = select(Book).order_by(Book.title)
        if method_id is not None:
            stmt = stmt.where(Book.method_id == method_id)
        if subject_id is not None:
            stmt = stmt.where(Book.subject_id == subject_id)
        if level is not None:
            stmt = stmt.where(Book.levels.contains([level.value]))  # type: ignore[union-attr]
        if school_year is not None:
            stmt = stmt.where(Book.school_years.contains([school_year.value]))  # type: ignore[union-attr]
        result = await session.execute(stmt)
        return list(result.scalars().all())

    return await run_read_with_retry(operation)


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(book_id: str):
    async def operation(session: AsyncSession) -> BookDetailResponse:
        book = await session.get(Book, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        subject = await session.get(SubjectModel, book.subject_id) if book.subject_id else None

        chapters_result = await session.execute(
            select(BookChapter).where(BookChapter.book_id == book_id).order_by(BookChapter.index)  # type: ignore[arg-type]
        )
        chapters = chapters_result.scalars().all()

        chapter_ids = [c.id for c in chapters]
        paragraphs_result = await session.execute(
            select(BookChapterParagraph)
            .where(BookChapterParagraph.chapter_id.in_(chapter_ids))  # type: ignore[union-attr]
            .order_by(BookChapterParagraph.index)  # type: ignore[arg-type]
        )
        paragraphs = paragraphs_result.scalars().all()

        paragraphs_by_chapter: dict[str, list[BookChapterParagraph]] = {}
        for p in paragraphs:
            paragraphs_by_chapter.setdefault(p.chapter_id, []).append(p)

        return BookDetailResponse(
            id=book.id,
            slug=book.slug,
            title=book.title,
            subject_id=book.subject_id,
            subject_slug=subject.slug if subject else None,
            subject_name=subject.name if subject else None,
            subject_category=subject.category if subject else None,
            method_id=book.method_id,
            edition=book.edition,
            school_years=book.school_years,
            levels=book.levels,
            cover_url=book.cover_url,
            url=book.url,
            chapters=[
                ChapterResponse(
                    id=c.id,
                    index=c.index,
                    title=c.title,
                    paragraphs=[
                        ParagraphResponse(
                            id=p.id,
                            index=p.index,
                            title=p.title,
                            synopsis=p.synopsis,
                        )
                        for p in paragraphs_by_chapter.get(c.id, [])
                    ],
                )
                for c in chapters
            ],
        )

    return await run_read_with_retry(operation)


@router.post("/", response_model=Book, status_code=201)
async def create_book(data: Book, session: AsyncSession = Depends(get_session)):
    book = Book.model_validate(data)
    if book.subject_id is None:
        raise HTTPException(status_code=422, detail="subject_id is required")
    if not await _subject_exists(session, book.subject_id):
        raise HTTPException(status_code=422, detail="Invalid subject_id")
    session.add(book)
    await session.commit()
    await session.refresh(book)
    logger.info("Created book: id=%s slug=%s", book.id, book.slug)
    return book


@router.patch("/{book_id}", response_model=Book)
async def update_book(book_id: str, data: Book, session: AsyncSession = Depends(get_session)):
    book = await session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    has_subject_id = "subject_id" in update

    if has_subject_id and update["subject_id"] is None:
        raise HTTPException(status_code=422, detail="subject_id cannot be null")

    if has_subject_id and update["subject_id"] is not None:
        subject_id_value = update["subject_id"]
        if not isinstance(subject_id_value, str):
            raise HTTPException(status_code=422, detail="Invalid subject_id")
        if not await _subject_exists(session, subject_id_value):
            raise HTTPException(status_code=422, detail="Invalid subject_id")
    book.sqlmodel_update(update)
    await session.commit()
    await session.refresh(book)
    logger.info("Updated book: id=%s fields=%s", book_id, list(update.keys()))
    return book


@router.delete("/{book_id}", status_code=204)
async def delete_book(book_id: str, session: AsyncSession = Depends(get_session)):
    book = await session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    await session.delete(book)
    await session.commit()
    logger.info("Deleted book: id=%s", book_id)
