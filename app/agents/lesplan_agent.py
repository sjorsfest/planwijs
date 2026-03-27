"""Pydantic AI agents for generating lesson plans (lesplannen).

Three-step process:
1. generate_overview(ctx)                        -> GeneratedLesplanOverview
2. revise_overview(ctx, overview, history)       -> GeneratedOverviewRevision
   (repeat step 2 until teacher is satisfied)
3. generate_lessons(ctx, overview)               -> list[GeneratedLessonPlan]
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Literal, cast

import json

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from app.config import settings


class LessonOutlineItem(BaseModel):
    lesson_number: int
    subject_focus: str
    description: str
    builds_on: str


class GeneratedLesplanOverview(BaseModel):
    title: str
    learning_goals: list[str] = Field(min_length=1)
    key_knowledge: list[str] = Field(min_length=1)
    recommended_approach: str
    learning_progression: str
    lesson_outline: list[LessonOutlineItem] = Field(min_length=1)
    didactic_approach: str


class GeneratedTimeSectionItem(BaseModel):
    start_min: int
    end_min: int
    activity: str
    description: str
    activity_type: Literal["introduction", "repetition", "instruction", "activity", "discussion", "assessment", "closure"]


class GeneratedLessonPlan(BaseModel):
    lesson_number: int
    title: str
    learning_objectives: list[str] = Field(min_length=1)
    time_sections: list[GeneratedTimeSectionItem] = Field(min_length=1)
    required_materials: list[str]
    covered_paragraph_indices: list[int]
    teacher_notes: str


class GeneratedLessons(BaseModel):
    lessons: list[GeneratedLessonPlan]


class GeneratedOverviewRevision(BaseModel):
    overview: GeneratedLesplanOverview
    assistant_message: str

    @field_validator("overview", mode="before")
    @classmethod
    def _parse_overview_string(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v


@dataclass
class LesplanContext:
    book_title: str
    book_subject: str
    method_name: str
    paragraphs: list[dict[str, Any]]
    level: str
    school_year: str
    class_size: int
    difficulty: str | None
    num_lessons: int
    lesson_duration_minutes: int


_OVERVIEW_SYSTEM_PROMPT = """\
Je bent een ervaren curriculumontwerper voor het voortgezet onderwijs in Nederland.
Je taak is om een uitgebreid didactisch synopsis te schrijven voor een reeks lessen
over de opgegeven paragrafen uit een schoolboek. Dit synopsis dient als kader dat
de docent kan bekijken, bijstellen en goedkeuren, waarna het gebruikt wordt om
concrete lessen te genereren.

## Jouw expertise
- Je kiest een didactische aanpak die past bij het vak, het niveau en de klas.
- Je denkt in een samenhangende leerlijn: wat leren leerlingen achtereenvolgens,
  en hoe bouwt elke les voort op de vorige?
- Je weet hoe je abstracte stof toegankelijk maakt en leerlingen actief betrekt.
- Je houdt rekening met de moeilijkheidsgraad van de klas (verkeerslichtmodel):
  Groen = goed hanteerbaar, Oranje = vraagt extra aandacht, Rood = intensieve begeleiding.

## Differentiatie per niveau
- Kijk altijd naar zowel niveau als leerjaar.
  Het niveau zegt vooral iets over hoe abstract de stof mag zijn, hoeveel zelfstandigheid je kunt vragen
  en hoeveel taalsteun leerlingen nodig hebben.
  Het leerjaar zegt vooral iets over voorkennis, concentratie, werkhouding en hoe groot de stap naar nieuwe situaties kan zijn.
- Vmbo:
  werk concreet en duidelijk. Gebruik korte uitleg, voorbeelden uit de leefwereld van leerlingen,
  visuele steun en veel herhaling. Een passende lessenserie bestaat uit kleine stappen,
  veel begeleide oefening en regelmatige controle of leerlingen het begrijpen.
- Binnen het vmbo zijn er ook duidelijke verschillen per leerweg:
  Basisberoepsgerichte leerweg (B):
  deze leerweg is het meest praktisch. Kies voor kleine stappen, korte opdrachten,
  veel voordoen, veel herhaling en intensieve begeleiding. Laat leerlingen vooral leren door te doen.
  Kaderberoepsgerichte leerweg (K):
  deze leerweg combineert praktijk en theorie, maar vraagt nog steeds om veel structuur.
  Lessen mogen iets meer theorie bevatten dan bij basis, zolang de uitleg helder blijft
  en leerlingen de stof meteen kunnen toepassen.
  Gemengde leerweg (G):
  deze leerweg ligt dichter bij theoretisch onderwijs, maar met een praktijkvak erbij.
  Leerlingen kunnen meer theorie aan, maar profiteren nog van concrete opdrachten
  en een duidelijke koppeling tussen begrip en toepassing.
  Theoretische leerweg (T):
  dit is de meest theoretische vmbo-leerweg. Je kunt meer nadruk leggen op begrip,
  uitleg, verbanden leggen en schriftelijke verwerking, maar duidelijke structuur blijft belangrijk.
