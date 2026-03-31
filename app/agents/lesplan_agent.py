"""Pydantic AI agents for generating lesson plans (lesplannen).

Three-step process:
1. generate_overview(ctx)                        -> GeneratedLesplanOverview
2. revise_overview(ctx, overview, history)       -> GeneratedOverviewRevision
   (repeat step 2 until teacher is satisfied)
3. generate_lessons(ctx, overview)               -> list[GeneratedLessonPlan]
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Literal, cast

import json

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_ai import Agent

from app.config import settings


class LessonOutlineItem(BaseModel):
    lesson_number: int = 0
    subject_focus: str = ""
    description: str = ""
    teaching_approach_hint: str = ""
    builds_on: str = ""
    concept_tags: list[str] = Field(default_factory=list)
    lesson_intention: str = ""
    end_understanding: str = ""
    sequence_rationale: str = ""
    builds_on_lessons: list[int] = Field(default_factory=list)
    paragraph_indices: list[int] = Field(default_factory=list)

    @field_validator("concept_tags", mode="before")
    @classmethod
    def _parse_concept_tags(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return [part.strip() for part in re.split(r"[,;]", v) if part.strip()]
        return v

    @field_validator("builds_on_lessons", "paragraph_indices", mode="before")
    @classmethod
    def _parse_int_lists(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                values: list[int] = []
                for part in re.split(r"[,\s]+", v.strip()):
                    if not part:
                        continue
                    try:
                        values.append(int(part))
                    except ValueError:
                        continue
                return values
        return v


class GoalCoverageItem(BaseModel):
    goal: str = ""
    lesson_numbers: list[int] = Field(default_factory=list)
    rationale: str = ""


class KnowledgeCoverageItem(BaseModel):
    knowledge: str = ""
    lesson_numbers: list[int] = Field(default_factory=list)
    rationale: str = ""


class ApprovalReadiness(BaseModel):
    ready_for_approval: bool = False
    rationale: str = ""
    checklist: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("checklist", "open_questions", mode="before")
    @classmethod
    def _parse_string_lists(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return [line.strip("- ").strip() for line in v.splitlines() if line.strip()]
        return v


class GeneratedLesplanOverview(BaseModel):
    title: str
    series_summary: str
    series_themes: list[str] = Field(default_factory=list)
    learning_goals: list[str] = Field(default_factory=list)
    key_knowledge: list[str] = Field(default_factory=list)
    recommended_approach: str
    learning_progression: str
    lesson_outline: list[LessonOutlineItem] = Field(default_factory=list)
    goal_coverage: list[GoalCoverageItem] = Field(default_factory=list)
    knowledge_coverage: list[KnowledgeCoverageItem] = Field(default_factory=list)
    approval_readiness: ApprovalReadiness
    didactic_approach: str

    @field_validator(
        "series_themes",
        "learning_goals",
        "key_knowledge",
        "lesson_outline",
        "goal_coverage",
        "knowledge_coverage",
        mode="before",
    )
    @classmethod
    def _parse_json_list_fields(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                return v
            return parsed
        return v

    @field_validator("approval_readiness", mode="before")
    @classmethod
    def _parse_approval_readiness_string(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {
                    "ready_for_approval": False,
                    "rationale": v,
                    "checklist": [],
                    "open_questions": [],
                }
        return v


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


def _default_approval_readiness() -> ApprovalReadiness:
    return ApprovalReadiness(
        ready_for_approval=False,
        rationale="Controleer doelen, kernkennis en lesopbouw voordat je goedkeurt.",
        checklist=[
            "Doelen sluiten aan op de klas.",
            "Kernkennis is volledig en correct.",
            "Lesvolgorde bouwt logisch op.",
        ],
        open_questions=[],
    )


class GeneratedOverviewIdentity(BaseModel):
    title: str = ""
    series_summary: str = ""
    series_themes: list[str] = Field(default_factory=list)

    @field_validator("series_themes", mode="before")
    @classmethod
    def _parse_string_list(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return [line.strip("- ").strip() for line in v.splitlines() if line.strip()]
        return v


class GeneratedOverviewSequence(BaseModel):
    learning_goals: list[str] = Field(default_factory=list)
    key_knowledge: list[str] = Field(default_factory=list)
    lesson_outline: list[LessonOutlineItem] = Field(default_factory=list)

    @field_validator("learning_goals", "key_knowledge", "lesson_outline", mode="before")
    @classmethod
    def _parse_json_lists(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                return []
            except json.JSONDecodeError:
                if info.field_name == "lesson_outline":
                    return []
                return [line.strip("- ").strip() for line in v.splitlines() if line.strip()]
        return v


class GeneratedOverviewTeacherNotes(BaseModel):
    recommended_approach: str = ""
    learning_progression: str = ""
    didactic_approach: str = ""
    approval_readiness: ApprovalReadiness = Field(default_factory=_default_approval_readiness)

    @field_validator("approval_readiness", mode="before")
    @classmethod
    def _parse_approval_readiness(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {
                    "ready_for_approval": False,
                    "rationale": v,
                    "checklist": [],
                    "open_questions": [],
                }
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
- series_summary: 2-4 zinnen die kort uitleggen waar de reeks over gaat, waarom dit onderwerp relevant is
  en hoe de reeks inhoudelijk oploopt.
- series_themes: 3-6 korte thema's of kernmotieven die door de hele reeks lopen.
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
  Verplicht per les:
  - lesson_number
  - subject_focus
  - description (1-2 zinnen)
  - teaching_approach_hint (1 korte zin: hoe de stof in deze les wordt aangeboden)
  - builds_on
  - concept_tags (2-4 compacte tags)
  - lesson_intention (wat is het doel van deze les)
  - end_understanding (wat leerlingen aan het einde begrijpen)
  - sequence_rationale (waarom deze les op deze plek staat)
  - builds_on_lessons (lijst met eerdere lesnummers waar deze les op voortbouwt)
  - paragraph_indices (0-gebaseerde indices van de geselecteerde paragrafen die deze les dekt)
- goal_coverage: koppel elk learning_goal aan lesson_numbers (minimaal 1) met korte rationale.
- knowledge_coverage: koppel elk key_knowledge-item aan lesson_numbers (minimaal 1) met korte rationale.
- approval_readiness: object met:
  - ready_for_approval (boolean)
  - rationale (1-2 zinnen)
  - checklist (korte bullets die docent kan nalopen)
  - open_questions (optioneel, kan leeg zijn)
- didactic_approach: de uitgewerkte didactische aanpak voor de gehele serie (5-8 zinnen).
  Beschrijf concreet welke werkvormen worden ingezet, hoe lessen zijn opgebouwd,
  (bijv. activering → instructie → verwerking → reflectie), 
  Waarom deze aanpak effectief is voor dit specifieke onderwerp en deze doelgroep,
  En hoe differentiatie plaatsvindt tussen leerlingen onderling.

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
- Lever exact hetzelfde schema terug als in de overzichtsfase, inclusief:
  series_summary, series_themes, lesson_outline met alle subvelden,
  goal_coverage, knowledge_coverage en approval_readiness.

## Uitvoer
- overview: het volledig bijgewerkte overzicht (alle velden ingevuld).
- assistant_message: een korte reactie aan de docent (2-4 zinnen) die uitlegt
  wat je hebt aangepast, of vraagt om verduidelijking als dat nodig is.
  Schrijf dit als een directe boodschap aan de docent, in het Nederlands.

Wees concreet. Vage antwoorden zijn niet nuttig voor de docent.
"""

