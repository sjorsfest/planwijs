"""Agent for generating lesson preparation todos per LessonPlan."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel
from pydantic_ai import Agent

from app.config import settings


class GeneratedPreparationTodo(BaseModel):
    title: str
    description: str
    why: str


class GeneratedPreparationTodos(BaseModel):
    todos: list[GeneratedPreparationTodo]


@dataclass
class PreparationContext:
    lesson_number: int
    title: str
    learning_objectives: list[str]
    time_sections: list[dict[str, Any]]
    required_materials: list[str]
    teacher_notes: str


_SYSTEM_PROMPT = """\
Je bent een ervaren docent voor het voortgezet onderwijs in Nederland.
Je analyseert een uitgewerkt lesprogramma en bepaalt welke concrete voorbereidingstaken
de docent moet uitvoeren vóór de les kan plaatsvinden.

## Jouw taak
- Analyseer het lesprogramma: lesdoelen, tijdsvakken, benodigde materialen en docentnotities.
- Bepaal welke voorbereidingstaken écht nodig zijn om de les goed te kunnen uitvoeren.
- Denk aan: materialen zoeken of maken, opdrachten printen of klaarzetten, digitale middelen
  voorbereiden, een activiteit uitwerken, afbeeldingen zoeken, etc.
- Genereer alleen taken die concreet en uitvoerbaar zijn. Geen vage algemeenheden.
- Als er geen voorbereiding nodig is, geef dan een lege todos-lijst terug.

## Uitvoer per taak
- title: een korte, actieve taakomschrijving (bijv. "Zoek passende afbeeldingen voor de introductie")
- description: wat er precies gedaan moet worden, met genoeg detail om direct mee aan de slag te gaan
- why: waarom deze taak nodig is voor het welslagen van de les

Schrijf in correct, helder Nederlands.
"""

_preparation_agent: Agent[None, GeneratedPreparationTodos] | None = None


def _configure_env() -> None:
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)


def _get_preparation_agent() -> Agent[None, GeneratedPreparationTodos]:
    global _preparation_agent
    if _preparation_agent is None:
        _configure_env()
        _preparation_agent = cast(
            Agent[None, GeneratedPreparationTodos],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedPreparationTodos,
                system_prompt=_SYSTEM_PROMPT,
            ),
        )
    return _preparation_agent


def _build_prompt(ctx: PreparationContext) -> str:
    objectives = "\n".join(f"  - {o}" for o in ctx.learning_objectives)
    materials = (
        "\n".join(f"  - {m}" for m in ctx.required_materials)
        if ctx.required_materials
        else "  (geen)"
    )
    sections = "\n".join(
        f"  {s['start_min']}-{s['end_min']} min: {s['activity']} "
        f"({s.get('activity_type', '')}) — {s['description']}"
        for s in ctx.time_sections
    )
    return (
        f"Les {ctx.lesson_number}: {ctx.title}\n\n"
        f"Lesdoelen:\n{objectives}\n\n"
        f"Tijdsvakken:\n{sections}\n\n"
        f"Benodigde materialen:\n{materials}\n\n"
        f"Docentnotities:\n{ctx.teacher_notes}\n\n"
        "Genereer de voorbereidingstaken voor deze les."
    )


async def generate_preparation_todos(ctx: PreparationContext) -> list[GeneratedPreparationTodo]:
    prompt = _build_prompt(ctx)
    result = await _get_preparation_agent().run(prompt)
    return result.output.todos
