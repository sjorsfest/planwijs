"""Agent that applies structured field-level feedback to an individual lesson plan."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from ._agent_base import MODEL_NAME, configure_env

# The valid field names that can be targeted by feedback on a lesson plan
LESSON_FIELD_NAMES = {
    "title",
    "learning_objectives",
    "time_sections",
    "required_materials",
    "teacher_notes",
}


class LessonFeedbackRevisionResult(BaseModel):
    """The LLM returns only the fields it revised, as a JSON object."""

    updated_fields: dict[str, Any] = Field(
        description="A dict mapping field_name -> new value for each field that was revised."
    )


_LESSON_FEEDBACK_SYSTEM_PROMPT = """\
Je bent een expert in didactiek en lespraktijk in het voortgezet onderwijs. Je taak is het \
verwerken van gerichte feedback van een docent op een bestaand uitgewerkt lesplan.

Je ontvangt:
1. Het huidige lesplan als JSON
2. Een lijst van feedbackitems, elk met:
   - field_name: het veld van het lesplan waarop de feedback betrekking heeft
   - specific_part: een specificatie van welk onderdeel binnen dat veld (kan leeg zijn)
   - user_feedback: de feedback van de docent

INSTRUCTIES:
- Pas ALLEEN de velden aan waarvoor feedback is gegeven.
- Als feedback op een veld (bijv. time_sections) invloed heeft op gerelateerde velden \
(bijv. required_materials), pas die gerelateerde velden dan OOK aan zodat alles consistent blijft.
- Behoud alle velden waarvoor geen feedback is gegeven exact zoals ze zijn.
- Houd je aan de exacte datastructuur van elk veld (zie het huidige lesplan als referentie).
- De tijdsvakken moeten exact optellen tot de totale lesduur.
- Schrijf in helder, professioneel Nederlands.
- Retourneer ALLEEN de gewijzigde velden in updated_fields, niet het volledige lesplan.

VELDENSTRUCTUUR (ter referentie):
- title: string
- learning_objectives: list[string]
- time_sections: list[object] met per item: start_min (int), end_min (int), activity (string), \
description (string), activity_type (een van: introduction, repetition, instruction, activity, \
discussion, assessment, closure)
- required_materials: list[string]
- teacher_notes: string (concrete tips: misconcepties, differentiatiesuggesties, extra \
ondersteuning en aandachtspunten)
"""

_lesson_feedback_agent: Agent[None, LessonFeedbackRevisionResult] | None = None


def get_lesson_feedback_agent() -> Agent[None, LessonFeedbackRevisionResult]:
    global _lesson_feedback_agent
    if _lesson_feedback_agent is None:
        configure_env()
        _lesson_feedback_agent = cast(
            Agent[None, LessonFeedbackRevisionResult],
            Agent(
                MODEL_NAME,
                output_type=LessonFeedbackRevisionResult,
                system_prompt=_LESSON_FEEDBACK_SYSTEM_PROMPT,
            ),
        )
    return _lesson_feedback_agent


def build_lesson_feedback_prompt(
    lesson_data: dict[str, Any],
    feedback_items: list[dict[str, str]],
) -> str:
    """Build the prompt for the lesson feedback revision agent."""
    lesson_json = json.dumps(lesson_data, ensure_ascii=False, indent=2)
    feedback_lines = []
    for item in feedback_items:
        line = f"- Veld: {item['field_name']}"
        if item.get("specific_part"):
            line += f" | Onderdeel: {item['specific_part']}"
        line += f"\n  Feedback: {item['user_feedback']}"
        feedback_lines.append(line)
    feedback_block = "\n".join(feedback_lines)

    return f"""\
### HUIDIG LESPLAN
```json
{lesson_json}
```

### FEEDBACK VAN DE DOCENT
{feedback_block}

Verwerk de bovenstaande feedback. Retourneer in updated_fields ALLEEN de velden die je hebt \
aangepast. Zorg dat gerelateerde velden (zoals required_materials bij wijziging van time_sections) \
ook worden meegenomen als dat nodig is voor consistentie.
"""


async def apply_lesson_feedback(
    lesson_data: dict[str, Any],
    feedback_items: list[dict[str, str]],
) -> dict[str, Any]:
    """Run the lesson feedback agent and return the updated fields dict."""
    prompt = build_lesson_feedback_prompt(lesson_data, feedback_items)
    result = await get_lesson_feedback_agent().run(prompt)
    return result.output.updated_fields