_OVERVIEW_IDENTITY_SYSTEM_PROMPT = """\
Je schrijft alleen de kernidentiteit van een lessenreeks voor review vóór goedkeuring.

Uitvoer:
- title: korte, inhoudelijke titel.
- series_summary: markdown met precies 3 bullets:
  - **Onderwerp:** thema en relevantie.
  - **Opbouw over X lessen:** inhoudelijke opbouw.
  - **Didactische aanpak voor deze klas:** hoe de docent dit aanpakt voor deze doelgroep.
  Gebruik doelgroepinformatie uit de context (vak, niveau, leerjaar, klasgrootte, moeilijkheid).
- series_themes: 3-6 korte thema's.

Schrijf helder Nederlands en blijf concreet.
"""

_OVERVIEW_SEQUENCE_SYSTEM_PROMPT = """\
Je schrijft alleen de inhoudelijke reviewkern van een lessenreeks.

Uitvoer:
- learning_goals: 4-6 doelen die beschrijven wat leerlingen kunnen.
- key_knowledge: 6-10 inhoudelijke kennispunten.
- lesson_outline: precies het aantal lessen uit de context, met per les:
  lesson_number, subject_focus, description, teaching_approach_hint, builds_on, concept_tags (2-4),
  lesson_intention, end_understanding, sequence_rationale, builds_on_lessons, paragraph_indices.
  teaching_approach_hint moet per les verschillen en een concrete werkvorm noemen die past bij het onderwerp
  van die les. Vermijd herhaling van dezelfde zinstructuur voor alle lessen.
  Kwaliteitsregels per les:
  - subject_focus is inhoudelijk specifiek (niet: "Les 1", "Les 2", ...).
  - description zegt in 1-2 zinnen zowel waar de les over gaat als wat leerlingen doen.
  - lesson_intention en end_understanding mogen niet letterlijk dezelfde zin zijn als description.
  - Vermijd placeholders zoals: "In deze les staat les X centraal."

Voorbeeld GOED:
- subject_focus: "Bestuur en democratie in Athene"
- description: "Leerlingen onderzoeken hoe de Atheense democratie werkte via een korte bronvergelijking en koppelen dit aan burgerschap nu."
- teaching_approach_hint: "Start met een kaart- en bronduo-opdracht, laat leerlingen daarna in een mini-debat standpunten onderbouwen."

Voorbeeld SLECHT:
- subject_focus: "Les 2"
- description: "In deze les staat les 2 centraal."
- teaching_approach_hint: "Korte activering, daarna uitleg, daarna verwerking."

Geen tijdsblokken of lesfasen op minutenniveau.
"""

_OVERVIEW_NOTES_SYSTEM_PROMPT = """\
Je schrijft alleen docentgerichte onderbouwing voor een review vóór goedkeuring.

Uitvoer:
- recommended_approach: 4-6 zinnen.
- learning_progression: 3-5 zinnen.
- didactic_approach: 5-8 zinnen.
- approval_readiness: object met ready_for_approval, rationale, checklist, open_questions.

Beschrijf expliciet dat details pas na goedkeuring worden uitgewerkt.
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
- Gebruik actief:
  - series_summary en series_themes als rode draad voor samenhang.
  - lesson_outline.paragraph_indices voor inhoudelijke toewijzing.
  - lesson_outline.teaching_approach_hint voor de didactische werkvorm per les.
  - lesson_outline.lesson_intention, end_understanding en sequence_rationale voor lesdoel en positionering.
  - goal_coverage en knowledge_coverage om te bewaken dat doelen en kernkennis terugkomen in de uitgewerkte lessen.

## Uitvoer
- Schrijf alle tekst in correct, helder Nederlands.
- Lestitel is specifiek voor de inhoud van die les.
- teacher_notes bevatten concrete tips: misconcepties, differentiatiesuggesties, extra ondersteuning en aandachtspunten
  die passen bij zowel niveau als leerjaar.
"""


_overview_identity_agent: Agent[None, GeneratedOverviewIdentity] | None = None
_overview_sequence_agent: Agent[None, GeneratedOverviewSequence] | None = None
_overview_teacher_agent: Agent[None, GeneratedOverviewTeacherNotes] | None = None
_lessons_agent: Agent[None, GeneratedLessons] | None = None


def _configure_env() -> None:
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)


def _get_overview_identity_agent() -> Agent[None, GeneratedOverviewIdentity]:
    global _overview_identity_agent
    if _overview_identity_agent is None:
        _configure_env()
        _overview_identity_agent = cast(
            Agent[None, GeneratedOverviewIdentity],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedOverviewIdentity,
                system_prompt=_OVERVIEW_IDENTITY_SYSTEM_PROMPT,
            ),
        )
    return _overview_identity_agent


def _get_overview_sequence_agent() -> Agent[None, GeneratedOverviewSequence]:
    global _overview_sequence_agent
    if _overview_sequence_agent is None:
        _configure_env()
        _overview_sequence_agent = cast(
            Agent[None, GeneratedOverviewSequence],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedOverviewSequence,
                system_prompt=_OVERVIEW_SEQUENCE_SYSTEM_PROMPT,
            ),
        )
    return _overview_sequence_agent


def _get_overview_teacher_agent() -> Agent[None, GeneratedOverviewTeacherNotes]:
    global _overview_teacher_agent
    if _overview_teacher_agent is None:
        _configure_env()
        _overview_teacher_agent = cast(
            Agent[None, GeneratedOverviewTeacherNotes],
            Agent(
                "openrouter:xiaomi/mimo-v2-pro",
                output_type=GeneratedOverviewTeacherNotes,
                system_prompt=_OVERVIEW_NOTES_SYSTEM_PROMPT,
            ),
        )
    return _overview_teacher_agent


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


def _extract_builds_on_numbers(text: str) -> list[int]:
    found: list[int] = []
    for match in re.finditer(r"les\s*(\d+)", text, flags=re.IGNORECASE):
        try:
            found.append(int(match.group(1)))
        except ValueError:
            continue
    return sorted(set(found))


