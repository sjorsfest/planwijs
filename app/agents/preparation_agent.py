"""Agent for generating lesson preparation todos per LessonPlan."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.config import settings


class GeneratedPreparationTodo(BaseModel):
    title: str = ""
    description: str = ""
    why: str = ""


class GeneratedPreparationTodos(BaseModel):
    todos: list[GeneratedPreparationTodo] = Field(default_factory=list)


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
- Verplicht: zet "benodigde materialen" actief om naar voorbereidingstaken zodra er iets
  gemaakt, verzameld, geprint, gekopieerd of digitaal klaargezet moet worden.
- Concreet:
  - "opdrachtblad / werkblad / carousel / tijdlijn / quiz / bronblad" => taak om te maken of te verzamelen.
  - "afbeelding / bron / kaart / video / presentatie / digibord" => taak om materiaal te zoeken en klaar te zetten.
  - "check / aandachtspunt / zorg dat" in docentnotities => taak om deze voorbereiding vooraf te borgen.
- Alleen als er aantoonbaar géén voorbereiding nodig is, geef een lege todos-lijst terug.

## Uitvoer per taak
- title: een korte, actieve taakomschrijving (bijv. "Zoek passende afbeeldingen voor de introductie")
- description: wat er precies gedaan moet worden, met genoeg detail om direct mee aan de slag te gaan
- why: waarom deze taak nodig is voor het welslagen van de les

Schrijf in correct, helder Nederlands.
"""


logger = logging.getLogger(__name__)

_preparation_agent: Agent[None, GeneratedPreparationTodos] | None = None

_MATERIAL_PREP_KEYWORDS = (
    "opdracht",
    "werkblad",
    "bron",
    "kaart",
    "afbeeld",
    "presentatie",
    "slide",
    "digibord",
    "video",
    "quiz",
    "carrousel",
    "carousel",
    "tijdlijn",
    "print",
    "kopie",
)

_NOTE_PREP_KEYWORDS = (
    "check",
    "let op",
    "aandachtspunt",
    "zorg dat",
    "voorbereid",
    "klaar",
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sanitize_generated_todos(todos: list[GeneratedPreparationTodo]) -> list[GeneratedPreparationTodo]:
    clean: list[GeneratedPreparationTodo] = []
    seen_titles: set[str] = set()
    for todo in todos:
        title = _clean_text(todo.title)
        if not title:
            continue
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        description = _clean_text(todo.description)
        why = _clean_text(todo.why)
        clean.append(
            GeneratedPreparationTodo(
                title=title,
                description=description or "Werk deze voorbereiding uit en zet alles klaar voor de les.",
                why=why or "Dit is nodig om de les volgens planning uit te voeren.",
            )
        )
    return clean


def _material_needs_preparation(material: str) -> bool:
    lowered = material.lower()
    return any(keyword in lowered for keyword in _MATERIAL_PREP_KEYWORDS)


def _todo_from_material(material: str) -> GeneratedPreparationTodo:
    lowered = material.lower()
    if any(keyword in lowered for keyword in ("opdracht", "werkblad", "quiz", "carrousel", "carousel", "tijdlijn")):
        return GeneratedPreparationTodo(
            title=f"Maak of verzamel: {material}",
            description=(
                f"Werk '{material}' inhoudelijk uit en zorg dat het geprint of digitaal klaarstaat "
                "voor de lesstart."
            ),
            why="Leerlingen hebben dit materiaal nodig om de geplande activiteit uit te voeren.",
        )
    if any(keyword in lowered for keyword in ("bron", "afbeeld", "kaart", "video", "presentatie", "slide", "digibord")):
        return GeneratedPreparationTodo(
            title=f"Verzamel lesmateriaal: {material}",
            description=(
                f"Zoek '{material}' op, controleer kwaliteit/toegankelijkheid en zet het klaar "
                "op het juiste lesmoment."
            ),
            why="Deze ondersteuning maakt de uitleg en verwerking concreet en uitvoerbaar.",
        )
    return GeneratedPreparationTodo(
        title=f"Zet klaar: {material}",
        description=f"Controleer dat '{material}' beschikbaar is en leg het vooraf klaar voor de les.",
        why="Zonder dit materiaal kan de les niet volgens planning worden uitgevoerd.",
    )


def _needs_note_preparation(teacher_notes: str) -> bool:
    lowered = teacher_notes.lower()
    return any(keyword in lowered for keyword in _NOTE_PREP_KEYWORDS)


def _fallback_todos(ctx: PreparationContext) -> list[GeneratedPreparationTodo]:
    todos: list[GeneratedPreparationTodo] = []
    seen_materials: set[str] = set()
    for raw_material in ctx.required_materials:
        material = _clean_text(raw_material)
        if not material:
            continue
        material_key = material.lower()
        if material_key in seen_materials:
            continue
        seen_materials.add(material_key)
        if _material_needs_preparation(material):
            todos.append(_todo_from_material(material))

    notes = _clean_text(ctx.teacher_notes)
    if notes and _needs_note_preparation(notes):
        todos.append(
            GeneratedPreparationTodo(
                title="Controleer aandachtspunten uit docentnotities",
                description=(
                    "Loop de docentnotities door en vertaal aandachtspunten naar concrete acties "
                    "voor differentiatie, begeleiding en lesorganisatie."
                ),
                why="Zo voorkom je dat belangrijke randvoorwaarden tijdens de les worden gemist.",
            )
        )

    if not todos and ctx.required_materials:
        todos.append(
            GeneratedPreparationTodo(
                title="Controleer en verzamel benodigde materialen",
                description=(
                    "Check alle benoemde benodigdheden, regel ontbrekende onderdelen en leg alles "
                    "klaar vóór de lesstart."
                ),
                why="De les kan alleen soepel starten als alle benodigde materialen beschikbaar zijn.",
            )
        )

    return _sanitize_generated_todos(todos)


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
        "Instructie voor output:\n"
        "- Maak een concrete todo voor elk benoemd materiaal dat voorbereiding vraagt "
        "(maken, verzamelen, printen/kopiëren of digitaal klaarzetten).\n"
        "- Materialen zoals opdrachtblad, tijdlijn/carrousel, bronnen, afbeeldingen en kaarten "
        "mogen niet zonder todo blijven.\n"
        "- Geef alleen een lege lijst als er echt geen voorbereiding nodig is.\n\n"
        "Genereer de voorbereidingstaken voor deze les."
    )


async def generate_preparation_todos(ctx: PreparationContext) -> list[GeneratedPreparationTodo]:
    prompt = _build_prompt(ctx)
    generated: list[GeneratedPreparationTodo] = []
    try:
        result = await _get_preparation_agent().run(prompt)
        generated = _sanitize_generated_todos(result.output.todos)
    except Exception:
        logger.exception("Preparation todo generation failed; using deterministic fallback todos.")

    if generated:
        return generated
    return _fallback_todos(ctx)
