from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel as PydanticBase
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings
from app.models.enums import Level, SchoolYear, Subject

if TYPE_CHECKING:
    from app.scraper import ScrapedBook

logger = logging.getLogger(__name__)


class EnrichedFields(PydanticBase):
    subject: Subject
    levels: list[Level]
    school_years: list[SchoolYear] = []


_model = OpenAIChatModel(
    "minimax/minimax-m2.5",
    provider=OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    ),
)

enrichment_agent = Agent(
    model=_model,
    output_type=EnrichedFields,
    system_prompt=(
        "You are a Dutch educational content classifier. "
        "Given a book title and page content from a Dutch secondary school website, "
        "extract the school subject, education levels, and school years. "
        "Use only values from the provided enums. "
        "For subject, pick the single best match (e.g. Wiskunde, Geschiedenis). "
        "For levels, list all that apply (e.g. Havo, Vwo). "
        "For school_years, list all years mentioned (e.g. ['3e jaar', '4e jaar']). "
        "If you cannot determine a value with confidence, use 'Unknown' for subject or empty lists."
    ),
)


async def enrich_book_metadata(html_text: str, book: ScrapedBook) -> ScrapedBook:
    """Call the AI agent to fill in UNKNOWN fields on a ScrapedBook."""
    logger.info("Enriching book metadata: slug=%s title=%r", book.slug, book.title)
    prompt = (
        f"Book title: {book.title}\n"
        f"Method title: {book.method_slug or ''}\n"
        f"Current subject: {book.subject.value}\n"
        f"Current levels: {[l.value for l in book.levels]}\n"
        f"Current school_years: {[y.value for y in book.school_years]}\n\n"
        f"Page content (first 4000 chars):\n{html_text[:4000]}"
    )
    result = await enrichment_agent.run(prompt)
    enriched = cast(EnrichedFields, result.output)
    logger.info(
        "Enrichment result for %r: subject=%s levels=%s school_years=%s",
        book.title,
        enriched.subject.value,
        [l.value for l in enriched.levels],
        [y.value for y in enriched.school_years],
    )
    return book.model_copy(
        update={
            "subject": enriched.subject,
            "levels": enriched.levels,
            "school_years": enriched.school_years,
        }
    )


def needs_enrichment(book: ScrapedBook) -> bool:
    """Return True if the book has any UNKNOWN fields worth enriching."""
    return (
        book.subject is Subject.UNKNOWN
        or not book.levels
        or not book.school_years
    )