def _validate_overview_for_context(overview: GeneratedLesplanOverview, ctx: LesplanContext) -> None:
    if not overview.series_themes:
        raise ValueError("series_themes must contain at least one theme")
    if not overview.learning_goals:
        raise ValueError("learning_goals must contain at least one goal")
    if not overview.key_knowledge:
        raise ValueError("key_knowledge must contain at least one knowledge item")

    if len(overview.lesson_outline) != ctx.num_lessons:
        raise ValueError(
            f"lesson_outline must contain exactly {ctx.num_lessons} lessons, got {len(overview.lesson_outline)}"
        )

    expected_numbers = list(range(1, ctx.num_lessons + 1))
    lesson_numbers = sorted(item.lesson_number for item in overview.lesson_outline)
    if lesson_numbers != expected_numbers:
        raise ValueError(f"lesson numbers must be contiguous {expected_numbers}, got {lesson_numbers}")

    paragraph_count = len(ctx.paragraphs)
    covered_paragraph_indices: set[int] = set()
    valid_lessons = set(expected_numbers)
    for lesson in overview.lesson_outline:
        if not (2 <= len(lesson.concept_tags) <= 4):
            raise ValueError(f"lesson {lesson.lesson_number} must have 2-4 concept_tags")
        if not lesson.teaching_approach_hint.strip():
            raise ValueError(f"lesson {lesson.lesson_number} must include teaching_approach_hint")
        if _is_placeholder_lesson_text(lesson.subject_focus):
            raise ValueError(f"lesson {lesson.lesson_number} has placeholder subject_focus")
        if _is_placeholder_lesson_text(lesson.description):
            raise ValueError(f"lesson {lesson.lesson_number} has placeholder description")
        if _squash_text(lesson.lesson_intention) == _squash_text(lesson.description):
            raise ValueError(f"lesson {lesson.lesson_number} lesson_intention should add detail beyond description")
        if _squash_text(lesson.end_understanding) == _squash_text(lesson.description):
            raise ValueError(f"lesson {lesson.lesson_number} end_understanding should add detail beyond description")

        for prior in lesson.builds_on_lessons:
            if prior >= lesson.lesson_number:
                raise ValueError(
                    f"lesson {lesson.lesson_number} has invalid builds_on_lessons entry {prior} (must be earlier lesson)"
                )
            if prior < 1 or prior not in valid_lessons:
                raise ValueError(
                    f"lesson {lesson.lesson_number} has invalid builds_on_lessons entry {prior} (unknown lesson)"
                )

        inferred_from_text = _extract_builds_on_numbers(lesson.builds_on)
        for inferred in inferred_from_text:
            if inferred >= lesson.lesson_number:
                raise ValueError(
                    f"lesson {lesson.lesson_number} references les {inferred} in builds_on, but it is not earlier"
                )

        for paragraph_index in lesson.paragraph_indices:
            if paragraph_index < 0 or paragraph_index >= paragraph_count:
                raise ValueError(
                    f"lesson {lesson.lesson_number} has paragraph index {paragraph_index}, "
                    f"but valid range is 0..{paragraph_count - 1}"
                )
            covered_paragraph_indices.add(paragraph_index)

    missing_paragraphs = sorted(set(range(paragraph_count)) - covered_paragraph_indices)
    if missing_paragraphs:
        raise ValueError(
            f"lesson_outline.paragraph_indices must cover all selected paragraphs; missing indices: {missing_paragraphs}"
        )

    goal_set = {goal.strip() for goal in overview.learning_goals if goal.strip()}
    covered_goals: set[str] = set()
    for item in overview.goal_coverage:
        goal_name = item.goal.strip()
        if not goal_name:
            raise ValueError("goal_coverage contains an empty goal name")
        if goal_name not in goal_set:
            raise ValueError(f"goal_coverage references unknown goal: {goal_name}")
        if not item.lesson_numbers:
            raise ValueError(f"goal_coverage for '{goal_name}' must contain at least one lesson number")
        for lesson_number in item.lesson_numbers:
            if lesson_number not in valid_lessons:
                raise ValueError(
                    f"goal_coverage for '{goal_name}' references invalid lesson number {lesson_number}"
                )
        covered_goals.add(goal_name)

    missing_goals = sorted(goal_set - covered_goals)
    if missing_goals:
        raise ValueError(f"goal_coverage must contain every learning goal; missing: {missing_goals}")

    knowledge_set = {item.strip() for item in overview.key_knowledge if item.strip()}
    covered_knowledge: set[str] = set()
    for item in overview.knowledge_coverage:
        knowledge_name = item.knowledge.strip()
        if not knowledge_name:
            raise ValueError("knowledge_coverage contains an empty knowledge name")
        if knowledge_name not in knowledge_set:
            raise ValueError(f"knowledge_coverage references unknown key_knowledge item: {knowledge_name}")
        if not item.lesson_numbers:
            raise ValueError(
                f"knowledge_coverage for '{knowledge_name}' must contain at least one lesson number"
            )
        for lesson_number in item.lesson_numbers:
            if lesson_number not in valid_lessons:
                raise ValueError(
                    f"knowledge_coverage for '{knowledge_name}' references invalid lesson number {lesson_number}"
                )
        covered_knowledge.add(knowledge_name)

    missing_knowledge = sorted(knowledge_set - covered_knowledge)
    if missing_knowledge:
        raise ValueError(
            f"knowledge_coverage must contain every key_knowledge item; missing: {missing_knowledge}"
        )


def _unique_non_empty(values: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if limit is not None and len(result) >= limit:
            break
    return result


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) >= 4}


def _derive_concept_tags(subject_focus: str, key_knowledge: list[str], lesson_number: int) -> list[str]:
    focus_parts = [
        part.strip()
        for part in re.split(r"[,;:/-]", subject_focus)
        if part.strip()
    ]
    knowledge_parts = [item.split(":")[0].strip() for item in key_knowledge[:3] if item.strip()]
    tags = _unique_non_empty([*focus_parts, *knowledge_parts, f"les {lesson_number}"], limit=4)
    while len(tags) < 2:
        tags.append(f"thema {lesson_number}")
    return tags[:4]


def _squash_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_placeholder_lesson_text(text: str) -> bool:
    normalized = _squash_text(text).lower()
    if not normalized:
        return True
    if re.fullmatch(r"les\s*\d+", normalized):
        return True
    markers = (
        "in deze les staat",
        "samenvatting ontbreekt",
        "niet beschikbaar",
        "staat les",
    )
    return any(marker in normalized for marker in markers)


def _short_topic(text: str, *, max_words: int = 9) -> str:
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    return f"{' '.join(words[:max_words]).rstrip(',.;:')}..."