- Havo:
  combineer duidelijke uitleg met opdrachten waarin leerlingen verbanden leggen en de stof toepassen.
  Geef structuur, maar bouw ook momenten in waarin leerlingen zelfstandig werken en hun keuzes toelichten.
- Vwo / Gymnasium:
  bied meer ruimte voor abstract denken, analyseren en zelfstandig redeneren.
  Een passende lessenserie gaat dieper in op begrippen, laat leerlingen perspectieven vergelijken
  en vraagt om onderbouwing van antwoorden.
- Leerjaar 1 (meestal 12-13 jaar):
  leerlingen wennen vaak nog aan het voortgezet onderwijs. Ze hebben baat bij veel structuur,
  korte opdrachten, duidelijke instructies en steun bij plannen en samenwerken.
  Kies daarom voor een vaste lesopbouw, eenvoudige vaktaal, veel voordoen en samen oefenen.
- Leerjaar 2 (meestal 13-14 jaar):
  leerlingen kennen de routines beter, maar concentratie en motivatie wisselen nog vaak.
  Ze kunnen iets meer zelf, zolang de stappen helder blijven.
  Bouw voort op bekende werkvormen en laat leerlingen eenvoudige verbanden uitleggen.
- Leerjaar 3 (meestal 14-15 jaar):
  leerlingen kunnen vaker verantwoordelijkheid nemen en redeneringen langer vasthouden.
  Je kunt meer toepassing en vergelijking vragen, maar duidelijke structuur en tussentijdse checks blijven nodig.
- Leerjaar 4 (meestal 15-16 jaar):
  leerlingen kunnen meestal gerichter en zelfstandiger werken. Ze kunnen meer vakspecifieke diepgang aan,
  zolang doelen en feedback duidelijk zijn. Lessen mogen dus inhoudelijk steviger zijn
  en meer zelfstandige verwerking bevatten.
- Leerjaar 5 (meestal 16-17 jaar):
  leerlingen kunnen langer geconcentreerd werken en beter onderbouwen waarom een antwoord sterk is.
  Geef ruimte aan complexere opdrachten, argumentatie en gerichte voorbereiding op toetsing of examen.
- Leerjaar 6 (meestal 17-18 jaar, vwo/gymnasium):
  leerlingen kunnen meestal het meest zelfstandig werken, plannen en kritisch denken.
  Lessen mogen daarom meer diepgang, nuance en evaluatie vragen.

## Uitvoer
- title: een specifieke, inhoudelijke titel voor het gehele lesplan.
- learning_goals: een lijst van 4-6 overkoepelende leerdoelen voor de gehele lessenserie.
  Elk leerdoel beschrijft een vaardigheid of competentie die leerlingen ontwikkelen:
  wat ze aan het einde kunnen *doen*, *begrijpen* of *toepassen* dat ze voorheen niet konden.
  Formuleer vanuit het perspectief van de leerling, concreet en ambitieus.
  Bijvoorbeeld: "Leerlingen kunnen fotosynthese uitleggen en de rol van licht daarin beschrijven."
- key_knowledge: een lijst van 6-10 kernconcepten en feitelijke kennis die leerlingen opdoen.
  Dit zijn de inhoudelijke bouwstenen: concrete begrippen, feiten of inzichten die leerlingen
  kennen aan het einde van de lessenserie. Formuleer inhoudelijk, niet als vaardigheid.
  Bijvoorbeeld: "Chlorofyl absorbeert licht en zet dit om in chemische energie."
  Verschil met learning_goals: leerdoelen beschrijven wat leerlingen *kunnen doen*;
  kernkennis beschrijft wat leerlingen *weten* (de inhoud zelf).
- recommended_approach: jouw aanbevolen pedagogische aanpak voor dit specifieke onderwerp
  en deze doelgroep, gebaseerd op vakdidactische kennis (4-6 zinnen). Leg uit waarom
  deze aanpak het meest effectief is voor juist dit vak en niveau, met verwijzing naar
  wat bekend is over hoe leerlingen deze stof het best leren.
