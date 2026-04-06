"""Agent for generating lesson preparation todos per LessonPlan."""

from __future__ import annotations

import asyncio
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
Je analyseert een uitgewerkt lesprogramma en genereert concrete, specifieke voorbereidingstaken.

## Werkwijze — verplicht
1. Lees ALLE tijdsvakken (activiteiten) zorgvuldig door. Let op wat de docent en leerlingen
   concreet doen: welke materialen worden gebruikt, getoond, uitgedeeld of besproken?
2. Lees de lijst "Benodigde materialen".
3. Koppel elk materiaal aan de tijdsvakken waarin het wordt gebruikt.
   Gebruik de beschrijvingen van die tijdsvakken om te bepalen WAT het materiaal precies
   moet bevatten. Dit is de kern van je taak.
4. Genereer per materiaal dat voorbereiding vraagt (maken, zoeken, printen, klaarzetten)
   een todo met SPECIFIEKE inhoud.

## Regels voor de description van elke todo
- De description moet EXACT beschrijven wat het materiaal moet bevatten of tonen.
- Haal deze details uit de beschrijvingen van de tijdsvakken.
- Voorbeelden van wat WEL specifiek genoeg is:
  - "Zoek afbeeldingen van: het Parthenon, een Grieks amfitheater, de Discuswerper van Myron,
    een pagina uit de Ilias of Odyssee, en een modern gebouw met Griekse zuilen.
    Print 5-6 afbeeldingen per groep (4-5 groepen) in kleur op A4-formaat."
  - "Maak een werkblad met per afbeelding drie vragen: (1) Wat is dit? (2) Wat is typisch
    Grieks hieraan? (3) Waar zien we dit nog terug in onze tijd? Voeg ruimte toe voor
    antwoorden en een sectie onderaan voor de groepspresentatie."
  - "Maak gebeurteniskaartjes met de volgende gebeurtenissen: val van de Berlijnse Muur (1989),
    Golfoorlog (1990-1991), verdrag van Maastricht (1992), genocide in Rwanda (1994),
    aanslagen 11 september (2001), toetreding Oost-Europese landen tot EU (2004).
    Print per duo één set."
- Voorbeelden van wat NIET specifiek genoeg is (NIET doen):
  - "Zoek afbeeldingen voor de les" (welke afbeeldingen?!)
  - "Maak een werkblad" (met welke vragen/inhoud?!)
  - "Verzamel materiaal" (welk materiaal?!)

## Uitvoer per taak
- title: korte actieve taakomschrijving (max 10 woorden)
- description: WAT er precies gemaakt/gezocht moet worden, inclusief concrete inhoud,
  aantallen, en format. De docent moet hiermee direct aan de slag kunnen zonder het
  lesplan opnieuw te lezen.
- why: waarom deze taak nodig is, gekoppeld aan het specifieke lesmoment.

## Belangrijk
- Genereer voor ELK materiaal dat voorbereiding vraagt minimaal één todo.
- Standaard materialen zoals een schoolboek of schrift hoeven GEEN todo.
- Als een materiaal meerdere onderdelen bevat (bijv. "foto's en kaartmateriaal"),
  maak dan aparte todos per onderdeel.
- Schrijf in correct, helder Nederlands.
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