def _derive_lesson_topic(
    lesson: LessonOutlineItem,
    ctx: LesplanContext,
    key_knowledge: list[str],
) -> str:
    paragraph_titles: list[str] = []
    for paragraph_index in lesson.paragraph_indices:
        if 0 <= paragraph_index < len(ctx.paragraphs):
            title = str(ctx.paragraphs[paragraph_index].get("title") or "").strip()
            if title:
                paragraph_titles.append(_short_topic(title))
        if len(paragraph_titles) >= 2:
            break

    if paragraph_titles:
        if len(paragraph_titles) == 1:
            return paragraph_titles[0]
        return f"{paragraph_titles[0]} en {paragraph_titles[1]}"

    valid_tags = [tag for tag in lesson.concept_tags if not re.fullmatch(r"les\s*\d+", tag, flags=re.IGNORECASE)]
    if valid_tags:
        return ", ".join(valid_tags[:2])

    if key_knowledge:
        return _short_topic(key_knowledge[min(lesson.lesson_number - 1, len(key_knowledge) - 1)])

    return f"kernonderwerp van les {lesson.lesson_number}"


def _default_description_for_style(topic: str, style: str) -> str:
    templates = {
        "intro_schema": (
            f"Kennismaking met {topic}: leerlingen verkennen de kernbegrippen via een korte startopdracht en bouwen "
            "samen een eerste inhoudelijk kader op."
        ),
        "source": (
            f"Leerlingen onderzoeken {topic} met een bron- of beeldanalyse en bespreken klassikaal welke conclusies "
            "ze daaruit trekken."
        ),
        "cause_effect": (
            f"Leerlingen brengen bij {topic} oorzaken en gevolgen in kaart en lichten de belangrijkste verbanden toe."
        ),
        "compare": (
            f"Leerlingen vergelijken perspectieven of systemen binnen {topic} en onderbouwen overeenkomsten en "
            "verschillen met vakbegrippen."
        ),
        "timeline": (
            f"Leerlingen plaatsen gebeurtenissen rond {topic} in tijd en context en verklaren waarom de volgorde "
            "inhoudelijk logisch is."
        ),
        "debate": (
            f"Leerlingen verkennen {topic} via een stellingenspel en beargumenteren hun positie met inhoudelijke "
            "voorbeelden."
        ),
        "application": (
            f"Leerlingen passen kennis over {topic} toe in een korte opdracht waarin ze inzichten uit eerdere lessen "
            "combineren."
        ),
    }
    return templates.get(style, templates["intro_schema"])


def _default_lesson_intention(topic: str, style: str) -> str:
    if style in {"compare", "cause_effect"}:
        return f"Leerlingen kunnen {topic.lower()} analyseren door verbanden en verschillen expliciet te benoemen."
    return f"Leerlingen verkennen {topic.lower()} en koppelen dit aan de belangrijkste begrippen uit de reeks."


def _default_end_understanding(topic: str) -> str:
    return f"Aan het einde kunnen leerlingen de kern van {topic.lower()} uitleggen met passende vakbegrippen."


def _default_sequence_rationale(lesson_number: int, total_lessons: int) -> str:
    if lesson_number == 1:
        return "Deze les legt de basiscontext en kernbegrippen voor de rest van de reeks."
    if lesson_number == total_lessons:
        return "Deze les rondt de reeks af door inzichten uit eerdere lessen samen te brengen."
    return f"Deze les verdiept de opbouw na les {lesson_number - 1} en bereidt voor op de volgende stap."


def _enrich_generic_lesson_text(
    lessons: list[LessonOutlineItem],
    *,
    ctx: LesplanContext,
    key_knowledge: list[str],
) -> None:
    total_lessons = len(lessons)
    for lesson in lessons:
        inferred_style = _teaching_style_from_content(lesson.subject_focus, lesson.description) or _teaching_style_from_position(
            lesson.lesson_number,
            total_lessons,
        )
        topic = _derive_lesson_topic(lesson, ctx, key_knowledge)

        if _is_placeholder_lesson_text(lesson.subject_focus):
            lesson.subject_focus = topic

        if _is_placeholder_lesson_text(lesson.description):
            lesson.description = _default_description_for_style(topic, inferred_style)

        if _is_placeholder_lesson_text(lesson.lesson_intention) or _squash_text(lesson.lesson_intention) == _squash_text(lesson.description):
            lesson.lesson_intention = _default_lesson_intention(topic, inferred_style)

        if _is_placeholder_lesson_text(lesson.end_understanding) or _squash_text(lesson.end_understanding) == _squash_text(lesson.description):
            lesson.end_understanding = _default_end_understanding(topic)

        if _is_placeholder_lesson_text(lesson.sequence_rationale):
            lesson.sequence_rationale = _default_sequence_rationale(lesson.lesson_number, total_lessons)


def _normalize_lesson_outline_for_context(
    outline: list[LessonOutlineItem],
    ctx: LesplanContext,
    key_knowledge: list[str],
) -> list[LessonOutlineItem]:
    by_number: dict[int, LessonOutlineItem] = {}
    for index, raw in enumerate(outline):
        lesson_number = raw.lesson_number if raw.lesson_number > 0 else index + 1
        if lesson_number < 1:
            continue
        if lesson_number not in by_number:
            by_number[lesson_number] = raw

    paragraph_count = len(ctx.paragraphs)
    normalized: list[LessonOutlineItem] = []
    for lesson_number in range(1, ctx.num_lessons + 1):
        raw = by_number.get(lesson_number, LessonOutlineItem(lesson_number=lesson_number))
        subject_focus = raw.subject_focus.strip() or f"Les {lesson_number}"
        description = raw.description.strip()
        teaching_approach_hint = raw.teaching_approach_hint.strip() or _default_lesson_teaching_hint(
            ctx=ctx,
            lesson_number=lesson_number,
            total_lessons=ctx.num_lessons,
            subject_focus=subject_focus,
            description=description,
        )
        builds_on_lessons = sorted({number for number in raw.builds_on_lessons if 1 <= number < lesson_number})
        if not builds_on_lessons and lesson_number > 1:
            builds_on_lessons = [lesson_number - 1]
        builds_on = raw.builds_on.strip() or (
            "Start van de reeks."
            if lesson_number == 1
            else f"Bouwt voort op les {builds_on_lessons[-1]}."
        )

        concept_tags = _unique_non_empty(raw.concept_tags, limit=4)
        if len(concept_tags) < 2:
            concept_tags = _derive_concept_tags(subject_focus, key_knowledge, lesson_number)
        while len(concept_tags) < 2:
            concept_tags.append(f"les {lesson_number}")
        concept_tags = concept_tags[:4]

        paragraph_indices = sorted(
            {
                index
                for index in raw.paragraph_indices
                if 0 <= index < paragraph_count
            }
        )
        if not paragraph_indices and paragraph_count > 0:
            paragraph_indices = [min(lesson_number - 1, paragraph_count - 1)]

        lesson_intention = raw.lesson_intention.strip() or description
        end_understanding = raw.end_understanding.strip() or description
        sequence_rationale = raw.sequence_rationale.strip() or (
            "Legt het fundament voor de rest van de reeks."
            if lesson_number == 1
            else builds_on
        )

        normalized.append(
            LessonOutlineItem(
                lesson_number=lesson_number,
                subject_focus=subject_focus,
                description=description,
                teaching_approach_hint=teaching_approach_hint,
                builds_on=builds_on,
                concept_tags=concept_tags,
                lesson_intention=lesson_intention,
                end_understanding=end_understanding,
                sequence_rationale=sequence_rationale,
                builds_on_lessons=builds_on_lessons,
                paragraph_indices=paragraph_indices,
            )
        )

    if paragraph_count > 0 and normalized:
        covered = {index for lesson in normalized for index in lesson.paragraph_indices}
        missing = [index for index in range(paragraph_count) if index not in covered]
        for offset, paragraph_index in enumerate(missing):
            lesson = normalized[offset % len(normalized)]
            lesson.paragraph_indices = sorted(set([*lesson.paragraph_indices, paragraph_index]))

    _enrich_generic_lesson_text(normalized, ctx=ctx, key_knowledge=key_knowledge)
    _diversify_generic_teaching_hints(normalized, ctx=ctx)

    return normalized


