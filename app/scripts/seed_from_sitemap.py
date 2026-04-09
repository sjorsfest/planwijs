"""Seed Method, Book, BookChapter, BookChapterParagraph from JojoSchool sitemap.

Usage:
    python -m app.scripts.seed_from_sitemap [--dry-run] [--limit N] \
        [--subject SLUG] [--method SLUG]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal, cast

import xml.etree.ElementTree as ET

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent
from sqlmodel import select

from app.config import settings
from app.database import SessionLocal
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.enums import Level, SchoolYear, Subject
from app.models.method import Method
from app.models.subject import Subject as SubjectModel

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://leren.jojoschool.nl/book-sitemap/1.xml"
BASE_URL = "https://leren.jojoschool.nl"

# ── URL classification regexes ────────────────────────────────────────────────

SECTION_RE = re.compile(
    r"^/course/(?P<subject>[^/]+)/books/(?P<method_slug>[^/]+)"
    r"/(?P<book_slug>[^/]+)/chapters/(?P<chapter_slug>[^/]+)"
    r"/sections/(?P<section_slug>[^/]+)/?$"
)
CHAPTER_RE = re.compile(
    r"^/course/(?P<subject>[^/]+)/books/(?P<method_slug>[^/]+)"
    r"/(?P<book_slug>[^/]+)/chapters/(?P<chapter_slug>[^/]+)/?$"
)
BOOK_RE = re.compile(
    r"^/course/(?P<subject>[^/]+)/books/(?P<method_slug>[^/]+)"
    r"/(?P<book_slug>[^/]+)/?$"
)
SLUG_INDEX_RE = re.compile(r"^(?P<index>\d+)-(?P<title>.+)$")

# ── Level patterns: match right-to-left, longest first ───────────────────────

KNOWN_LEVEL_PATTERNS: list[tuple[list[str], list[Level]]] = [
    # 3-token patterns (longest first)
    (["vmbo", "t", "havo"], [Level.VMBO_T, Level.HAVO]),
    # 2-token patterns
    (["vmbo", "thavo"], [Level.VMBO_T, Level.HAVO]),
    (["vmbo", "kgt"], [Level.VMBO_K, Level.VMBO_G, Level.VMBO_T]),
    (["vmbo", "gt"], [Level.VMBO_G, Level.VMBO_T]),
    (["vmbo", "th"], [Level.VMBO_T, Level.HAVO]),  # th = thavo abbreviation
    (["vmbo", "b"], [Level.VMBO_B]),
    (["vmbo", "k"], [Level.VMBO_K]),
    (["vmbo", "g"], [Level.VMBO_G]),
    (["vmbo", "t"], [Level.VMBO_T]),
    (["havo", "vwo"], [Level.HAVO, Level.VWO]),
    # 1-token patterns
    (["mavo"], [Level.VMBO_T]),
    (["gymnasium"], [Level.GYMNASIUM]),
    (["vwogymnasium"], [Level.VWO, Level.GYMNASIUM]),
    (["gymvwo"], [Level.GYMNASIUM, Level.VWO]),
    (["havovwo"], [Level.HAVO, Level.VWO]),
    (["havo"], [Level.HAVO]),
    (["vwo"], [Level.VWO]),
    (["vmbo"], [Level.VMBO_B, Level.VMBO_K, Level.VMBO_G, Level.VMBO_T]),
]

SUBJECT_MAP: dict[str, Subject] = {
    "wiskunde": Subject.WISKUNDE,
    "wiskunde-a": Subject.WISKUNDE_A,
    "wiskunde-b": Subject.WISKUNDE_B,
    "nederlands": Subject.NEDERLANDS,
    "biologie": Subject.BIOLOGIE,
    "scheikunde": Subject.SCHEIKUNDE,
    "natuurkunde": Subject.NATUURKUNDE,
    "engels": Subject.ENGELS,
    "duits": Subject.DUITS,
    "frans": Subject.FRANS,
    "spaans": Subject.SPAANS,
    "economie": Subject.ECONOMIE,
    "aardrijkskunde": Subject.AARDRIJKSKUNDE,
    "geschiedenis": Subject.GESCHIEDENIS,
    "maatschappijleer": Subject.MAATSCHAPPIJLEER,
    "mens-en-maatschappij": Subject.MENS_EN_MAATSCHAPPIJ,
    "levensbeschouwing": Subject.LEVENS_BESCHOUWING,
    "bedrijfseconomie": Subject.BEDRIJFSECONOMIE,
    "grieks": Subject.GRIEKS,
    "latijn": Subject.LATIJN,
    "nask-science": Subject.NASK_SCIENCE,
    "maw": Subject.MAW,
}
LEGACY_TO_SUBJECT_SLUG: dict[Subject, str] = {legacy: slug for slug, legacy in SUBJECT_MAP.items()}

YEAR_MAP: dict[str, SchoolYear] = {
    "1": SchoolYear.YEAR_1,
    "2": SchoolYear.YEAR_2,
    "3": SchoolYear.YEAR_3,
    "4": SchoolYear.YEAR_4,
    "5": SchoolYear.YEAR_5,
    "6": SchoolYear.YEAR_6,
}


# ── Intermediate data structures ──────────────────────────────────────────────


@dataclass
class ParsedUrl:
    url: str
    resource_type: Literal["book", "chapter", "section"]
    subject_slug: str
    method_slug: str
    book_slug: str
    chapter_slug: str | None = None
    section_slug: str | None = None
    chapter_index: int | None = None
    chapter_title_slug: str | None = None
    section_index: int | None = None
    section_title_slug: str | None = None
    raw_title_slug: str = ""
    raw_level_tokens: list[str] = field(default_factory=list)
    # digits sandwiched BETWEEN title and level  →  school years
    raw_year_tokens: list[str] = field(default_factory=list)
    # digits that appeared AFTER the level (at the very end of the slug)  →  edition
    raw_edition_tokens: list[str] = field(default_factory=list)

    @property
    def book_group_key(self) -> str:
        return f"{self.subject_slug}::{self.method_slug}::{self.book_slug}"


@dataclass
class BookGroup:
    subject_slug: str
    method_slug: str
    book_slug: str
    book_url: str | None
    raw_title_slug: str
    raw_level_tokens: list[str]
    # digits sandwiched BETWEEN title and level  →  school years
    raw_year_tokens: list[str]
    # digits that appeared AFTER the level (at the very end of the slug)  →  edition
    raw_edition_tokens: list[str]
    # chapter_index -> raw title slug
    chapters: dict[int, str] = field(default_factory=dict)
    # (chapter_index, section_index) -> raw title slug
    paragraphs: dict[tuple[int, int], str] = field(default_factory=dict)


# ── LLM fallback (only when deterministic parsing yields Unknown) ─────────────


class LLMBookMetadata(BaseModel):
    subject: Subject | None = None
    school_years: list[SchoolYear] | None = None
    edition: str | None = None


_fallback_agent: Agent[None, LLMBookMetadata] | None = None


def _get_fallback_agent() -> Agent[None, LLMBookMetadata]:
    global _fallback_agent
    if _fallback_agent is None:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
        _fallback_agent = cast(
            Agent[None, LLMBookMetadata],
            Agent(
                "openrouter:google/gemini-2.5-flash-lite",
                output_type=LLMBookMetadata,
                system_prompt=(
                    "You extract structured metadata for Dutch secondary school textbooks.\n"
                    "You receive a URL path and the stripped HTML of the book page.\n\n"
                    "## Your job\n"
                    "Return three fields for the book: subject, school_years, edition.\n"
                    "Use the page content as the primary source. The URL slug is a fallback.\n\n"
                    "## Subject\n"
                    "The subject_slug in the URL is a lowercased Dutch school subject:\n"
                    "  wiskunde, biologie, scheikunde, natuurkunde, engels, duits, etc.\n\n"
                    "## School years\n"
                    "The school year is the year of secondary school (1–6). NOT the edition number.\n"
                    "The page usually shows it explicitly, e.g. '1 vmbo-kgt · 4e editie' → school_year=1.\n"
                    "In the slug, digits sandwiched between the title and the level are school years.\n"
                    "  Example: flex-boek-1-vmbo-kgt-4 → school_year=1  (the trailing 4 is the edition)\n"
                    "  Example: leerboek-4-vmbo-kgt → school_year=4\n\n"
                    "## Edition\n"
                    "The edition is a version/print number, often shown on the page as '4e editie', '2022', etc.\n"
                    "A trailing digit at the very end of the slug (after the education level) is typically an edition.\n"
                    "  Example: flex-boek-1-vmbo-kgt-4 → edition='4e editie'  (trailing 4 = edition)\n"
                    "Return it as a short string (e.g. '4e editie', '2022') or null if not present.\n\n"
                    "## Rules\n"
                    "- The page content is the authoritative source. Trust it over the slug.\n"
                    "- Return null for any field you cannot determine confidently.\n"
                    "- Do not invent information not found on the page or in the slug."
                ),
            ),
        )
    return _fallback_agent


async def _fetch_page_text(url: str) -> str | None:
    """Fetch a book page and return its stripped text content (no truncation)."""
    try:
        import lxml.html as lxml_html
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        doc = lxml_html.fromstring(resp.content)
        for el in doc.xpath("//script | //style | //nav | //footer | //head | //header"):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
        text = doc.text_content()
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as exc:
        logger.debug("Page fetch failed for %s: %s", url, exc)
        return None


async def _llm_normalize_book(
    group: BookGroup,
) -> tuple[Subject, list[Level], list[SchoolYear], str | None]:
    """Call the LLM with only the raw slug and page content — no pre-parsed hints."""
    book_url = group.book_url or (
        f"{BASE_URL}/course/{group.subject_slug}/books/{group.method_slug}/{group.book_slug}"
    )
    page_text = await _fetch_page_text(book_url)

    prompt = (
        f"URL path: /course/{group.subject_slug}/books/{group.method_slug}/{group.book_slug}\n"
    )
    if page_text:
        prompt += f"\nPage content (stripped HTML):\n{page_text}"

    # Levels always resolved deterministically from the slug
    levels = _resolve_levels(group.raw_level_tokens)
    fallback_subject = SUBJECT_MAP.get(group.subject_slug, Subject.UNKNOWN)
    try:
        result = await asyncio.wait_for(_get_fallback_agent().run(prompt), timeout=30)
        meta = result.output
        subject = meta.subject if meta.subject is not None else fallback_subject
        school_years = meta.school_years if meta.school_years is not None else [SchoolYear.UNKNOWN]
        edition = meta.edition
        return subject, levels, school_years, edition
    except Exception as exc:
        logger.warning("  LLM normalization failed for '%s': %s", group.book_slug, exc)
        det_years = _resolve_years(group.raw_year_tokens)
        return fallback_subject, levels, det_years, None


# ── Deterministic helpers ─────────────────────────────────────────────────────


def _humanize(slug: str) -> str:
    """Convert a URL slug to a display title: replace hyphens with spaces, capitalize first letter."""
    return slug.replace("-", " ").capitalize()


def _parse_slug_index(slug: str) -> tuple[int | None, str]:
    m = SLUG_INDEX_RE.match(slug)
    if m:
        return int(m.group("index")), m.group("title")
    return None, slug


def _is_noise_token(t: str) -> bool:
    """Return True for trailing tokens that are not titles or levels.

    Covers: the keyword 'release', any integer greater than 6 (year numbers like
    2020/2022, edition codes like 50/51/60/202150, multi-year groups like 31/45/456).
    """
    if t == "release":
        return True
    if t.isdigit() and int(t) > 6:
        return True
    return False


def _parse_book_slug(book_slug: str) -> tuple[str, list[str], list[str], list[str]]:
    """Split book slug right-to-left into (title_slug, level_tokens, year_tokens, edition_tokens).

    Iteratively strips edition digits (1-6) and noise tokens (large numbers, 'release')
    from the right until stable, then matches the level pattern. This handles slugs like:
        flex-boek-1-vmbo-kgt-4          → year=[1], level=vmbo-kgt, edition=[4]
        leerwerkboek-2a-2-havo-vwo-51   → year=[2], level=havo-vwo, edition=[]  (51 = noise)
        leerboek-1-vmbo-kgt-release-2020-5 → year=[1], level=vmbo-kgt, edition=[5]
    """
    tokens = [t for t in book_slug.split("-") if t]  # drop empty tokens from double dashes

    edition_tokens: list[str] = []

    # Alternately strip edition digits (1-6) and noise tokens until nothing more changes.
    # This handles cases where edition comes after noise (e.g. "release-2020-5").
    changed = True
    while changed and tokens:
        changed = False
        while tokens and tokens[-1].isdigit() and 1 <= int(tokens[-1]) <= 6:
            edition_tokens.insert(0, tokens.pop())
            changed = True
        while tokens and _is_noise_token(tokens[-1]):
            tokens.pop()
            changed = True

    # Match longest known level suffix
    level_tokens: list[str] = []
    for pattern, _ in KNOWN_LEVEL_PATTERNS:
        n = len(pattern)
        if len(tokens) >= n and tokens[-n:] == pattern:
            level_tokens = pattern
            tokens = tokens[:-n]
            break

    # Strip digits (1-6) sandwiched between title and level — these are school years
    year_tokens: list[str] = []
    while tokens and tokens[-1].isdigit() and 1 <= int(tokens[-1]) <= 6:
        year_tokens.insert(0, tokens.pop())

    raw_title = "-".join(tokens) if tokens else book_slug
    return raw_title, level_tokens, year_tokens, edition_tokens


def _resolve_levels(tokens: list[str]) -> list[Level]:
    for pattern, levels in KNOWN_LEVEL_PATTERNS:
        if pattern == tokens:
            return levels
    return [Level.UNKNOWN]


def _resolve_years(tokens: list[str]) -> list[SchoolYear]:
    resolved = [YEAR_MAP[t] for t in tokens if t in YEAR_MAP]
    return resolved if resolved else [SchoolYear.UNKNOWN]


def _classify_url(url: str) -> ParsedUrl | None:
    path = url.removeprefix(BASE_URL).rstrip("/")
    for regex, rtype in [
        (SECTION_RE, "section"),
        (CHAPTER_RE, "chapter"),
        (BOOK_RE, "book"),
    ]:
        m = regex.match(path)
        if not m:
            continue
        g = m.groupdict()
        raw_title, level_tokens, year_tokens, edition_tokens = _parse_book_slug(g["book_slug"])
        p = ParsedUrl(
            url=url,
            resource_type=rtype,  # type: ignore[arg-type]
            subject_slug=g["subject"],
            method_slug=g["method_slug"],
            book_slug=g["book_slug"],
            chapter_slug=g.get("chapter_slug"),
            section_slug=g.get("section_slug"),
            raw_title_slug=raw_title,
            raw_level_tokens=level_tokens,
            raw_year_tokens=year_tokens,
            raw_edition_tokens=edition_tokens,
        )
        if g.get("chapter_slug"):
            p.chapter_index, p.chapter_title_slug = _parse_slug_index(g["chapter_slug"])
        if g.get("section_slug"):
            p.section_index, p.section_title_slug = _parse_slug_index(g["section_slug"])
        return p
    logger.debug("Unmatched URL: %s", url)
    return None


# ── Sitemap fetch ─────────────────────────────────────────────────────────────


async def _fetch_urls() -> list[str]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(SITEMAP_URL)
        resp.raise_for_status()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(resp.content)
    return [
        loc.text.strip()
        for loc in root.findall(".//sm:loc", ns)
        if loc.text and loc.text.strip()
    ]


# ── Grouping ──────────────────────────────────────────────────────────────────


def _build_groups(parsed: list[ParsedUrl]) -> dict[str, BookGroup]:
    groups: dict[str, BookGroup] = {}
    for p in parsed:
        key = p.book_group_key
        if key not in groups:
            groups[key] = BookGroup(
                subject_slug=p.subject_slug,
                method_slug=p.method_slug,
                book_slug=p.book_slug,
                book_url=None,
                raw_title_slug=p.raw_title_slug,
                raw_level_tokens=p.raw_level_tokens,
                raw_year_tokens=p.raw_year_tokens,
                raw_edition_tokens=p.raw_edition_tokens,
            )
        g = groups[key]
        if p.resource_type == "book":
            g.book_url = p.url
        elif p.resource_type == "chapter" and p.chapter_index is not None:
            g.chapters.setdefault(p.chapter_index, p.chapter_title_slug or "")
        elif p.resource_type == "section":
            if p.chapter_index is not None and p.section_index is not None:
                g.paragraphs.setdefault((p.chapter_index, p.section_index), p.section_title_slug or "")
                # Derive chapter from section parent if not already present
                g.chapters.setdefault(p.chapter_index, p.chapter_title_slug or "")
    return groups


# ── Database upserts ──────────────────────────────────────────────────────────


async def _upsert_method(
    session, slug: str, title: str, subject: Subject, url: str
) -> Method:
    result = await session.execute(select(Method).where(Method.slug == slug))
    existing = result.scalars().first()
    if existing:
        existing.title = title
        existing.subject = subject
        existing.url = url
        return existing
    obj = Method(slug=slug, title=title, subject=subject, url=url)
    session.add(obj)
    return obj


def _subject_slug_for_book(group_subject_slug: str, subject: Subject) -> str:
    return LEGACY_TO_SUBJECT_SLUG.get(subject, group_subject_slug)


async def _subject_id_for_slug(session, subject_slug: str) -> str | None:
    result = await session.execute(
        select(SubjectModel.id).where(SubjectModel.slug == subject_slug)
    )
    return result.scalars().first()


async def _upsert_book(
    session,
    method_id: str,
    group: BookGroup,
    subject: Subject,
    levels: list[Level],
    school_years: list[SchoolYear],
    edition: str | None,
) -> Book:
    url = group.book_url or (
        f"{BASE_URL}/course/{group.subject_slug}/books/{group.method_slug}/{group.book_slug}"
    )
    title = _humanize(group.raw_title_slug) if group.raw_title_slug else _humanize(group.book_slug)

    result = await session.execute(select(Book).where(Book.slug == group.book_slug))
    existing = result.scalars().first()
    subject_slug = _subject_slug_for_book(group.subject_slug, subject)
    subject_id = await _subject_id_for_slug(session, subject_slug)
    if subject_id is None:
        raise RuntimeError(
            f"No subject found for slug '{subject_slug}' while processing book '{group.book_slug}'"
        )
    if existing:
        existing.title = title
        existing.subject_id = subject_id
        existing.method_id = method_id
        existing.levels = levels
        existing.school_years = school_years
        existing.edition = edition
        existing.url = url
        return existing
    obj = Book(
        slug=group.book_slug,
        title=title,
        subject_id=subject_id,
        method_id=method_id,
        levels=levels,
        school_years=school_years,
        edition=edition,
        url=url,
    )
    session.add(obj)
    return obj


async def _upsert_chapter(session, book_id: str, index: int, title: str) -> BookChapter:
    result = await session.execute(
        select(BookChapter).where(
            BookChapter.book_id == book_id,
            BookChapter.index == index,
        )
    )
    existing = result.scalars().first()
    if existing:
        existing.title = title
        return existing
    obj = BookChapter(index=index, title=title, book_id=book_id)
    session.add(obj)
    return obj


async def _upsert_paragraph(
    session, chapter_id: str, index: int, title: str
) -> BookChapterParagraph:
    result = await session.execute(
        select(BookChapterParagraph).where(
            BookChapterParagraph.chapter_id == chapter_id,
            BookChapterParagraph.index == index,
        )
    )
    existing = result.scalars().first()
    if existing:
        existing.title = title
        return existing
    obj = BookChapterParagraph(index=index, title=title, chapter_id=chapter_id)
    session.add(obj)
    return obj


# ── Pipeline ──────────────────────────────────────────────────────────────────


async def run(
    dry_run: bool = False,
    limit: int | None = None,
    subject_filter: str | None = None,
    method_filter: str | None = None,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    logger.info("Fetching sitemap: %s", SITEMAP_URL)
    raw_urls = await _fetch_urls()
    logger.info("Found %d URLs in sitemap", len(raw_urls))

    parsed = [p for u in raw_urls if (p := _classify_url(u)) is not None]
    logger.info("Classified %d URLs", len(parsed))

    if subject_filter:
        parsed = [p for p in parsed if p.subject_slug == subject_filter]
        logger.info("After --subject '%s': %d URLs", subject_filter, len(parsed))

    if method_filter:
        parsed = [p for p in parsed if p.method_slug == method_filter]
        logger.info("After --method '%s': %d URLs", method_filter, len(parsed))

    groups = _build_groups(parsed)
    logger.info("Built %d book groups", len(groups))

    group_list = list(groups.values())
    if limit:
        group_list = group_list[:limit]
        logger.info("Limited to %d book groups", len(group_list))

    # Track already-created methods across book groups (slug -> id)
    seen_methods: dict[str, str] = {}

    for i, group in enumerate(group_list, 1):
        logger.info(
            "[%d/%d] %s / %s / %s  (%d chapters, %d paragraphs)",
            i,
            len(group_list),
            group.subject_slug,
            group.method_slug,
            group.book_slug,
            len(group.chapters),
            len(group.paragraphs),
        )

        book_title = _humanize(group.raw_title_slug) if group.raw_title_slug else _humanize(group.book_slug)
        method_title = _humanize(group.method_slug)
        subject, levels, school_years, edition = await _llm_normalize_book(group)

        chapter_titles = {
            idx: (_humanize(slug) if slug else f"Hoofdstuk {idx}")
            for idx, slug in group.chapters.items()
        }
        para_titles = {
            (ch_idx, sec_idx): (_humanize(slug) if slug else f"Paragraaf {sec_idx}")
            for (ch_idx, sec_idx), slug in group.paragraphs.items()
        }

        if dry_run:
            print(f"\n--- {group.book_slug} ---")
            print(f"  Method : {group.method_slug!r} -> {method_title!r}  subject={subject}")
            print(f"  Book   : {book_title!r}  levels={levels}  years={school_years}")
            for ch_idx, ch_title in sorted(chapter_titles.items()):
                print(f"    [{ch_idx}] {ch_title}")
                for (ci, si), p_title in sorted(para_titles.items()):
                    if ci == ch_idx:
                        print(f"        [{si}] {p_title}")
            continue

        # Persist
        async with SessionLocal() as session:
            method_key = f"{group.subject_slug}::{group.method_slug}"
            if method_key not in seen_methods:
                method_url = group.book_url or (
                    f"{BASE_URL}/course/{group.subject_slug}/books/{group.method_slug}"
                )
                method = await _upsert_method(
                    session,
                    slug=group.method_slug,
                    title=method_title,
                    subject=subject,
                    url=method_url,
                )
                await session.commit()
                await session.refresh(method)
                seen_methods[method_key] = method.id

            method_id = seen_methods[method_key]

            book = await _upsert_book(session, method_id, group, subject, levels, school_years, edition)
            await session.commit()
            await session.refresh(book)

            for ch_idx, ch_title in chapter_titles.items():
                chapter = await _upsert_chapter(session, book.id, ch_idx, ch_title)
                await session.commit()
                await session.refresh(chapter)

                for (ci, si), p_title in para_titles.items():
                    if ci == ch_idx:
                        await _upsert_paragraph(session, chapter.id, si, p_title)

            await session.commit()
            logger.info("  Saved: %s", group.book_slug)

    logger.info("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed database from JojoSchool sitemap"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Process only N book groups")
    parser.add_argument("--subject", default=None, metavar="SLUG", help="Filter by subject slug (e.g. wiskunde)")
    parser.add_argument("--method", default=None, metavar="SLUG", help="Filter by method slug")
    args = parser.parse_args()

    asyncio.run(
        run(
            dry_run=args.dry_run,
            limit=args.limit,
            subject_filter=args.subject,
            method_filter=args.method,
        )
    )


if __name__ == "__main__":
    main()
