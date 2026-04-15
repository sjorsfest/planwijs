"""Fix incorrect book_chapter_paragraphs by scraping correct titles from jojoschool.

The seed_from_sitemap script created paragraphs from sitemap URLs, but many chapters
ended up with all paragraphs having the same title (the chapter title). This script
scrapes the actual book pages to get the correct paragraph titles from the nav sidebar.

Usage:
    python -m app.scripts.fix_paragraphs [--dry-run] [--limit N]
    python -m app.scripts.fix_paragraphs rebuild [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import lxml.html as lxml_html
from sqlmodel import delete, select

from app.database import SessionLocal
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent / "damp-firefly-51454050_dev_neondb_2026-04-14_15-51-18.csv"

# Regex to parse "1.2 Some title" -> chapter_num=1, para_num=2, title="Some title"
PARA_TITLE_RE = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")
# Patterns to extract chapter number and title from various formats:
#   "1 Arm en rijk"                     -> num=1, title="Arm en rijk"
#   "Hoofdstuk 1 | Ruilen over de tijd" -> num=1, title="Ruilen over de tijd"
#   "HOOFDSTUK 1 Ruilen over de tijd"   -> num=1, title="Ruilen over de tijd"
#   "Thema 5 REGELING"                  -> num=5, title="REGELING"
#   "A Hoe wordt geschiedenis gebruikt?" -> num=None (use position), title="Hoe wordt geschiedenis gebruikt?"
#   "SPELTHEORIE"                        -> num=None (use position), title="SPELTHEORIE"
NUMBERED_CHAPTER_PATTERNS = [
    re.compile(r"^hoofdstuk\s+(\d+)\s*\|\s*(.+)$", re.IGNORECASE),
    re.compile(r"^hoofdstuk\s+(\d+)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^thema\s+(\d+)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(\d+)\.\s+(.+)$"),  # "1. Title"
    re.compile(r"^(\d+)\s+(.+)$"),     # "1 Title"
]
# Letter-prefixed: "A Title", "B Title", etc.
LETTER_CHAPTER_RE = re.compile(r"^([A-Z])\s+(.+)$")



@dataclass
class CsvRow:
    book_url: str
    chapter_id: str
    chapter_title: str


@dataclass
class ParsedParagraph:
    index: int
    title: str  # Full title like "1.1 Veranderingen in woonbuurten"
    short_title: str  # Just "Veranderingen in woonbuurten"


@dataclass
class ParsedChapter:
    number: int
    title: str  # e.g. "Arm en rijk"
    paragraphs: list[ParsedParagraph] = field(default_factory=list)


def _read_csv(csv_path: Path | None = None) -> list[CsvRow]:
    rows: list[CsvRow] = []
    with open(csv_path or CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                CsvRow(
                    book_url=row["book_url"],
                    chapter_id=row["chapter_id"],
                    chapter_title=row["chapter"],
                )
            )
    return rows


async def _fetch_page(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        return None


def _parse_nav_chapters(html: str) -> list[ParsedChapter]:
    """Parse the navigation sidebar to extract chapters and paragraphs."""
    doc = lxml_html.fromstring(html)

    # Find all chapter sections in the nav using XPath
    sections = doc.xpath("//nav//section")
    if not sections:
        sections = doc.xpath("//section[contains(@class, 'group/content-sidebar-group')]")

    chapters: list[ParsedChapter] = []

    for section in sections:
        # Get chapter title from the font-gilroy span
        title_spans = section.xpath(".//span[contains(@class, 'font-gilroy')]")
        if not title_spans:
            continue
        chapter_full_title = title_spans[0].text_content().strip()

        # Try numbered patterns first
        m = None
        for pattern in NUMBERED_CHAPTER_PATTERNS:
            m = pattern.match(chapter_full_title)
            if m:
                break

        if m:
            chapter_num = int(m.group(1))
            chapter_title = m.group(2)
        else:
            # Try letter-prefixed: "A Title", "B Title"
            lm = LETTER_CHAPTER_RE.match(chapter_full_title)
            if lm:
                # Use letter's position (A=1, B=2, ...)
                chapter_num = ord(lm.group(1)) - ord("A") + 1
                chapter_title = lm.group(2)
            else:
                # No number/letter prefix — use position, full title
                chapter_num = len(chapters) + 1
                chapter_title = chapter_full_title

        chapter = ParsedChapter(number=chapter_num, title=chapter_title)

        # Get paragraphs from the <ul> <li> inside this section
        lis = section.xpath(".//ul/li")
        for idx, li in enumerate(lis, start=1):
            # Get the paragraph title from the truncate span
            truncate_spans = li.xpath(".//span[contains(@class, 'truncate')]")
            if not truncate_spans:
                continue
            para_full_title = truncate_spans[0].text_content().strip()

            pm = PARA_TITLE_RE.match(para_full_title)
            if pm:
                para_index = int(pm.group(2))
                short_title = pm.group(3)
            else:
                # Fallback: use position as index, full text as title
                para_index = idx
                short_title = para_full_title

            chapter.paragraphs.append(
                ParsedParagraph(
                    index=para_index,
                    title=para_full_title,
                    short_title=short_title,
                )
            )

        chapters.append(chapter)

    return chapters


def _normalize(s: str) -> str:
    """Normalize a string for fuzzy matching."""
    return re.sub(r"\s+", " ", s.lower().strip())


def _match_chapter(
    csv_title: str, parsed_chapters: list[ParsedChapter]
) -> ParsedChapter | None:
    """Match a CSV chapter title to a parsed nav chapter."""
    norm_csv = _normalize(csv_title)
    for ch in parsed_chapters:
        if _normalize(ch.title) == norm_csv:
            return ch
    # Fuzzy: check if one contains the other
    for ch in parsed_chapters:
        norm_ch = _normalize(ch.title)
        if norm_csv in norm_ch or norm_ch in norm_csv:
            return ch
    return None


async def run(dry_run: bool = False, limit: int | None = None, csv_path: Path | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    rows = _read_csv(csv_path)
    logger.info("Read %d rows from CSV", len(rows))

    if limit:
        rows = rows[:limit]

    # Group by book_url
    book_chapters: dict[str, list[CsvRow]] = {}
    for row in rows:
        book_chapters.setdefault(row.book_url, []).append(row)
    logger.info("Found %d unique book URLs", len(book_chapters))

    total_fixed = 0
    total_skipped = 0

    for book_url, csv_rows in book_chapters.items():
        logger.info("Fetching: %s (%d chapters)", book_url, len(csv_rows))

        html = await _fetch_page(book_url)
        if html is None:
            logger.warning("  Skipping (fetch failed)")
            total_skipped += len(csv_rows)
            continue

        parsed_chapters = _parse_nav_chapters(html)
        if not parsed_chapters:
            logger.warning("  No chapters found in nav for %s", book_url)
            total_skipped += len(csv_rows)
            continue

        logger.info("  Parsed %d chapters from nav", len(parsed_chapters))

        for csv_row in csv_rows:
            matched = _match_chapter(csv_row.chapter_title, parsed_chapters)
            if matched is None:
                logger.warning(
                    "  No nav match for chapter '%s' (id=%s)",
                    csv_row.chapter_title,
                    csv_row.chapter_id,
                )
                total_skipped += 1
                continue

            if not matched.paragraphs:
                logger.warning(
                    "  No paragraphs in nav for chapter '%s'",
                    csv_row.chapter_title,
                )
                total_skipped += 1
                continue

            if dry_run:
                print(f"\n  Chapter '{csv_row.chapter_title}' (id={csv_row.chapter_id}):")
                print(f"    Matched nav chapter: {matched.number} {matched.title}")
                for p in matched.paragraphs:
                    print(f"      [{p.index}] {p.title}")
                total_fixed += 1
                continue

            # Delete existing paragraphs and insert correct ones
            async with SessionLocal() as session:
                # Verify chapter exists
                result = await session.execute(
                    select(BookChapter).where(BookChapter.id == csv_row.chapter_id)
                )
                chapter = result.scalars().first()
                if not chapter:
                    logger.warning(
                        "  Chapter id=%s not found in DB, skipping",
                        csv_row.chapter_id,
                    )
                    total_skipped += 1
                    continue

                # Delete existing paragraphs
                await session.execute(
                    delete(BookChapterParagraph).where(
                        BookChapterParagraph.chapter_id == csv_row.chapter_id  # type: ignore[arg-type]
                    )
                )

                # Also update chapter title with the correct title from nav
                chapter.title = matched.title
                chapter.index = matched.number

                # Insert correct paragraphs
                for p in matched.paragraphs:
                    session.add(
                        BookChapterParagraph(
                            index=p.index,
                            title=p.short_title,
                            chapter_id=csv_row.chapter_id,
                        )
                    )

                await session.commit()
                logger.info(
                    "  Fixed chapter '%s': %d paragraphs",
                    csv_row.chapter_title,
                    len(matched.paragraphs),
                )
                total_fixed += 1

        # Small delay between book fetches
        await asyncio.sleep(0.5)

    logger.info("Done. Fixed: %d, Skipped: %d", total_fixed, total_skipped)


def _sanitize_chapter_title(title: str) -> str:
    """Remove leading chapter numbers, 'HOOFDSTUK X', 'Thema X', and letter prefixes."""
    # Remove "Hoofdstuk X |" / "HOOFDSTUK X" prefix
    title = re.sub(r"^hoofdstuk\s+\d+\s*\|?\s*", "", title, flags=re.IGNORECASE).strip()
    # Remove "Thema X" prefix
    title = re.sub(r"^thema\s+\d+\s+", "", title, flags=re.IGNORECASE).strip()
    # Remove leading "X. " or "X " chapter number if still present
    m = re.match(r"^\d+\.?\s+(.+)$", title)
    if m:
        title = m.group(1)
    # Remove single letter prefix like "A ", "B "
    m = re.match(r"^[A-Z]\s+(.+)$", title)
    if m:
        title = m.group(1)
    return title.strip()


async def run_rebuild(dry_run: bool = False, limit: int | None = None, csv_path: Path | None = None) -> None:
    """Rebuild chapters for books where matching previously failed.

    Strategy: for each unmatched chapter, find its book, delete ALL chapters
    from that book, then re-scrape and re-create from the nav sidebar.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    rows = _read_csv(csv_path)
    logger.info("Read %d rows from CSV", len(rows))

    # Group by book_url
    book_chapters: dict[str, list[CsvRow]] = {}
    for row in rows:
        book_chapters.setdefault(row.book_url, []).append(row)

    # First pass: identify which book_urls have unmatched chapters
    unmatched_book_urls: dict[str, list[CsvRow]] = {}

    for book_url, csv_rows in book_chapters.items():
        html = await _fetch_page(book_url)
        if html is None:
            # Can't fetch at all — collect these too
            unmatched_book_urls[book_url] = csv_rows
            continue

        parsed_chapters = _parse_nav_chapters(html)
        if not parsed_chapters:
            unmatched_book_urls[book_url] = csv_rows
            continue

        for csv_row in csv_rows:
            matched = _match_chapter(csv_row.chapter_title, parsed_chapters)
            if matched is None:
                unmatched_book_urls.setdefault(book_url, []).append(csv_row)

        await asyncio.sleep(0.3)

    logger.info("Found %d book URLs with unmatched chapters", len(unmatched_book_urls))

    if limit:
        urls = list(unmatched_book_urls.keys())[:limit]
        unmatched_book_urls = {u: unmatched_book_urls[u] for u in urls}

    total_rebuilt = 0
    total_skipped = 0

    for book_url, csv_rows in unmatched_book_urls.items():
        logger.info("Rebuilding: %s", book_url)

        html = await _fetch_page(book_url)
        if html is None:
            logger.warning("  Skipping (fetch failed)")
            total_skipped += 1
            continue

        parsed_chapters = _parse_nav_chapters(html)
        if not parsed_chapters:
            logger.warning("  No chapters found in nav, skipping")
            total_skipped += 1
            continue

        # Sanitize chapter titles
        for ch in parsed_chapters:
            ch.title = _sanitize_chapter_title(ch.title)

        if dry_run:
            print(f"\n  Book: {book_url}")
            print(f"  Will delete existing chapters and recreate {len(parsed_chapters)} from nav:")
            for ch in parsed_chapters:
                print(f"    [{ch.number}] {ch.title} ({len(ch.paragraphs)} paragraphs)")
                for p in ch.paragraphs:
                    print(f"        [{p.index}] {p.short_title}")
            total_rebuilt += 1
            continue

        async with SessionLocal() as session:
            # Find the book by URL
            result = await session.execute(select(Book).where(Book.url == book_url))
            book = result.scalars().first()
            if not book:
                logger.warning("  Book not found in DB for URL: %s", book_url)
                total_skipped += 1
                continue

            # Delete ALL existing chapters (cascade deletes paragraphs)
            await session.execute(
                delete(BookChapter).where(BookChapter.book_id == book.id)  # type: ignore[arg-type]
            )

            # Create new chapters and paragraphs from nav
            for ch in parsed_chapters:
                new_chapter = BookChapter(
                    index=ch.number,
                    title=ch.title,
                    book_id=book.id,
                )
                session.add(new_chapter)
                await session.flush()  # Get the new chapter ID

                for p in ch.paragraphs:
                    session.add(
                        BookChapterParagraph(
                            index=p.index,
                            title=p.short_title,
                            chapter_id=new_chapter.id,
                        )
                    )

            await session.commit()
            logger.info(
                "  Rebuilt book: %d chapters, %d total paragraphs",
                len(parsed_chapters),
                sum(len(ch.paragraphs) for ch in parsed_chapters),
            )
            total_rebuilt += 1

        await asyncio.sleep(0.5)

    logger.info("Done. Rebuilt: %d, Skipped: %d", total_rebuilt, total_skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix incorrect book chapter paragraphs")
    subparsers = parser.add_subparsers(dest="command")

    # Default command (fix paragraphs by matching)
    fix_parser = subparsers.add_parser("fix", help="Fix paragraphs by matching chapter titles")
    fix_parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    fix_parser.add_argument("--limit", type=int, default=None, help="Process only first N CSV rows")
    fix_parser.add_argument("--csv", type=str, default=None, help="Path to CSV file (default: original CSV)")

    # Rebuild command (delete and recreate chapters)
    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild chapters for unmatched books")
    rebuild_parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    rebuild_parser.add_argument("--limit", type=int, default=None, help="Process only first N book URLs")
    rebuild_parser.add_argument("--csv", type=str, default=None, help="Path to CSV file (default: original CSV)")

    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else CSV_PATH

    if args.command == "rebuild":
        asyncio.run(run_rebuild(dry_run=args.dry_run, limit=args.limit, csv_path=csv_path))
    else:
        asyncio.run(run(dry_run=args.dry_run, limit=args.limit, csv_path=csv_path))


if __name__ == "__main__":
    main()