def _match_lesson_numbers(text: str, outline: list[LessonOutlineItem]) -> list[int]:
    if not outline:
        return []
    target_tokens = _tokenize(text)
    if not target_tokens:
        return [outline[0].lesson_number]

    scored: list[tuple[int, int]] = []
    for lesson in outline:
        lesson_text = " ".join(
            [
                lesson.subject_focus,
                lesson.description,
                lesson.teaching_approach_hint,
                lesson.builds_on,
                lesson.lesson_intention,
                lesson.end_understanding,
                lesson.sequence_rationale,
                " ".join(lesson.concept_tags),
            ]
        )
        score = len(target_tokens & _tokenize(lesson_text))
        scored.append((lesson.lesson_number, score))

    max_score = max(score for _, score in scored)
    if max_score <= 0:
        return [outline[0].lesson_number]
    return [number for number, score in scored if score == max_score][:3]


def _build_goal_coverage(
    goals: list[str],
    outline: list[LessonOutlineItem],
) -> list[GoalCoverageItem]:
    coverage: list[GoalCoverageItem] = []
    for goal in goals:
        lesson_numbers = _match_lesson_numbers(goal, outline)
        lesson_label = ", ".join(f"les {number}" for number in lesson_numbers)
        coverage.append(
            GoalCoverageItem(
                goal=goal,
                lesson_numbers=lesson_numbers,
                rationale=f"Dit leerdoel wordt expliciet geoefend in {lesson_label}.",
            )
        )
    return coverage


def _build_knowledge_coverage(
    knowledge_items: list[str],
    outline: list[LessonOutlineItem],
) -> list[KnowledgeCoverageItem]:
    coverage: list[KnowledgeCoverageItem] = []
    for knowledge in knowledge_items:
        lesson_numbers = _match_lesson_numbers(knowledge, outline)
        lesson_label = ", ".join(f"les {number}" for number in lesson_numbers)
        coverage.append(
            KnowledgeCoverageItem(
                knowledge=knowledge,
                lesson_numbers=lesson_numbers,
                rationale=f"Dit kernbegrip komt terug in {lesson_label}.",
            )
        )
    return coverage


def _normalize_approval_readiness(
    readiness: ApprovalReadiness,
    *,
    has_goals: bool,
    has_knowledge: bool,
    has_outline: bool,
) -> ApprovalReadiness:
    checklist = _unique_non_empty(readiness.checklist)
    if not checklist:
        checklist = [
            "Doelen sluiten aan op de klas.",
            "Kernkennis is volledig en correct.",
            "Lesvolgorde bouwt logisch op.",
        ]
    rationale = readiness.rationale.strip() or "De reeks is klaar om inhoudelijk beoordeeld te worden."
    open_questions = _unique_non_empty(readiness.open_questions)
    ready_for_approval = readiness.ready_for_approval and has_goals and has_knowledge and has_outline
    return ApprovalReadiness(
        ready_for_approval=ready_for_approval,
        rationale=rationale,
        checklist=checklist,
        open_questions=open_questions,
    )


def _first_sentence(text: str) -> str:
    clean = text.strip()
    if not clean:
        return ""
    match = re.match(r"(.+?[.!?])(?:\s|$)", clean)
    if match:
        return match.group(1).strip()
    return clean


def _contains_delivery_hint(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "activering",
        "instructie",
        "verwerking",
        "reflectie",
        "differenti",
        "werkvorm",
        "opbouw",
        "begeleid",
    )
    return any(marker in lowered for marker in markers)


def _default_delivery_sentence(ctx: LesplanContext) -> str:
    level = (ctx.level or "deze klas").lower()
    year = (ctx.school_year or "").lower()
    subject = (ctx.book_subject or "dit onderwerp").lower()
    difficulty_hint = ""
    if ctx.difficulty == "Rood":
        difficulty_hint = ", met extra korte stappen en frequente begrip-checks"
    elif ctx.difficulty == "Oranje":
        difficulty_hint = ", met extra begeleide verwerking en tussentijdse checks"

    return (
        "Didactische hoofdroute: start elke les met een korte activering, geef daarna gerichte instructie, "
        f"laat leerlingen begeleid verwerken en sluit af met een check op begrip, bij {subject}, afgestemd op "
        f"{level} {year} ({ctx.class_size} leerlingen{difficulty_hint})."
    )


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_generic_teaching_hint(text: str) -> bool:
    normalized = _normalize_whitespace(text).lower()
    if not normalized:
        return True
    if normalized.startswith(
        (
            "korte activering, daarna gerichte uitleg over",
            "start met een korte activering, daarna gerichte uitleg over",
        )
    ):
        return True
    return (
        "begeleide verwerking" in normalized
        and "check op begrip" in normalized
        and len(normalized.split()) <= 28
    )


def _lesson_scaffold_clause(ctx: LesplanContext) -> str:
    level = (ctx.level or "").lower()
    year = (ctx.school_year or "").lower()
    if ctx.difficulty == "Rood":
        return "met kleine stappen, extra modeling en frequente checks"
    if ctx.difficulty == "Oranje":
        return "met begeleide tussenstappen en extra checkmomenten"
    if "vmbo" in level or year in {"leerjaar_1", "leerjaar_2"}:
        return "met korte stappen en visuele steun"
    if "vwo" in level or "gymnasium" in level:
        return "met ruimte voor zelfstandige onderbouwing"
    return "met heldere instructie en gerichte feedback"


