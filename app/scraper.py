"""
Scraper for toets-mij.nl — fetches methods, books, and chapters.

Usage:
    python -m app.scraper --methods [--dry-run]
    python -m app.scraper --method-slug <slug> [--dry-run]
    python -m app.scraper --book-url <url> [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel as PydanticBase
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.enums import Level, SchoolYear, Subject
from app.models.method import Method

logger = logging.getLogger(__name__)

BASE_URL = "https://www.toets-mij.nl"
DEFAULT_TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Intermediate Pydantic scrape models (not SQLModel / no DB table)
# ---------------------------------------------------------------------------


class ScrapedMethod(PydanticBase):
    slug: str
    title: str
    subject: Subject = Subject.UNKNOWN
    url: str


class ScrapedBook(PydanticBase):
    book_id: Optional[int] = None
    slug: str
    title: str
    subject: Subject = Subject.UNKNOWN
    method_slug: Optional[str] = None
    edition: Optional[str] = None
    school_years: list[SchoolYear] = []
    levels: list[Level] = []
    cover_url: Optional[str] = None
    url: str


class ScrapedChapter(PydanticBase):
    index: int
    title: str
    toets_url: Optional[str] = None
    book_url: str


# ---------------------------------------------------------------------------
# Regex / lookup tables
# ---------------------------------------------------------------------------

SUBJECT_BY_LABEL = {item.value.casefold(): item for item in Subject}
LEVEL_BY_LABEL = {item.value.casefold(): item for item in Level}
YEAR_BY_LABEL = {item.value.casefold(): item for item in SchoolYear}

METHOD_HREF_RE = re.compile(r"(?:https://www\.toets-mij\.nl)?/lesboeken/([^/?#]+)$")
BOOK_HREF_RE = re.compile(r"(?:https://www\.toets-mij\.nl)?/lesboeken/(\d+)-([^/?#]+)$")
COUNT_RE = re.compile(r"(\d+)\s+lesboeken", re.IGNORECASE)
CHAPTER_TITLE_RE = re.compile(r"^Hoofdstuk\s+(\d+)\s*-?\s*(.+)$", re.IGNORECASE)
YEAR_RE = re.compile(r"\b([1-6]e jaar)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ToetsMijScraper:
    def __init__(self, base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                )
            },
            follow_redirects=True,
            timeout=timeout,
        )

    def __enter__(self) -> ToetsMijScraper:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def get_soup(self, path_or_url: str) -> BeautifulSoup:
        url = path_or_url if path_or_url.startswith("http") else urljoin(self.base_url, path_or_url)
        logger.debug("GET %s", url)
        response = self._client.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml")

    def get_text(self, path_or_url: str) -> str:
        url = path_or_url if path_or_url.startswith("http") else urljoin(self.base_url, path_or_url)
        logger.debug("GET %s", url)
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def fetch_methods(self) -> list[ScrapedMethod]:
        soup = self.get_soup("/lesboeken")
        article = soup.select_one("main article") or soup

        methods: dict[str, ScrapedMethod] = {}
        for anchor in article.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            match = METHOD_HREF_RE.match(href)
            if not match:
                continue

            slug = match.group(1)
            if slug in {"lesboeken", "zoeken"}:
                continue

            text = normalize_ws(anchor.get_text(" ", strip=True))
            if not text:
                continue

            method = self._parse_method_anchor(anchor, slug)
            if method is None:
                continue

            existing = methods.get(slug)
            if existing is None:
                methods[slug] = method
            else:
                methods[slug] = _merge_methods(existing, method)

        result = sorted(methods.values(), key=lambda m: (m.subject.value, m.title.lower()))
        logger.info("Fetched %d methods", len(result))
        return result

    def fetch_books_for_method(self, method: ScrapedMethod | str) -> list[ScrapedBook]:
        method_url = method.url if isinstance(method, ScrapedMethod) else method
        method_slug = _extract_slug_from_url(str(method_url))
        soup = self.get_soup(str(method_url))

        books: dict[str, ScrapedBook] = {}
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not BOOK_HREF_RE.match(href):
                continue
            book = self._parse_book_anchor(anchor, method_slug=method_slug)
            if book is not None:
                books[book.url] = book

        result = sorted(books.values(), key=lambda b: (b.title.lower(), b.url))
        logger.info("Fetched %d books for method %s", len(result), method_slug)
        return result

    def fetch_book_chapters(self, book: ScrapedBook | str) -> list[ScrapedChapter]:
        book_url = book.url if isinstance(book, ScrapedBook) else book
        soup = self.get_soup(str(book_url))

        # Primary: "Hoofdstuk N - title" anchors that link directly to the toets
        chapters: dict[int, ScrapedChapter] = {}
        for anchor in soup.select("a[href]"):
            text = normalize_ws(anchor.get_text(" ", strip=True))
            match = CHAPTER_TITLE_RE.match(text)
            if not match:
                continue
            index = int(match.group(1))
            title = normalize_ws(match.group(2))
            href = str(anchor.get("href") or "").strip()
            toets_url = urljoin(self.base_url, href) if href else None
            if index not in chapters:
                chapters[index] = ScrapedChapter(
                    index=index,
                    title=title,
                    toets_url=toets_url,
                    book_url=str(book_url),
                )

        if chapters:
            result = [chapters[idx] for idx in sorted(chapters)]
            logger.info("Fetched %d chapters for book %s", len(result), book_url)
            return result

        # Fallback: sectie-style books (HC / thema-based) where chapters are
        # linked as #sectie1, #sectie2, … with separate /lesboeken/toets/ URLs.
        sectie_anchors = soup.select("a[href^='#sectie']")
        toets_anchors = [
            a for a in soup.select("a[href]")
            if re.search(r"/lesboeken/toets/", str(a.get("href", "")))
        ]
        for i, sectie_a in enumerate(sectie_anchors, start=1):
            title = normalize_ws(sectie_a.get_text(" ", strip=True))
            toets_url = None
            if i <= len(toets_anchors):
                href = str(toets_anchors[i - 1].get("href") or "").strip()
                toets_url = href if href.startswith("http") else urljoin(self.base_url, href)
            chapters[i] = ScrapedChapter(
                index=i,
                title=title,
                toets_url=toets_url,
                book_url=str(book_url),
            )

        result = [chapters[idx] for idx in sorted(chapters)]
        logger.info("Fetched %d chapters for book %s", len(result), book_url)
        return result

    def _parse_method_anchor(self, anchor: Tag, slug: str) -> Optional[ScrapedMethod]:
        text = normalize_ws(anchor.get_text(" ", strip=True))

        subject = Subject.UNKNOWN
        for candidate in Subject:
            if candidate is Subject.UNKNOWN:
                continue
            if text.casefold().startswith(candidate.value.casefold()):
                subject = candidate
                break

        title = COUNT_RE.sub("", text).strip()
        if subject is not Subject.UNKNOWN and title.casefold().startswith(subject.value.casefold()):
            title = title[len(subject.value):].strip() or title

        title_candidates = [
            normalize_ws(node.get_text(" ", strip=True))
            for node in anchor.select(".text, .title, img[alt]")
            if normalize_ws(node.get_text(" ", strip=True))
        ]
        if title_candidates:
            title = str(max(title_candidates, key=len))

        if not title:
            return None

        return ScrapedMethod(
            slug=slug,
            title=title,
            subject=subject,
            url=urljoin(self.base_url, str(anchor["href"])),
        )

    def _parse_book_anchor(self, anchor: Tag, method_slug: Optional[str]) -> Optional[ScrapedBook]:
        href = str(anchor.get("href") or "").strip()
        match = BOOK_HREF_RE.match(href)
        if not match:
            return None

        book_id = int(match.group(1))
        slug = match.group(2)
        title = _extract_first_text(anchor, [".title", "img[alt]"]) or normalize_ws(anchor.get_text(" ", strip=True))
        title = _cleanup_book_title(title)
        edition = _extract_first_text(anchor, [".edition"]) or _extract_edition_from_text(normalize_ws(anchor.get_text(" ", strip=True)))
        levels = _parse_levels(_extract_first_text(anchor, [".metadata"]) or normalize_ws(anchor.get_text(" ", strip=True)))
        school_years = _parse_school_years(normalize_ws(anchor.get_text(" ", strip=True)))
        subject_text = _extract_first_text(anchor, [".label"]) or normalize_ws(anchor.get_text(" ", strip=True))
        subject = _parse_subject(subject_text)

        img = anchor.select_one("img[src]")
        cover_url = urljoin(self.base_url, str(img["src"])) if img and img.get("src") else None

        return ScrapedBook(
            book_id=book_id,
            slug=slug,
            title=title,
            subject=subject,
            method_slug=method_slug,
            edition=edition,
            school_years=school_years,
            levels=levels,
            cover_url=cover_url,
            url=urljoin(self.base_url, href),
        )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _extract_slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def _extract_first_text(anchor: Tag, selectors: Iterable[str]) -> Optional[str]:
    for selector in selectors:
        if selector.endswith("[alt]"):
            node = anchor.select_one(selector)
            if node and node.get("alt"):
                return normalize_ws(str(node["alt"]))
        else:
            node = anchor.select_one(selector)
            if node:
                text = normalize_ws(node.get_text(" ", strip=True))
                if text:
                    return text
    return None


def _cleanup_book_title(value: str) -> str:
    value = normalize_ws(value)
    value = re.sub(r"\bToetsen bekijken\b", "", value, flags=re.IGNORECASE)
    return normalize_ws(value)


def _extract_edition_from_text(value: str) -> Optional[str]:
    match = re.search(r"\b\d+(?:e|de) editie\b", value, flags=re.IGNORECASE)
    return normalize_ws(match.group(0)) if match else None


def _parse_subject(text: str) -> Subject:
    text_cf = normalize_ws(text).casefold()
    for label, subject in SUBJECT_BY_LABEL.items():
        if label == Subject.UNKNOWN.value.casefold():
            continue
        if re.search(rf"\b{re.escape(label)}\b", text_cf):
            return subject
    return Subject.UNKNOWN


def _parse_school_years(text: str) -> list[SchoolYear]:
    years: list[SchoolYear] = []
    for match in YEAR_RE.finditer(text):
        key = str(match.group(1)).casefold()
        year = next((v for k, v in YEAR_BY_LABEL.items() if k == key), None)
        if year and year not in years:
            years.append(year)
    return years


# Map legacy combined strings to their constituent individual Level values.
_COMBINED_LEVEL_EXPANSIONS: dict[str, list[Level]] = {
    "havo/vwo": [Level.HAVO, Level.VWO],
    "vmbo-havo": [Level.VMBO_T, Level.HAVO],
    "vmbo-bk": [Level.VMBO_B, Level.VMBO_K],
    "vmbo-gt": [Level.VMBO_G, Level.VMBO_T],
}


def _parse_levels(text: str) -> list[Level]:
    text_cf = normalize_ws(text).casefold()
    seen: set[Level] = set()
    levels: list[Level] = []

    # Expand combined strings first so they don't partial-match individual labels.
    for combined, expansion in _COMBINED_LEVEL_EXPANSIONS.items():
        if combined in text_cf:
            for lvl in expansion:
                if lvl not in seen:
                    seen.add(lvl)
                    levels.append(lvl)

    # Then match individual labels.
    for label, level in LEVEL_BY_LABEL.items():
        if label == Level.UNKNOWN.value.casefold():
            continue
        if level in seen:
            continue
        if re.search(rf"\b{re.escape(label)}\b", text_cf):
            seen.add(level)
            levels.append(level)

    return levels


def _merge_methods(existing: ScrapedMethod, candidate: ScrapedMethod) -> ScrapedMethod:
    return ScrapedMethod(
        slug=existing.slug,
        title=existing.title if len(existing.title) >= len(candidate.title) else candidate.title,
        subject=existing.subject if existing.subject is not Subject.UNKNOWN else candidate.subject,
        url=existing.url,
    )


# ---------------------------------------------------------------------------
# DB persistence — incremental helpers
# ---------------------------------------------------------------------------


async def _upsert_method(session: AsyncSession, sm: ScrapedMethod) -> str:
    result = await session.exec(select(Method).where(Method.slug == sm.slug))
    existing = result.first()
    if existing:
        logger.debug("Updating method: slug=%s", sm.slug)
        existing.title = sm.title
        existing.subject = sm.subject
        existing.url = sm.url
        await session.flush()
        return existing.id
    else:
        logger.debug("Inserting method: slug=%s", sm.slug)
        db_method = Method(slug=sm.slug, title=sm.title, subject=sm.subject, url=sm.url)
        session.add(db_method)
        await session.flush()
        return db_method.id


async def _upsert_book(session: AsyncSession, method_id: str, sb: ScrapedBook) -> str:
    result = await session.exec(select(Book).where(Book.url == sb.url))
    existing = result.first()
    if existing:
        logger.debug("Updating book: slug=%s", sb.slug)
        existing.title = sb.title
        existing.subject = sb.subject
        existing.edition = sb.edition
        existing.school_years = sb.school_years
        existing.levels = sb.levels
        existing.cover_url = sb.cover_url
        await session.flush()
        return existing.id
    else:
        logger.debug("Inserting book: slug=%s", sb.slug)
        db_book = Book(
            book_id=sb.book_id, slug=sb.slug, title=sb.title, subject=sb.subject,
            method_id=method_id, edition=sb.edition, school_years=sb.school_years,
            levels=sb.levels, cover_url=sb.cover_url, url=sb.url,
        )
        session.add(db_book)
        await session.flush()
        return db_book.id


async def _upsert_chapters(session: AsyncSession, book_id: str, chapters: list[ScrapedChapter]) -> None:
    for sc in chapters:
        result = await session.exec(
            select(BookChapter).where(BookChapter.book_id == book_id, BookChapter.index == sc.index)
        )
        existing = result.first()
        if existing:
            existing.title = sc.title
            existing.toets_url = sc.toets_url
        else:
            session.add(BookChapter(index=sc.index, title=sc.title, toets_url=sc.toets_url, book_id=book_id))


# ---------------------------------------------------------------------------
# AI enrichment
# ---------------------------------------------------------------------------


async def _enrich_book(scraper: ToetsMijScraper, book: ScrapedBook) -> ScrapedBook:
    from app.agents.ai_agent import enrich_book_metadata, needs_enrichment
    if not needs_enrichment(book):
        return book
    try:
        html = scraper.get_text(book.url)
        return await enrich_book_metadata(html, book)
    except Exception as exc:
        logger.warning("Enrichment failed for %s: %s", book.url, exc)
        return book


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    from app.logging_config import configure_logging
    configure_logging()

    parser = argparse.ArgumentParser(description="Scrape lesmethodes, books, and chapters from ToetsMij.")
    parser.add_argument("--methods", action="store_true", help="Fetch all lesmethodes from /lesboeken")
    parser.add_argument("--method-slug", help="Fetch all books + chapters for a specific method slug")
    parser.add_argument("--book-url", help="Fetch chapters for a specific book URL")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON output only, do not save to DB")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    with ToetsMijScraper() as scraper:
        if args.methods:
            methods = scraper.fetch_methods()
            payload: object = [m.model_dump(mode="json") for m in methods]
            if not args.dry_run:
                async def _save_methods() -> None:
                    engine = create_async_engine(settings.database_url)
                    async with AsyncSession(engine) as session:
                        for sm in methods:
                            await _upsert_method(session, sm)
                        await session.commit()
                    logger.info("Saved %d methods", len(methods))
                    await engine.dispose()
                asyncio.run(_save_methods())

        elif args.method_slug:
            methods = scraper.fetch_methods()
            method = next((m for m in methods if m.slug == args.method_slug), None)
            if method is None:
                parser.error(f"Method slug '{args.method_slug}' not found")
                return

            books = scraper.fetch_books_for_method(method)
            saved_books: list[ScrapedBook] = []
            chapters_by_book: dict[str, list[ScrapedChapter]] = {}

            async def _scrape_and_save() -> None:
                engine = create_async_engine(settings.database_url)
                async with AsyncSession(engine) as session:
                    method_id = await _upsert_method(session, method)
                    await session.commit()

                    for book in books:
                        chapters = scraper.fetch_book_chapters(book)
                        enriched = await _enrich_book(scraper, book)
                        saved_books.append(enriched)
                        chapters_by_book[enriched.url] = chapters

                        if not args.dry_run:
                            book_id = await _upsert_book(session, method_id, enriched)
                            await _upsert_chapters(session, book_id, chapters)
                            await session.commit()
                            logger.info("Saved book: %s (%d chapters)", enriched.slug, len(chapters))

                await engine.dispose()

            asyncio.run(_scrape_and_save())

            payload = {
                "method": method.model_dump(mode="json"),
                "books": [b.model_dump(mode="json") for b in saved_books],
                "chapters_by_book_url": {
                    url: [c.model_dump(mode="json") for c in chaps]
                    for url, chaps in chapters_by_book.items()
                },
            }

        elif args.book_url:
            chapters = scraper.fetch_book_chapters(args.book_url)
            payload = [c.model_dump(mode="json") for c in chapters]

        else:
            parser.error("Choose one of: --methods, --method-slug, or --book-url")
            return

    print(json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