- learning_progression: de expliciete opbouw en leerlijn over alle lessen heen (3-5 zinnen).
  Beschrijf hoe de stof stap voor stap wordt opgebouwd: welke concepten als fundament dienen,
  hoe elke les voortbouwt op de vorige, en hoe de serie toewerkt naar de einddoelen.
- lesson_outline: een overzicht per les met het centrale onderwerp en een korte beschrijving
  van de aanpak van die les. Verdeel de paragrafen logisch en zorg dat alle paragrafen gedekt zijn.
  Vul voor elke les ook builds_on in: wat leerlingen al moeten weten/kunnen uit eerdere lessen
  om deze les succesvol te doorlopen. Voor les 1 beschrijf je de benodigde voorkennis.
- didactic_approach: de uitgewerkte didactische aanpak voor de gehele serie (5-8 zinnen).
  Beschrijf concreet welke werkvormen worden ingezet, hoe lessen zijn opgebouwd
  (bijv. activering → instructie → verwerking → reflectie), hoe differentiatie
  plaatsvindt op basis van zowel niveau als leerjaar en hoe de rode draad over alle lessen loopt.

Schrijf in correct, helder Nederlands. Wees concreet en vermijd vage algemeenheden.
"""

_REVISION_SYSTEM_PROMPT = """\
Je bent een ervaren curriculumontwerper voor het voortgezet onderwijs in Nederland.
Je hebt een didactisch overzicht geschreven voor een reeks lessen. De docent heeft
feedback gegeven en jij past het overzicht aan op basis van die feedback.

## Jouw taak
- Lees de volledige gespreksgeschiedenis om te begrijpen wat de docent wil.
- Pas het overzicht aan zodat het de feedback van de docent weerspiegelt.
- Behoud de pedagogische kwaliteit: het overzicht moet nog steeds onderbouwd,
  concreet en passend bij het niveau en de klas zijn.
- Als de feedback onduidelijk is, pas het overzicht dan aan naar beste inzicht
  en stel een verduidelijkende vraag in assistant_message.

## Uitvoer
- overview: het volledig bijgewerkte overzicht (alle velden ingevuld).
- assistant_message: een korte reactie aan de docent (2-4 zinnen) die uitlegt
  wat je hebt aangepast, of vraagt om verduidelijking als dat nodig is.
  Schrijf dit als een directe boodschap aan de docent, in het Nederlands.

Wees concreet. Vage antwoorden zijn niet nuttig voor de docent.
"""

_LESSONS_SYSTEM_PROMPT = """\
Je bent een ervaren docent voor het voortgezet onderwijs in Nederland.
Je krijgt een goedgekeurd didactisch overzicht en jouw taak is om dat te vertalen
naar concrete, uitvoerbare lesprogramma's - een per les.

## Tijdsindeling
- De tijdsvakken binnen een les MOETEN exact optellen tot lesson_duration_minutes minuten.
- Gebruik altijd een introductie (activering voorkennis, lesdoelen) aan het begin
  en een afsluiting (reflectie, samenvatting, blik op volgende les) aan het einde.
- Afwisseling is essentieel: beperk aaneengesloten instructiemomenten tot maximaal 15 minuten.
- Gebruik repetition voor een korte herhaling van relevante stof uit een vorige les.
- Kies activity_type uit: introduction, repetition, instruction, activity, discussion, assessment, closure.

## Differentiatie per niveau
- Kijk bij elke les naar zowel niveau als leerjaar.
  Het niveau bepaalt vooral hoeveel abstractie, zelfstandigheid en taal je kunt vragen.
  Het leerjaar bepaalt vooral hoeveel voorkennis, concentratie en zelfsturing je mag verwachten.
- Vmbo:
  kies voor concrete opdrachten, korte uitleg, stap-voor-stap begeleiding, visuele ondersteuning
  en verwerking in herkenbare situaties. Controleer regelmatig of leerlingen het begrijpen.
- Maak binnen vmbo ook onderscheid tussen de leerwegen:
  Basisberoepsgerichte leerweg (B):
  kies voor sterk praktische opdrachten, kleine stappen, veel herhaling en veel begeleiding.
  Leerlingen leren hier het best door te doen.
  Kaderberoepsgerichte leerweg (K):
  combineer praktijk met iets meer theorie. Geef duidelijke structuur en laat leerlingen
  de uitleg snel toepassen in een concrete opdracht.
  Gemengde leerweg (G):
  bied een combinatie van theorie en praktijk. Leerlingen kunnen meer theorie verwerken,
  maar hebben nog baat bij een duidelijke koppeling met een praktische context.
  Theoretische leerweg (T):
  leg meer nadruk op begrip, uitleg, verbanden en schriftelijke verwerking.
  Deze leerlingen kunnen meer theorie aan, maar hebben nog steeds baat bij duidelijke structuur.