def _teaching_style_from_content(subject_focus: str, description: str) -> str | None:
    text = f"{subject_focus} {description}".lower()
    if any(token in text for token in ("vergelijk", "verschil", "overeenkomst", "versus")):
        return "compare"
    if any(token in text for token in ("oorzaak", "gevolg", "crisis", "ontwikkeling", "revolutie")):
        return "cause_effect"
    if any(token in text for token in ("tijdlijn", "tijdvak", "chronolog", "periode", "jaartal")):
        return "timeline"
    if any(token in text for token in ("bron", "tekst", "afbeeld", "kaart", "grafiek")):
        return "source"
    if any(token in text for token in ("macht", "ideologie", "dilemma", "stelling", "debat")):
        return "debate"
    return None


def _teaching_style_from_position(lesson_number: int, total_lessons: int) -> str:
    if lesson_number <= 1:
        return "intro_schema"
    if lesson_number == total_lessons:
        return "application"
    if total_lessons >= 4 and lesson_number >= total_lessons - 1:
        return "debate"
    cycle = ("source", "cause_effect", "compare")
    return cycle[(lesson_number - 2) % len(cycle)]


def _render_lesson_teaching_hint(
    *,
    ctx: LesplanContext,
    lesson_number: int,
    subject_focus: str,
    style: str,
) -> str:
    focus = subject_focus.strip().lower() or f"les {lesson_number}"
    scaffold = _lesson_scaffold_clause(ctx)
    templates = {
        "intro_schema": (
            f"Start met een instapvraag en bouw samen een begrippenschema rond {focus}; leerlingen verwerken dit "
            f"daarna in duo's en sluiten af met een korte begripcheck, {scaffold}."
        ),
        "source": (
            f"Introduceer {focus} via een korte bron- of beeldanalyse, bespreek klassikaal wat opvalt en laat "
            f"leerlingen hun conclusie onderbouwen, {scaffold}."
        ),
        "cause_effect": (
            f"Werk bij {focus} met een oorzaak-gevolgketen op het bord; leerlingen vullen de schakels begeleid aan "
            f"en passen die daarna toe op een korte casus, {scaffold}."
        ),
        "compare": (
            f"Behandel {focus} met een vergelijkingsschema van overeenkomsten en verschillen; leerlingen vullen dit "
            f"in tweetallen in en lichten een keuze toe, {scaffold}."
        ),
        "timeline": (
            f"Laat leerlingen {focus} structureren met een korte tijdlijn- of ordenopdracht en bespreek daarna "
            f"samen waarom de volgorde klopt, {scaffold}."
        ),
        "debate": (
            f"Gebruik bij {focus} een korte stelling of dilemma, laat leerlingen positie kiezen en die met een "
            f"argument verdedigen, gevolgd door een reflectiecheck, {scaffold}."
        ),
        "application": (
            f"Laat leerlingen {focus} toepassen in een mini-opdracht (schema, tijdlijn of uitlegkaart) waarin ze "
            f"kennis uit eerdere lessen combineren, {scaffold}."
        ),
    }
    return _normalize_whitespace(templates.get(style, templates["intro_schema"]))


def _default_lesson_teaching_hint(
    *,
    ctx: LesplanContext,
    lesson_number: int,
    total_lessons: int,
    subject_focus: str,
    description: str,
) -> str:
    style = _teaching_style_from_content(subject_focus, description) or _teaching_style_from_position(
        lesson_number,
        total_lessons,
    )
    return _render_lesson_teaching_hint(
        ctx=ctx,
        lesson_number=lesson_number,
        subject_focus=subject_focus,
        style=style,
    )


def _diversify_generic_teaching_hints(
    lessons: list[LessonOutlineItem],
    *,
    ctx: LesplanContext,
) -> None:
    if not lessons:
        return

    used_styles: set[str] = set()
    seen_hints: set[str] = set()
    style_order = ["intro_schema", "source", "cause_effect", "compare", "timeline", "debate", "application"]
    total_lessons = len(lessons)

    for lesson in lessons:
        current_hint = _normalize_whitespace(lesson.teaching_approach_hint)
        signature = current_hint.lower()
        is_duplicate = signature in seen_hints
        mentions_placeholder_lesson = bool(
            re.search(rf"\b(?:rond|over)\s+les\s*{lesson.lesson_number}\b", signature)
        )
        seen_hints.add(signature)

        if (
            current_hint
            and not _is_generic_teaching_hint(current_hint)
            and not is_duplicate
            and not mentions_placeholder_lesson
        ):
            continue

        preferred = _teaching_style_from_content(lesson.subject_focus, lesson.description) or _teaching_style_from_position(
            lesson.lesson_number,
            total_lessons,
        )
        chosen = preferred
        if chosen in used_styles:
            for candidate in style_order:
                if candidate not in used_styles:
                    chosen = candidate
                    break
        used_styles.add(chosen)
        lesson.teaching_approach_hint = _render_lesson_teaching_hint(
            ctx=ctx,
            lesson_number=lesson.lesson_number,
            subject_focus=lesson.subject_focus,
            style=chosen,
        )


def _ensure_series_summary_includes_delivery(
    *,
    series_summary: str,
    learning_progression: str,
    recommended_approach: str,
    didactic_approach: str,
    ctx: LesplanContext,
) -> str:
    plain_base = re.sub(r"[*_`#>-]", "", series_summary or "").replace("\n", " ").strip()
    plain_progression = re.sub(r"[*_`#>-]", "", learning_progression or "").replace("\n", " ").strip()
    topic = _first_sentence(plain_base) or (
        f"Deze reeks behandelt {ctx.book_subject or 'de kern van dit onderwerp'} over {ctx.num_lessons} lessen."
    )
    progression = _first_sentence(plain_progression) or (
        "De reeks bouwt van basisbegrippen naar toepassing en samenhang."
    )

    recommended_sentence = _first_sentence(recommended_approach)
    didactic_sentence = _first_sentence(didactic_approach)
    delivery = recommended_sentence or didactic_sentence
    if not delivery:
        delivery = _default_delivery_sentence(ctx)
    elif not _contains_delivery_hint(delivery):
        delivery = f"{delivery} {_default_delivery_sentence(ctx)}"

    profile_bits = [
        f"vak: {ctx.book_subject or 'onbekend'}",
        f"niveau: {ctx.level}",
        f"leerjaar: {ctx.school_year}",
        f"klasgrootte: {ctx.class_size}",
    ]
    if ctx.difficulty:
        profile_bits.append(f"moeilijkheid: {ctx.difficulty}")
    profile = ", ".join(profile_bits)

    return (
        f"- **Onderwerp:** {topic}\n"
        f"- **Opbouw over {ctx.num_lessons} lessen:** {progression}\n"
        f"- **Didactische aanpak voor deze klas:** {delivery} ({profile})."
    )


