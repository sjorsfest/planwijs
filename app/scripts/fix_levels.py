"""Re-parse levels for all books that currently have Level.Unknown.

Uses the improved _parse_book_slug / KNOWN_LEVEL_PATTERNS from seed_from_sitemap
to deterministically derive levels from the book slug and update the database.

Usage:
    python -m app.scripts.fix_levels [--dry-run] [--all]

Options:
    --dry-run   Print what would change without writing to the database.
    --all       Re-process every book, not just those with Unknown levels.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlmodel import select

from app.database import SessionLocal
from app.models.book import Book
from app.models.enums import Level
import re

from app.scripts.seed_from_sitemap import (
    _parse_book_slug,
    _resolve_levels,
)

logger = logging.getLogger(__name__)

_BOOK_SLUG_RE = re.compile(r"/books/(?P<method>[^/]+)/(?P<book>[^/?#]+)")


def _slug_from_url(url: str) -> str | None:
    m = _BOOK_SLUG_RE.search(url)
    return m.group("book") if m else None


async def run(dry_run: bool = False, process_all: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    async with SessionLocal() as session:
        stmt = select(Book)
        if not process_all:
            # SQLAlchemy JSONB contains check: levels array includes the string "Unknown"
            stmt = stmt.where(Book.levels.contains(["Unknown"]))  # type: ignore[union-attr]
        result = await session.execute(stmt)
        books: list[Book] = list(result.scalars().all())

    label = "all" if process_all else "Unknown-level"
    logger.info("Found %d %s books to process", len(books), label)

    updated = 0
    unchanged = 0
    no_slug = 0

    for book in books:
        book_slug = _slug_from_url(book.url) or book.slug
        _, level_tokens, _, _ = _parse_book_slug(book_slug)
        new_levels = _resolve_levels(level_tokens)

        current = [lv if isinstance(lv, str) else lv.value for lv in book.levels]
        new_values = [lv.value for lv in new_levels]

        if current == new_values:
            unchanged += 1
            continue

        logger.info(
            "  %-60s  %s  →  %s",
            book.slug,
            current,
            new_values,
        )

        if dry_run:
            updated += 1
            continue

        async with SessionLocal() as session:
            result2 = await session.execute(select(Book).where(Book.id == book.id))
            b = result2.scalars().first()
            if b:
                b.levels = new_levels
                await session.commit()
                updated += 1

    logger.info(
        "Done. updated=%d  unchanged=%d  no_slug=%d",
        updated,
        unchanged,
        no_slug,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix Unknown levels in the book table")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--all", dest="process_all", action="store_true",
                        help="Re-process all books, not just Unknown ones")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, process_all=args.process_all))


if __name__ == "__main__":
    main()