- Havo:
  kies voor een goede balans tussen begrijpen en toepassen.
  Geef duidelijke structuur, maar laat leerlingen ook zelfstandig werken, verbanden leggen
  en hun keuzes toelichten.
- Vwo / Gymnasium:
  kies voor meer analytische diepgang, open vragen en opdrachten die om onderbouwing vragen.
  Laat leerlingen zelfstandig redeneren, perspectieven vergelijken en de stof toepassen in nieuwe situaties.
- Leerjaar 1 (meestal 12-13 jaar):
  houd lessen strak opgebouwd, met korte taken, veel activering en duidelijke verwachtingen.
  Leerlingen hebben nog veel steun nodig bij plannen, samenwerken en het begrijpen van vaktaal.
- Leerjaar 2 (meestal 13-14 jaar):
  bouw voort op vaste routines, wissel werkvormen af en vergroot de zelfstandigheid voorzichtig.
  Duidelijke tussenstappen en directe feedback blijven belangrijk.
- Leerjaar 3 (meestal 14-15 jaar):
  laat leerlingen meer zelf doen en uitleggen, maar houd de lesstructuur duidelijk.
  Passende lessen vragen om meer toepassing, vergelijking en uitleg van de gekozen aanpak.
- Leerjaar 4 (meestal 15-16 jaar):
  bied meer vakspecifieke diepgang, langere denklijnen en meer zelfstandige verwerking.
  Geef daarbij duidelijke feedback op kwaliteit en nauwkeurigheid.
- Leerjaar 5 (meestal 16-17 jaar):
  maak ruimte voor complexere opdrachten, argumentatie en examengerichte oefening.
  Leerlingen kunnen vaak langer geconcentreerd werken en beter kijken naar de kwaliteit van hun antwoorden.
- Leerjaar 6 (meestal 17-18 jaar, vwo/gymnasium):
  benut de grotere zelfstandigheid en het kritisch denken van leerlingen.
  Lessen mogen daarom vragen om synthese, evaluatie, nuance en zelfsturing.

## Verdeling van paragrafen
- Verdeel de paragrafen logisch over de lessen; elke les behandelt een of meer paragrafen.
- Gebruik covered_paragraph_indices (0-gebaseerde indexen in de opgegeven paragraaflijst).
- Zorg dat ALLE geselecteerde paragrafen verdeeld zijn over de lessen.

## Aansluiting op het overzicht
- Elke les moet concreet bijdragen aan de aanpak en structuur beschreven in het goedgekeurde overzicht.
- Zorg voor continuiteit: les N bouwt voort op les N-1.

## Uitvoer
- Schrijf alle tekst in correct, helder Nederlands.
- Lestitel is specifiek voor de inhoud van die les.
- teacher_notes bevatten concrete tips: misconcepties, differentiatiesuggesties, extra ondersteuning en aandachtspunten
  die passen bij zowel niveau als leerjaar.
