"""
Fetch and store paragraphs for book chapters using the paragraph agent.

The agent searches the web for study summary pages and extracts the paragraph
structure for each chapter. Only reliably sourced data is stored; if nothing
is found for a chapter, no records are written.

Usage:
    python -m app.scripts.fetch_paragraphs --all [--dry-run] [--limit N]
    python -m app.scripts.fetch_paragraphs --book-id <id> [--dry-run]
    python -m app.scripts.fetch_paragraphs --chapter-id <id> [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


async def _upsert_paragraphs(
    session: AsyncSession,
    chapter_id: str,
    paragraphs: list,
) -> None:
    for p in paragraphs:
        result = await session.exec(
            select(BookChapterParagraph).where(
                BookChapterParagraph.chapter_id == chapter_id,
                BookChapterParagraph.index == p.index,
            )
        )
        existing = result.first()
        if existing:
            existing.title = p.title
            existing.synopsis = p.synopsis
        else:
            session.add(BookChapterParagraph(
                index=p.index,
                title=p.title,
                synopsis=p.synopsis,
                chapter_id=chapter_id,
            ))


# ---------------------------------------------------------------------------
# Per-chapter processing
# ---------------------------------------------------------------------------


async def process_chapter(
    session: AsyncSession,
    chapter: BookChapter,
    book: Book,
    dry_run: bool,
) -> list[dict]:
    from app.agents.paragraph_agent import find_paragraphs

    result = await find_paragraphs(chapter, book)

    if not result.paragraphs:
        logger.info(
            "No paragraphs found for chapter %d of %r — skipping",
            chapter.index, book.title,
        )
        return []

    if not dry_run:
        await _upsert_paragraphs(session, chapter.id, result.paragraphs)
        await session.commit()
        logger.info(
            "Saved %d paragraph(s) for chapter %d of %r",
            len(result.paragraphs), chapter.index, book.title,
        )

    return [p.model_dump() for p in result.paragraphs]


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> list[dict]:
    engine = create_async_engine(settings.database_url)
    output: list[dict] = []

    async with AsyncSession(engine) as session:
        if args.chapter_id:
            chapter_result = await session.exec(
                select(BookChapter).where(BookChapter.id == args.chapter_id)
            )
            chapter = chapter_result.first()
            if chapter is None:
                logger.error("Chapter not found: %s", args.chapter_id)
                await engine.dispose()
                return []
            book_result = await session.exec(select(Book).where(Book.id == chapter.book_id))
            book = book_result.first()
            if book is None:
                logger.error("Book not found for chapter: %s", args.chapter_id)
                await engine.dispose()
                return []
            paragraphs = await process_chapter(session, chapter, book, args.dry_run)
            output.append({"chapter_id": chapter.id, "paragraphs": paragraphs})

        elif args.book_id:
            book_result = await session.exec(select(Book).where(Book.id == args.book_id))
            book = book_result.first()
            if book is None:
                logger.error("Book not found: %s", args.book_id)
                await engine.dispose()
                return []
            chapters_result = await session.exec(
                select(BookChapter).where(BookChapter.book_id == args.book_id)
            )
            chapters = list(chapters_result.all())
            limit = args.limit or len(chapters)
            for chapter in chapters[:limit]:
                paragraphs = await process_chapter(session, chapter, book, args.dry_run)
                output.append({"chapter_id": chapter.id, "paragraphs": paragraphs})

        elif args.all:
            chapters_result = await session.exec(select(BookChapter))
            chapters = list(chapters_result.all())
            limit = args.limit or len(chapters)
            for chapter in chapters[:limit]:
                book_result = await session.exec(
                    select(Book).where(Book.id == chapter.book_id)
                )
                book = book_result.first()
                if book is None:
                    logger.warning("Book not found for chapter %s — skipping", chapter.id)
                    continue
                paragraphs = await process_chapter(session, chapter, book, args.dry_run)
                output.append({"chapter_id": chapter.id, "paragraphs": paragraphs})

    await engine.dispose()
    return output


def main() -> None:
    from app.logging_config import configure_logging
    # level is set after arg parsing below

    parser = argparse.ArgumentParser(
        description="Fetch paragraphs for book chapters using an AI web-search agent."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Process all chapters in the database")
    group.add_argument("--book-id", help="Process all chapters for a specific book ID")
    group.add_argument("--chapter-id", help="Process a single chapter by ID")
    parser.add_argument("--dry-run", action="store_true", help="Print output only, do not save to DB")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of chapters to process")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show raw agent outputs (DEBUG logging)")
    args = parser.parse_args()

    configure_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    output = asyncio.run(_run(args))
    print(json.dumps(output, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