def _compose_overview_from_parts(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
    sequence: GeneratedOverviewSequence,
    teacher_notes: GeneratedOverviewTeacherNotes,
) -> GeneratedLesplanOverview:
    subject_label = (ctx.book_subject or "dit onderwerp").strip()
    learning_goals = _unique_non_empty(sequence.learning_goals, limit=6)
    if not learning_goals:
        learning_goals = ["Leerlingen kunnen de kern van de reeks uitleggen en toepassen."]

    key_knowledge = _unique_non_empty(sequence.key_knowledge, limit=10)
    if not key_knowledge:
        key_knowledge = ["Kernkennis uit de geselecteerde paragrafen."]

    lesson_outline = _normalize_lesson_outline_for_context(sequence.lesson_outline, ctx, key_knowledge)
    series_themes = _unique_non_empty(identity.series_themes, limit=6)
    if not series_themes:
        series_themes = _unique_non_empty(key_knowledge[:5], limit=5) or ["Hoofdthema"]

    title = identity.title.strip() or f"Lessenreeks {subject_label}"
    series_summary = identity.series_summary.strip() or (
        f"Deze lessenreeks behandelt {subject_label} in {ctx.num_lessons} opeenvolgende lessen."
    )
    recommended_approach = teacher_notes.recommended_approach.strip() or (
        "Werk met duidelijke stappen, veel activering en regelmatige controles op begrip."
    )
    learning_progression = teacher_notes.learning_progression.strip() or (
        "De reeks start met basisbegrippen, bouwt per les verder op en werkt toe naar samenhangend begrip."
    )
    didactic_approach = teacher_notes.didactic_approach.strip() or (
        "Gebruik een vaste lesstructuur: activeren, instructie, begeleide verwerking en korte reflectie."
    )
    series_summary = _ensure_series_summary_includes_delivery(
        series_summary=series_summary,
        learning_progression=learning_progression,
        recommended_approach=recommended_approach,
        didactic_approach=didactic_approach,
        ctx=ctx,
    )

    goal_coverage = _build_goal_coverage(learning_goals, lesson_outline)
    knowledge_coverage = _build_knowledge_coverage(key_knowledge, lesson_outline)
    approval_readiness = _normalize_approval_readiness(
        teacher_notes.approval_readiness,
        has_goals=bool(learning_goals),
        has_knowledge=bool(key_knowledge),
        has_outline=bool(lesson_outline),
    )

    return GeneratedLesplanOverview(
        title=title,
        series_summary=series_summary,
        series_themes=series_themes,
        learning_goals=learning_goals,
        key_knowledge=key_knowledge,
        recommended_approach=recommended_approach,
        learning_progression=learning_progression,
        lesson_outline=lesson_outline,
        goal_coverage=goal_coverage,
        knowledge_coverage=knowledge_coverage,
        approval_readiness=approval_readiness,
        didactic_approach=didactic_approach,
    )


def _build_history_block(history: list[dict[str, Any]]) -> str:
    if not history:
        return ""
    history_lines = "\n".join(
        f"{'Docent' if message.get('role') == 'teacher' else 'Assistent'}: {message.get('content', '')}"
        for message in history
    )
    return f"## Gespreksgeschiedenis\n{history_lines}"


