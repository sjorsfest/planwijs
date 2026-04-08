import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_read_with_retry
from app.exceptions import NotFoundError, ValidationError
from app.models.book import Book
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.enums import Level, SchoolYear
from app.repositories import book as book_repo
from app.routes.books.types import BookDetailResponse, ChapterResponse, ParagraphResponse

logger = logging.getLogger(__name__)


async def list_books(
    *,
    method_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    level: Optional[Level] = None,
    school_year: Optional[SchoolYear] = None,
) -> list[Book]:
    async def _op(session: AsyncSession) -> list[Book]:
        return await book_repo.list_books(
            session,
            method_id=method_id,
            subject_id=subject_id,
            level_value=level.value if level else None,
            school_year_value=school_year.value if school_year else None,
        )

    return await run_read_with_retry(_op)


async def get_book_detail(book_id: str) -> BookDetailResponse:
    async def _op(session: AsyncSession) -> BookDetailResponse:
        book = await book_repo.get_by_id(session, book_id)
        if not book:
            raise NotFoundError("Book not found")

        subject = (
            await book_repo.get_subject_by_id(session, book.subject_id)
            if book.subject_id
            else None
        )
        chapters = await book_repo.get_chapters(session, book_id)
        chapter_ids = [c.id for c in chapters]
        paragraphs = await book_repo.get_chapter_paragraphs(session, chapter_ids)

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

    return await run_read_with_retry(_op)


async def create_book(session: AsyncSession, data: Book) -> Book:
    book = Book.model_validate(data)
    if book.subject_id is None:
        raise ValidationError("subject_id is required")
    if not await book_repo.subject_exists(session, book.subject_id):
        raise ValidationError("Invalid subject_id")
    book = await book_repo.save(session, book)
    logger.info("Created book: id=%s slug=%s", book.id, book.slug)
    return book


async def update_book(session: AsyncSession, book_id: str, data: Book) -> Book:
    book = await book_repo.get_by_id(session, book_id)
    if not book:
        raise NotFoundError("Book not found")

    update = data.model_dump(exclude_unset=True, exclude={"id"})
    has_subject_id = "subject_id" in update

    if has_subject_id and update["subject_id"] is None:
        raise ValidationError("subject_id cannot be null")

    if has_subject_id and update["subject_id"] is not None:
        subject_id_value = update["subject_id"]
        if not isinstance(subject_id_value, str):
            raise ValidationError("Invalid subject_id")
        if not await book_repo.subject_exists(session, subject_id_value):
            raise ValidationError("Invalid subject_id")

    book.sqlmodel_update(update)
    await session.commit()
    await session.refresh(book)
    logger.info("Updated book: id=%s fields=%s", book_id, list(update.keys()))
    return book


async def delete_book(session: AsyncSession, book_id: str) -> None:
    book = await book_repo.get_by_id(session, book_id)
    if not book:
        raise NotFoundError("Book not found")
    await book_repo.delete(session, book)
    logger.info("Deleted book: id=%s", book_id)