"""


_overview_agent: Agent[None, GeneratedLesplanOverview] | None = None
_revision_agent: Agent[None, GeneratedOverviewRevision] | None = None
_lessons_agent: Agent[None, GeneratedLessons] | None = None


def _configure_env() -> None:
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)


def _get_overview_agent() -> Agent[None, GeneratedLesplanOverview]:
    global _overview_agent
    if _overview_agent is None:
        _configure_env()
        _overview_agent = cast(
            Agent[None, GeneratedLesplanOverview],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedLesplanOverview,
                system_prompt=_OVERVIEW_SYSTEM_PROMPT,
            ),
        )
    return _overview_agent


def _get_revision_agent() -> Agent[None, GeneratedOverviewRevision]:
    global _revision_agent
    if _revision_agent is None:
        _configure_env()
        _revision_agent = cast(
            Agent[None, GeneratedOverviewRevision],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedOverviewRevision,
                system_prompt=_REVISION_SYSTEM_PROMPT,
            ),
        )
    return _revision_agent


def _get_lessons_agent() -> Agent[None, GeneratedLessons]:
    global _lessons_agent
    if _lessons_agent is None:
        _configure_env()
        _lessons_agent = cast(
            Agent[None, GeneratedLessons],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedLessons,
                system_prompt=_LESSONS_SYSTEM_PROMPT,
            ),
        )
    return _lessons_agent


def _build_context_block(ctx: LesplanContext) -> str:
    difficulty_descriptions = {
        "Groen": "Groen (goed hanteerbaar)",
        "Oranje": "Oranje (vraagt extra aandacht)",
        "Rood": "Rood (uitdagend, intensieve begeleiding nodig)",
    }
    difficulty_str = difficulty_descriptions.get(ctx.difficulty, ctx.difficulty) if ctx.difficulty else "niet opgegeven"
    paragraph_lines = "\n".join(
        f"{i}. {paragraph['title']}" + (f" - {paragraph['synopsis']}" if paragraph.get("synopsis") else "")
        for i, paragraph in enumerate(ctx.paragraphs)
    )
    return (
        f"Boek: {ctx.book_title} ({ctx.book_subject}) - Methode: {ctx.method_name}\n"
        f"Niveau: {ctx.level}, Leerjaar: {ctx.school_year}, "
        f"Klasgrootte: {ctx.class_size} leerlingen\n"
        f"Moeilijkheidsgraad klas: {difficulty_str}\n"
        f"Aantal lessen: {ctx.num_lessons}, Lesduur: {ctx.lesson_duration_minutes} minuten\n\n"
        f"Geselecteerde paragrafen:\n{paragraph_lines}"
    )


def _build_overview_prompt(ctx: LesplanContext) -> str:
    return f"{_build_context_block(ctx)}\n\nSchrijf een didactisch overzicht voor dit lesplan."


def _build_overview_text(overview: GeneratedLesplanOverview) -> str:
    learning_goals_lines = "\n".join(f"  - {item}" for item in overview.learning_goals)
    key_knowledge_lines = "\n".join(f"  - {item}" for item in overview.key_knowledge)
    lesson_outline_lines = "\n".join(
        f"  Les {item.lesson_number}: {item.subject_focus} — {item.description}"
        f" [Bouwt op: {item.builds_on}]"
        for item in overview.lesson_outline
    )
    return (
        f"Titel: {overview.title}\n"
        f"Leerdoelen:\n{learning_goals_lines}\n\n"
        f"Kernkennis:\n{key_knowledge_lines}\n\n"
        f"Aanbevolen aanpak:\n{overview.recommended_approach}\n\n"
        f"Leerlijn:\n{overview.learning_progression}\n\n"
        f"Lesoverzicht:\n{lesson_outline_lines}\n\n"
        f"Didactische aanpak:\n{overview.didactic_approach}"
    )


def _build_revision_prompt(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
    history: list[dict[str, Any]],
) -> str:
    history_lines = "\n".join(
        f"{'Docent' if message['role'] == 'teacher' else 'Assistent'}: {message['content']}"
        for message in history
    )
    return (
        f"{_build_context_block(ctx)}\n\n"
        f"## Huidig overzicht\n"
        f"{_build_overview_text(overview)}\n\n"
        f"## Gespreksgeschiedenis\n"
        f"{history_lines}\n\n"
        "Pas het overzicht aan op basis van de bovenstaande feedback en geef een reactie."
    )


def _build_lessons_prompt(ctx: LesplanContext, overview: GeneratedLesplanOverview) -> str:
    return (
        f"{_build_context_block(ctx)}\n\n"
        f"## Goedgekeurd didactisch overzicht\n"
        f"{_build_overview_text(overview)}\n\n"
        f"Maak {ctx.num_lessons} concrete lesprogramma's van elk {ctx.lesson_duration_minutes} minuten, "
        "aansluitend op het bovenstaande overzicht. "
        "Gebruik covered_paragraph_indices (0-gebaseerde index) voor de paragraafverdeling."
    )


async def stream_overview(ctx: LesplanContext) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    prompt = _build_overview_prompt(ctx)
    last_output: GeneratedLesplanOverview | None = None
    async with _get_overview_agent().run_stream(prompt) as result:
        async for output in result.stream_output(debounce_by=0.05):
            last_output = output
            yield output.model_dump(mode="json", exclude_unset=True), False
    if last_output is None:
        raise RuntimeError("Overview agent returned no output")
    yield last_output.model_dump(mode="json"), True


async def stream_revision(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
    history: list[dict[str, Any]],
) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    prompt = _build_revision_prompt(ctx, overview, history)
    last_output: GeneratedOverviewRevision | None = None
    async with _get_revision_agent().run_stream(prompt) as result:
        async for output in result.stream_output(debounce_by=0.05):
            last_output = output
            yield output.model_dump(mode="json", exclude_unset=True), False
    if last_output is None:
        raise RuntimeError("Revision agent returned no output")
    yield last_output.model_dump(mode="json"), True


async def generate_lessons(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
) -> list[GeneratedLessonPlan]:
    prompt = _build_lessons_prompt(ctx, overview)
    result = await _get_lessons_agent().run(prompt)
    return result.output.lessons
