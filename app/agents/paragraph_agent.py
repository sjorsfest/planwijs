"""
Two-agent pipeline for finding and structuring book chapter paragraphs.

1. Research agent  — perplexity/sonar-pro (built-in web search)
   Searches the web and returns raw findings about paragraph structure.

2. Structure agent — minimax/minimax-m2.5
   Reads the raw findings and maps them strictly onto the ParagraphResult
   data model. Never invents data.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel as PydanticBase
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.book_chapter import BookChapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class ScrapedParagraph(PydanticBase):
    index: int
    title: str
    synopsis: Optional[str] = None  # 1-3 sentences derived from source, or None


class ParagraphResult(PydanticBase):
    paragraphs: list[ScrapedParagraph]  # empty if nothing reliable was found


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_perplexity = OpenAIChatModel(
    "perplexity/sonar-pro",
    provider=OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    ),
)

_minimax = OpenAIChatModel(
    "minimax/minimax-m2.5",
    provider=OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    ),
)


# ---------------------------------------------------------------------------
# Agent 1 — Perplexity: web research
# ---------------------------------------------------------------------------

research_agent: Agent[None, str] = Agent(
    model=_perplexity,
    output_type=str,
    system_prompt=(
        "Geef een volledig overzicht van de genummerde paragrafen (nummer + titel) "
        "van het gevraagde hoofdstuk, inclusief een korte beschrijving per paragraaf indien beschikbaar. "
        "Vermeld ook je bronnen. "
        "De officiële uitgever heeft deze informatie doorgaans niet online staan, maar zoek op samenvattings- en "
        "studie-hulpsites zoals leren.jojoschool.nl (zeer aanbevolen — bevat paragraafindelingen van veel Nederlandse schoolboeken), "
        "scholieren.com, samengevat.nl, stuvia.com, bioplek.org, oefenweb.nl of vergelijkbare "
        "sites waar leerlingen samenvattingen delen — daar staan de paragraafindelingen vrijwel altijd in. "
        "Zoek dus actief op leren.jojoschool.nl voor dit hoofdstuk. "
        "Als je geen betrouwbare paragraafindeling kunt vinden, zeg dat dan expliciet — verzin niets."
    ),
)


# ---------------------------------------------------------------------------
# Agent 2 — Minimax: structure the findings into the data model
# ---------------------------------------------------------------------------

structure_agent: Agent[None, ParagraphResult] = Agent(  # type: ignore[assignment]
    model=_minimax,
    output_type=ParagraphResult,
    system_prompt=(
        "You receive raw research findings about a Dutch secondary school textbook chapter. "
        "Your job is to extract the paragraph structure and return it as structured data. "
        "\n\n"
        "STRICT RULES:\n"
        "- Only include paragraphs that are explicitly mentioned in the findings.\n"
        "- `index` must be the paragraph number as an integer (e.g. paragraph 3.2 → index 2, or use the ordinal if no sub-number).\n"
        "- `title` must be taken verbatim (or closely paraphrased) from the source — do not invent titles.\n"
        "- `synopsis` must be a 1-3 sentence paraphrase of what the findings say about that paragraph. "
        "If the findings contain no descriptive text for a paragraph, set synopsis to null.\n"
        "- If the findings say nothing reliable was found, return paragraphs=[].\n"
        "- Do not mix up chapters. Only return paragraphs for the exact chapter described."
    ),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def find_paragraphs(chapter: BookChapter, book: Book) -> ParagraphResult:
    """Run the two-agent pipeline to find and structure paragraphs for a chapter."""
    levels = [lvl if isinstance(lvl, str) else lvl.value for lvl in book.levels]

    level_str = f"{'/'.join(levels)}-niveau" if levels else ""
    edition_str = book.edition or ""
    research_prompt = (
        f"wat zijn de paragrafen van Hoofdstuk {chapter.index}: {chapter.title}"
        f" in {book.title}"
        + (f" {edition_str}" if edition_str else "")
        + (f" ({level_str})" if level_str else "")
        + "?"
    )
    logger.info("Research query: %s", research_prompt)

    logger.info(
        "Research agent starting — book=%r chapter=%d %r",
        book.title, chapter.index, chapter.title,
    )

    research_result = await research_agent.run(research_prompt)
    raw_findings = research_result.output

    logger.info(
        "Research agent done — %d chars of findings for chapter %d of %r",
        len(raw_findings), chapter.index, book.title,
    )
    logger.debug("Raw findings:\n%s", raw_findings)

    structure_prompt = (
        f"Structure the following research findings into the paragraph data model.\n\n"
        f"Context — Book: {book.title}, Chapter {chapter.index}: {chapter.title}\n\n"
        f"Research findings:\n{raw_findings}"
    )

    structure_result = await structure_agent.run(structure_prompt)
    paragraphs = structure_result.output.paragraphs

    logger.info(
        "Structure agent done — %d paragraph(s) extracted for chapter %d of %r",
        len(paragraphs), chapter.index, book.title,
    )

    return structure_result.output
