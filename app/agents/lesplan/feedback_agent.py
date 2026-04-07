"""Agent that applies structured field-level feedback to a lesplan overview."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env
from .types import GeneratedLesplanOverview
from .utils import _build_context_block

# The valid field names that can be targeted by feedback
OVERVIEW_FIELD_NAMES = {
    "title",
    "series_summary",
    "series_themes",
    "learning_goals",
    "key_knowledge",
    "recommended_approach",
    "learning_progression",
    "lesson_outline",
    "goal_coverage",
    "knowledge_coverage",
    "approval_readiness",
    "didactic_approach",
}


class FeedbackRevisionResult(BaseModel):
    """The LLM returns only the fields it revised, as a JSON object."""

    updated_fields: dict[str, Any] = Field(
        description="A dict mapping field_name -> new value for each field that was revised."
    )


_FEEDBACK_SYSTEM_PROMPT = """\
Je bent een expert in didactiek en curriculumontwikkeling. Je taak is het verwerken van \
gerichte feedback van een docent op een bestaand lesplan-overzicht.

Je ontvangt:
1. De volledige context (boek, klas, paragrafen, etc.)
2. Het huidige lesplan-overzicht als JSON
3. Een lijst van feedbackitems, elk met:
   - field_name: het veld van het overzicht waarop de feedback betrekking heeft
   - specific_part: een specificatie van welk onderdeel binnen dat veld (kan leeg zijn)
   - user_feedback: de feedback van de docent

INSTRUCTIES:
- Pas ALLEEN de velden aan waarvoor feedback is gegeven.
- Als feedback op een veld (bijv. learning_goals) invloed heeft op gerelateerde velden \
(bijv. goal_coverage), pas die gerelateerde velden dan OOK aan zodat alles consistent blijft.
- Behoud alle velden waarvoor geen feedback is gegeven exact zoals ze zijn.
- Houd je aan de exacte datastructuur van elk veld (zie het huidige overzicht als referentie).
- Schrijf in helder, professioneel Nederlands.
- Retourneer ALLEEN de gewijzigde velden in updated_fields, niet het volledige overzicht.

VELDENSTRUCTUUR (ter referentie):
- title: string
- series_summary: string (markdown)
- series_themes: list[string]
- learning_goals: list[string]
- key_knowledge: list[string]
- recommended_approach: string
- learning_progression: string
- lesson_outline: list[object] met per item: lesson_number, subject_focus, description, \
teaching_approach_hint, builds_on, concept_tags, lesson_intention, end_understanding, \
sequence_rationale, builds_on_lessons, paragraph_indices
- goal_coverage: list[object] met per item: goal, lesson_numbers, rationale
- knowledge_coverage: list[object] met per item: knowledge, lesson_numbers, rationale
- approval_readiness: object met: ready_for_approval, rationale, checklist, open_questions
- didactic_approach: string
"""

_feedback_agent: Agent[None, FeedbackRevisionResult] | None = None


def get_feedback_agent() -> Agent[None, FeedbackRevisionResult]:
    global _feedback_agent
    if _feedback_agent is None:
        configure_env()
        _feedback_agent = cast(
            Agent[None, FeedbackRevisionResult],
            Agent(
                MODEL_NAME,
                output_type=FeedbackRevisionResult,
                system_prompt=_FEEDBACK_SYSTEM_PROMPT,
            ),
        )
    return _feedback_agent


def build_feedback_prompt(
    ctx: Any,
    current_overview: GeneratedLesplanOverview,
    feedback_items: list[dict[str, str]],
) -> str:
    """Build the prompt for the feedback revision agent."""
    context_block = _build_context_block(ctx)
    overview_json = json.dumps(
        current_overview.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )
    feedback_lines = []
    for item in feedback_items:
        line = f"- Veld: {item['field_name']}"
        if item.get("specific_part"):
            line += f" | Onderdeel: {item['specific_part']}"
        line += f"\n  Feedback: {item['user_feedback']}"
        feedback_lines.append(line)
    feedback_block = "\n".join(feedback_lines)

    return f"""\
{context_block}

### HUIDIG LESPLAN-OVERZICHT
```json
{overview_json}
```

### FEEDBACK VAN DE DOCENT
{feedback_block}

Verwerk de bovenstaande feedback. Retourneer in updated_fields ALLEEN de velden die je hebt \
aangepast. Zorg dat gerelateerde velden (zoals goal_coverage bij wijziging van learning_goals) \
ook worden meegenomen als dat nodig is voor consistentie.
"""


async def apply_feedback(
    ctx: Any,
    current_overview: GeneratedLesplanOverview,
    feedback_items: list[dict[str, str]],
) -> dict[str, Any]:
    """Run the feedback agent and return the updated fields dict."""
    prompt = build_feedback_prompt(ctx, current_overview, feedback_items)
    result = await get_feedback_agent().run(prompt)
    return result.output.updated_fields