def _build_overview_background(
    ctx: LesplanContext,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    blocks = [_build_context_block(ctx)]
    if current_overview is not None:
        blocks.append(f"## Huidig overzicht\n{_build_overview_text(current_overview)}")
    if history:
        blocks.append(_build_history_block(history))
    return "\n\n".join(blocks)


def _build_identity_prompt(
    ctx: LesplanContext,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    background = _build_overview_background(ctx, current_overview=current_overview, history=history)
    return (
        f"{background}\n\n"
        "Schrijf alleen de reeksidentiteit voor deze reviewfase: title, series_summary en series_themes. "
        "Geef series_summary in markdown met 3 bullets: Onderwerp, Opbouw over de reeks, Didactische aanpak voor deze klas."
    )


def _build_sequence_prompt(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    background = _build_overview_background(ctx, current_overview=current_overview, history=history)
    identity_block = (
        "## Reeksidentiteit\n"
        f"Titel: {identity.title}\n"
        f"Samenvatting: {identity.series_summary}\n"
        f"Thema's: {', '.join(identity.series_themes)}"
    )
    return (
        f"{background}\n\n{identity_block}\n\n"
        "Schrijf alleen learning_goals, key_knowledge en lesson_outline voor deze reviewfase. "
        "Zorg dat elke les een korte teaching_approach_hint bevat (hoe de docent deze stof aanbiedt), "
        "met zichtbare variatie in werkvorm tussen lessen."
    )


def _build_teacher_notes_prompt(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
    sequence: GeneratedOverviewSequence,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    background = _build_overview_background(ctx, current_overview=current_overview, history=history)
    sequence_lines = "\n".join(
        f"- Les {item.lesson_number}: {item.subject_focus} ({', '.join(item.concept_tags)})"
        for item in sequence.lesson_outline
    )
    context_block = (
        "## Reekscontext\n"
        f"Titel: {identity.title}\n"
        f"Thema's: {', '.join(identity.series_themes)}\n"
        f"Leerdoelen: {len(sequence.learning_goals)}\n"
        f"Kernkennis: {len(sequence.key_knowledge)}\n"
        f"Lesopbouw:\n{sequence_lines}"
    )
    return (
        f"{background}\n\n{context_block}\n\n"
        "Schrijf alleen recommended_approach, learning_progression, didactic_approach en approval_readiness."
    )


def _build_revision_assistant_message(history: list[dict[str, Any]]) -> str:
    teacher_messages = [
        str(message.get("content", "")).strip()
        for message in history
        if message.get("role") == "teacher" and str(message.get("content", "")).strip()
    ]
    if not teacher_messages:
        return "Ik heb het overzicht bijgewerkt. Controleer of de opbouw en focus nu passen bij je klas."
    latest = teacher_messages[-1].splitlines()[0].strip()
    if len(latest) > 120:
        latest = f"{latest[:117].rstrip()}..."
    return (
        f"Ik heb je feedback verwerkt ({latest}). "
        "Bekijk vooral de aangepaste lesvolgorde, doelen en docentnotities."
    )


def _build_overview_text(overview: GeneratedLesplanOverview) -> str:
    learning_goals_lines = "\n".join(f"  - {item}" for item in overview.learning_goals)
    key_knowledge_lines = "\n".join(f"  - {item}" for item in overview.key_knowledge)
    series_themes_lines = "\n".join(f"  - {item}" for item in overview.series_themes)
    lesson_outline_lines = "\n".join(
        f"  Les {item.lesson_number}: {item.subject_focus} — {item.description}"
        f" [Teaching approach: {item.teaching_approach_hint}]"
        f" [Bouwt op: {item.builds_on}]"
        f" [Tags: {', '.join(item.concept_tags)}]"
        f" [Intention: {item.lesson_intention}]"
        f" [End understanding: {item.end_understanding}]"
        f" [Sequence rationale: {item.sequence_rationale}]"
        f" [Bouwt op lessen: {item.builds_on_lessons}]"
        f" [Paragrafen: {item.paragraph_indices}]"
        for item in overview.lesson_outline
    )
    goal_coverage_lines = "\n".join(
        f"  - {item.goal}: lessen {item.lesson_numbers} ({item.rationale})"
        for item in overview.goal_coverage
    )
    knowledge_coverage_lines = "\n".join(
        f"  - {item.knowledge}: lessen {item.lesson_numbers} ({item.rationale})"
        for item in overview.knowledge_coverage
    )
    readiness_checklist = "\n".join(f"  - {item}" for item in overview.approval_readiness.checklist) or "  - (geen)"
    readiness_questions = "\n".join(f"  - {item}" for item in overview.approval_readiness.open_questions) or "  - (geen)"
    return (
        f"Titel: {overview.title}\n"
        f"Seriesamenvatting:\n{overview.series_summary}\n\n"
        f"Series-thema's:\n{series_themes_lines}\n\n"
        f"Leerdoelen:\n{learning_goals_lines}\n\n"
        f"Kernkennis:\n{key_knowledge_lines}\n\n"
        f"Aanbevolen aanpak:\n{overview.recommended_approach}\n\n"
        f"Leerlijn:\n{overview.learning_progression}\n\n"
        f"Lesoverzicht:\n{lesson_outline_lines}\n\n"
        f"Goal coverage:\n{goal_coverage_lines}\n\n"
        f"Knowledge coverage:\n{knowledge_coverage_lines}\n\n"
        f"Approval readiness:\n"
        f"  ready_for_approval: {overview.approval_readiness.ready_for_approval}\n"
        f"  rationale: {overview.approval_readiness.rationale}\n"
        f"  checklist:\n{readiness_checklist}\n"
        f"  open_questions:\n{readiness_questions}\n\n"
        f"Didactische aanpak:\n{overview.didactic_approach}"
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


async def _stream_three_step_overview(
    ctx: LesplanContext,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    identity_result = await _get_overview_identity_agent().run(
        _build_identity_prompt(ctx, current_overview=current_overview, history=history)
    )
    identity = identity_result.output
    identity_partial = {
        "title": identity.title.strip(),
        "series_summary": identity.series_summary.strip(),
        "series_themes": _unique_non_empty(identity.series_themes, limit=6),
    }
    yield identity_partial, False

    sequence_result = await _get_overview_sequence_agent().run(
        _build_sequence_prompt(ctx, identity, current_overview=current_overview, history=history)
    )
    sequence = sequence_result.output
    sequence_goals = _unique_non_empty(sequence.learning_goals, limit=6)
    sequence_knowledge = _unique_non_empty(sequence.key_knowledge, limit=10)
    sequence_outline = _normalize_lesson_outline_for_context(sequence.lesson_outline, ctx, sequence_knowledge)
    sequence_partial = {
        "learning_goals": sequence_goals,
        "key_knowledge": sequence_knowledge,
        "lesson_outline": [item.model_dump(mode="json") for item in sequence_outline],
    }
    yield sequence_partial, False

    teacher_result = await _get_overview_teacher_agent().run(
        _build_teacher_notes_prompt(
            ctx,
            identity,
            GeneratedOverviewSequence(
                learning_goals=sequence_goals,
                key_knowledge=sequence_knowledge,
                lesson_outline=sequence_outline,
            ),
            current_overview=current_overview,
            history=history,
        )
    )
    teacher_notes = teacher_result.output
    readiness_partial = _normalize_approval_readiness(
        teacher_notes.approval_readiness,
        has_goals=bool(sequence_goals),
        has_knowledge=bool(sequence_knowledge),
        has_outline=bool(sequence_outline),
    )
    teacher_partial = {
        "recommended_approach": teacher_notes.recommended_approach.strip(),
        "learning_progression": teacher_notes.learning_progression.strip(),
        "didactic_approach": teacher_notes.didactic_approach.strip(),
        "approval_readiness": readiness_partial.model_dump(mode="json"),
    }
    identity_partial["series_summary"] = _ensure_series_summary_includes_delivery(
        series_summary=identity_partial["series_summary"],
        learning_progression=teacher_partial["learning_progression"],
        recommended_approach=teacher_partial["recommended_approach"],
        didactic_approach=teacher_partial["didactic_approach"],
        ctx=ctx,
    )
    teacher_partial["series_summary"] = identity_partial["series_summary"]
    yield teacher_partial, False

    composed_overview = _compose_overview_from_parts(
        ctx,
        GeneratedOverviewIdentity(
            title=identity_partial["title"],
            series_summary=identity_partial["series_summary"],
            series_themes=identity_partial["series_themes"],
        ),
        GeneratedOverviewSequence(
            learning_goals=sequence_goals,
            key_knowledge=sequence_knowledge,
            lesson_outline=sequence_outline,
        ),
        GeneratedOverviewTeacherNotes(
            recommended_approach=teacher_partial["recommended_approach"],
            learning_progression=teacher_partial["learning_progression"],
            didactic_approach=teacher_partial["didactic_approach"],
            approval_readiness=readiness_partial,
        ),
    )
    _validate_overview_for_context(composed_overview, ctx)
    yield composed_overview.model_dump(mode="json"), True


async def stream_overview(ctx: LesplanContext) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    async for payload, is_final in _stream_three_step_overview(ctx):
        yield payload, is_final


async def stream_revision(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
    history: list[dict[str, Any]],
) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    final_overview_payload: dict[str, Any] | None = None
    async for payload, is_final in _stream_three_step_overview(
        ctx,
        current_overview=overview,
        history=history,
    ):
        if is_final:
            final_overview_payload = payload
            continue
        yield payload, False

    if final_overview_payload is None:
        raise RuntimeError("Revision pipeline returned no final overview")

    yield {
        "overview": final_overview_payload,
        "assistant_message": _build_revision_assistant_message(history),
    }, True


async def generate_lessons(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
) -> list[GeneratedLessonPlan]:
    _validate_overview_for_context(overview, ctx)
    prompt = _build_lessons_prompt(ctx, overview)
    result = await _get_lessons_agent().run(prompt)
    return result.output.lessons
