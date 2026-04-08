from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.subject import Subject


async def list_books(
    session: AsyncSession,
    *,
    method_id: str | None = None,
    subject_id: str | None = None,
    level_value: str | None = None,
    school_year_value: str | None = None,
) -> list[Book]:
    stmt = select(Book).order_by(Book.title)
    if method_id is not None:
        stmt = stmt.where(Book.method_id == method_id)
    if subject_id is not None:
        stmt = stmt.where(Book.subject_id == subject_id)
    if level_value is not None:
        stmt = stmt.where(Book.levels.contains([level_value]))  # type: ignore[union-attr]
    if school_year_value is not None:
        stmt = stmt.where(Book.school_years.contains([school_year_value]))  # type: ignore[union-attr]
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, book_id: str) -> Book | None:
    return await session.get(Book, book_id)


async def get_chapters(session: AsyncSession, book_id: str) -> list[BookChapter]:
    result = await session.execute(
        select(BookChapter)
        .where(BookChapter.book_id == book_id)
        .order_by(BookChapter.index)  # type: ignore[arg-type]
    )
    return list(result.scalars().all())


async def get_chapter_paragraphs(
    session: AsyncSession, chapter_ids: list[str]
) -> list[BookChapterParagraph]:
    if not chapter_ids:
        return []
    result = await session.execute(
        select(BookChapterParagraph)
        .where(BookChapterParagraph.chapter_id.in_(chapter_ids))  # type: ignore[union-attr]
        .order_by(BookChapterParagraph.index)  # type: ignore[arg-type]
    )
    return list(result.scalars().all())


async def get_subject_by_id(session: AsyncSession, subject_id: str) -> Subject | None:
    return await session.get(Subject, subject_id)


async def subject_exists(session: AsyncSession, subject_id: str) -> bool:
    result = await session.execute(select(Subject.id).where(Subject.id == subject_id))
    return result.scalars().first() is not None


async def save(session: AsyncSession, book: Book) -> Book:
    session.add(book)
    await session.commit()
    await session.refresh(book)
    return book


async def delete(session: AsyncSession, book: Book) -> None:
    await session.delete(book)
    await session.commit()