def _find_related_sections(material: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find time sections that likely use this material based on keyword overlap."""
    material_words = {w for w in material.lower().split() if len(w) > 3}
    related: list[dict[str, Any]] = []
    for section in sections:
        desc = section.get("description", "").lower()
        activity = section.get("activity", "").lower()
        combined = f"{desc} {activity}"
        if any(word in combined for word in material_words):
            related.append(section)
    return related


def _build_fallback_description(material: str, related_sections: list[dict[str, Any]]) -> str:
    """Build a description that includes context from related time sections."""
    base = f"Bereid voor: '{material}'."
    if related_sections:
        section_details = []
        for s in related_sections:
            time_range = f"{s.get('start_min', '?')}-{s.get('end_min', '?')} min"
            desc = s.get("description", "")
            section_details.append(f"  - [{time_range}] {desc}")
        context = "\n".join(section_details)
        base += (
            f"\n\nDit materiaal wordt gebruikt in de volgende activiteit(en):\n{context}"
            "\n\nZorg dat het materiaal aansluit bij bovenstaande beschrijving: "
            "de juiste inhoud, aantallen, en format."
        )
    return base


def _todo_from_material(material: str, sections: list[dict[str, Any]] | None = None) -> GeneratedPreparationTodo:
    related = _find_related_sections(material, sections) if sections else []
    description = _build_fallback_description(material, related)

    lowered = material.lower()
    if any(keyword in lowered for keyword in ("opdracht", "werkblad", "quiz", "carrousel", "carousel", "tijdlijn")):
        return GeneratedPreparationTodo(
            title=f"Maak of verzamel: {material}",
            description=description,
            why="Leerlingen hebben dit materiaal nodig om de geplande activiteit uit te voeren.",
        )
    if any(keyword in lowered for keyword in ("bron", "afbeeld", "kaart", "video", "presentatie", "slide", "digibord")):
        return GeneratedPreparationTodo(
            title=f"Verzamel lesmateriaal: {material}",
            description=description,
            why="Deze ondersteuning maakt de uitleg en verwerking concreet en uitvoerbaar.",
        )
    return GeneratedPreparationTodo(
        title=f"Zet klaar: {material}",
        description=description,
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
            todos.append(_todo_from_material(material, ctx.time_sections))

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
                "openrouter:google/gemini-3.1-pro-preview",
                output_type=GeneratedPreparationTodos,
                system_prompt=_SYSTEM_PROMPT,
            ),
        )
    return _preparation_agent


def _build_prompt(ctx: PreparationContext) -> str:
    objectives = "\n".join(f"  - {o}" for o in ctx.learning_objectives)
    materials = (
        "\n".join(f"  {i+1}. {m}" for i, m in enumerate(ctx.required_materials))
        if ctx.required_materials
        else "  (geen)"
    )
    sections = "\n".join(
        f"  [{s['start_min']}-{s['end_min']} min] {s['activity']} "
        f"(type: {s.get('activity_type', '')})\n"
        f"    Beschrijving: {s['description']}"
        for s in ctx.time_sections
    )
    notes = ctx.teacher_notes.strip() if ctx.teacher_notes else "(geen)"
    return (
        f"# Les {ctx.lesson_number}: {ctx.title}\n\n"
        f"## Lesdoelen\n{objectives}\n\n"
        f"## Tijdsvakken (activiteiten)\n{sections}\n\n"
        f"## Benodigde materialen\n{materials}\n\n"
        f"## Docentnotities\n{notes}\n\n"
        "---\n\n"
        "## Opdracht\n"
        "Analyseer bovenstaand lesplan en genereer voorbereidingstodos.\n\n"
        "STAP 1: Ga elk materiaal uit de lijst 'Benodigde materialen' langs.\n"
        "STAP 2: Zoek in de tijdsvakken (activiteiten) op HOE dat materiaal wordt gebruikt.\n"
        "STAP 3: Bepaal op basis van de activiteitbeschrijving WAT het materiaal precies\n"
        "moet bevatten of tonen.\n"
        "STAP 4: Schrijf een todo met in de description de EXACTE inhoud, aantallen en format.\n\n"
        "Voorbeeld redenering:\n"
        '- Materiaal: "Set afbeeldingen (5-6 per groep): Parthenon, theater, beeld"\n'
        '- Tijdsvak zegt: "Groepjes ontvangen set afbeeldingen (tempel, theater, beeld, boekfragment)"\n'
        "- Dus de todo description wordt: \"Zoek en print afbeeldingen van: het Parthenon, "
        "een Grieks amfitheater, de Discuswerper, een fragment uit Homerus' werk, en een modern "
        "gebouw met Griekse zuilen. Print 5-6 afbeeldingen per groep in kleur op A4.\"\n\n"
        "Genereer nu de voorbereidingstaken."
    )


_AGENT_TIMEOUT_SECONDS = 300


async def generate_preparation_todos(ctx: PreparationContext) -> list[GeneratedPreparationTodo]:
    prompt = _build_prompt(ctx)
    logger.info("Generating preparation todos for lesson %s: %s", ctx.lesson_number, ctx.title)
    generated: list[GeneratedPreparationTodo] = []
    try:
        result = await asyncio.wait_for(
            _get_preparation_agent().run(prompt),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
        generated = _sanitize_generated_todos(result.output.todos)
        logger.info(
            "AI agent returned %d todos for lesson %s",
            len(generated),
            ctx.lesson_number,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Preparation agent timed out after %ds for lesson %s; using fallback.",
            _AGENT_TIMEOUT_SECONDS,
            ctx.lesson_number,
        )
    except Exception:
        logger.exception("Preparation todo generation failed for lesson %s; using fallback.", ctx.lesson_number)

    if generated:
        return generated

    fallback = _fallback_todos(ctx)
    logger.info("Fallback generated %d todos for lesson %s", len(fallback), ctx.lesson_number)
    return fallback
