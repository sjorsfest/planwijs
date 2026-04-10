import json
import logging
import re
import traceback
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from sqlmodel import select

from app.agents.lesplan_agent import (
    GeneratedLesplanOverview,
    GoalCoverageItem,
    KnowledgeCoverageItem,
    LesplanContext,
    LessonOutlineItem,
    generate_lessons,
)
from app.agents.lesplan.feedback_agent import apply_feedback
from app.agents.lesplan.pipeline import generate_overview
from app.agents.preparation_agent import PreparationContext, generate_preparation_todos
from app.database import SessionLocal
from app.models.book import Book
from app.models.book_chapter_paragraph import BookChapterParagraph
from app.models.school_class import Class
from app.models.enums import LesplanStatus
from app.models.lesplan import LesplanOverview, LesplanRequest, LessonPlan, LessonPreparationTodo
from app.models.classroom import Classroom
from app.models.method import Method
from app.models.subject import Subject as SubjectModel

from .types import (
    FeedbackItem,
    GoalCoverageItemResponse,
    KnowledgeCoverageItemResponse,
    LesplanOverviewResponse,
    LesplanResponse,
    LessonOutlineItemResponse,
    LessonPlanResponse,
    LessonPreparationTodoResponse,
    TimeSectionResponse,
)

logger = logging.getLogger(__name__)

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _todo_response(todo: LessonPreparationTodo) -> LessonPreparationTodoResponse:
    return LessonPreparationTodoResponse(
        id=todo.id,
        title=todo.title,
        description=todo.description,
        why=todo.why,
        status=todo.status.value,
        due_date=todo.due_date,
        created_at=todo.created_at,
    )


async def _get_lesson_or_404(session: AsyncSession, lesson_id: str) -> LessonPlan:
    lesson = await session.get(LessonPlan, lesson_id)
    if lesson is None:
        raise NotFoundError("Lesson not found")
    return lesson


async def _get_preparation_todo_or_404(session: AsyncSession, todo_id: str) -> LessonPreparationTodo:
    todo = await session.get(LessonPreparationTodo, todo_id)
    if todo is None:
        raise NotFoundError("Preparation todo not found")
    return todo


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        lines = []
        for line in value.splitlines():
            line = line.strip()
            if line.startswith("- "):
                line = line[2:].strip()
            numbered_prefix, separator, remainder = line.partition(" ")
            if (
                separator
                and len(numbered_prefix) > 1
                and numbered_prefix[-1] in {".", ")"}
                and numbered_prefix[:-1].isdigit()
            ):
                line = remainder.strip()
            if line:
                lines.append(line)

        if lines:
            return lines
        return [text]

    if value is None:
        return []

    text = str(value).strip()
    return [text] if text else []


def _normalize_learning_goals(value: Any) -> list[str]:
    return _normalize_string_list(value)


def _normalize_key_knowledge(value: Any) -> list[str]:
    return _normalize_string_list(value)


def _normalize_int_list(value: Any) -> list[int]:
    if isinstance(value, list):
        normalized: list[int] = []
        for item in value:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            normalized.append(number)
        return sorted(set(normalized))

    if isinstance(value, str):
        parts = re.split(r"[,\s]+", value.strip())
        normalized: list[int] = []
        for part in parts:
            if not part:
                continue
            try:
                normalized.append(int(part))
            except ValueError:
                continue
        return sorted(set(normalized))

    if isinstance(value, (int, float)):
        return [int(value)]

    return []


def _extract_builds_on_lessons(text: str) -> list[int]:
    numbers = [int(match.group(1)) for match in re.finditer(r"les\s*(\d+)", text, flags=re.IGNORECASE)]
    return sorted(set(numbers))


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


def _render_teaching_hint(lesson_number: int, subject_focus: str, style: str) -> str:
    focus = subject_focus.strip().lower() or f"les {lesson_number}"
    templates = {
        "intro_schema": (
            f"Start met een instapvraag en bouw samen een begrippenschema rond {focus}; laat leerlingen daarna "
            "in duo's een korte toepassing uitwerken en check klassikaal het begrip."
        ),
        "source": (
            f"Introduceer {focus} via een korte bron- of beeldanalyse, bespreek klassikaal wat opvalt en laat "
            "leerlingen hun conclusie onderbouwen."
        ),
        "cause_effect": (
            f"Werk bij {focus} met een oorzaak-gevolgketen op het bord; leerlingen vullen de schakels begeleid aan "
            "en passen die daarna toe op een korte casus."
        ),
        "compare": (
            f"Behandel {focus} met een vergelijkingsschema van overeenkomsten en verschillen; leerlingen vullen dit "
            "in tweetallen in en lichten een keuze toe."
        ),
        "timeline": (
            f"Laat leerlingen {focus} ordenen met een korte tijdlijnopdracht en bespreek samen waarom de volgorde "
            "klopt en wat de belangrijkste omslagpunten zijn."
        ),
        "debate": (
            f"Gebruik bij {focus} een korte stelling of dilemma, laat leerlingen positie kiezen met één argument en "
            "sluit af met een reflectiecheck."
        ),
        "application": (
            f"Laat leerlingen {focus} toepassen in een mini-opdracht (schema, tijdlijn of uitlegkaart) waarin ze "
            "kennis uit eerdere lessen combineren."
        ),
    }
    return _normalize_whitespace(templates.get(style, templates["intro_schema"]))


def _default_teaching_approach_hint(
    lesson_number: int,
    total_lessons: int,
    subject_focus: str,
    description: str,
) -> str:
    style = _teaching_style_from_content(subject_focus, description) or _teaching_style_from_position(
        lesson_number,
        total_lessons,
    )
    return _render_teaching_hint(lesson_number, subject_focus, style)


def _diversify_teaching_approach_hints(items: list[dict[str, Any]]) -> None:
    if not items:
        return

    used_styles: set[str] = set()
    seen_hints: set[str] = set()
    style_order = ["intro_schema", "source", "cause_effect", "compare", "timeline", "debate", "application"]
    total_lessons = len(items)

    for item in items:
        lesson_number = int(item.get("lesson_number") or 0)
        subject_focus = str(item.get("subject_focus") or "")
        description = str(item.get("description") or "")
        current_hint = _normalize_whitespace(str(item.get("teaching_approach_hint") or ""))
        signature = current_hint.lower()
        is_duplicate = signature in seen_hints
        seen_hints.add(signature)

        if current_hint and not _is_generic_teaching_hint(current_hint) and not is_duplicate:
            continue

        preferred = _teaching_style_from_content(subject_focus, description) or _teaching_style_from_position(
            lesson_number or 1,
            max(total_lessons, 1),
        )
        chosen = preferred
        if chosen in used_styles:
            for candidate in style_order:
                if candidate not in used_styles:
                    chosen = candidate
                    break
        used_styles.add(chosen)
        item["teaching_approach_hint"] = _render_teaching_hint(
            lesson_number or 1,
            subject_focus or f"les {lesson_number or 1}",
            chosen,
        )




def _normalize_lesson_outline(
    value: Any,
    *,
    num_lessons: int | None = None,
    paragraph_count: int | None = None,
) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue

        lesson_number_raw = raw.get("lesson_number")
        try:
            lesson_number = int(lesson_number_raw)
        except (TypeError, ValueError):
            lesson_number = index + 1
        if lesson_number < 1:
            lesson_number = index + 1

        subject_focus = str(raw.get("subject_focus") or "").strip() or f"Les {lesson_number}"
        description = str(raw.get("description") or "").strip() or subject_focus
        teaching_approach_hint = str(raw.get("teaching_approach_hint") or "").strip() or _default_teaching_approach_hint(
            lesson_number,
            num_lessons if num_lessons and num_lessons > 0 else len(raw_items) or 1,
            subject_focus,
            description,
        )
        builds_on = str(raw.get("builds_on") or "").strip()

        concept_tags = _normalize_string_list(raw.get("concept_tags"))
        if len(concept_tags) < 2:
            focus_tokens = [token for token in re.split(r"[,;:/\-\s]+", subject_focus) if token.strip()]
            concept_tags.extend(focus_tokens[: 2 - len(concept_tags)])
        while len(concept_tags) < 2:
            concept_tags.append(f"les {lesson_number}")
        concept_tags = concept_tags[:4]

        builds_on_lessons = _normalize_int_list(raw.get("builds_on_lessons"))
        if not builds_on_lessons and builds_on:
            builds_on_lessons = _extract_builds_on_lessons(builds_on)
        builds_on_lessons = sorted({number for number in builds_on_lessons if 1 <= number < lesson_number})

        paragraph_indices = _normalize_int_list(raw.get("paragraph_indices"))
        if paragraph_count is not None:
            paragraph_indices = [idx for idx in paragraph_indices if 0 <= idx < paragraph_count]
        if not paragraph_indices and paragraph_count and paragraph_count > 0:
            paragraph_indices = [min(max(lesson_number - 1, 0), paragraph_count - 1)]

        lesson_intention = str(raw.get("lesson_intention") or "").strip() or description
        end_understanding = str(raw.get("end_understanding") or "").strip() or description
        sequence_rationale = str(raw.get("sequence_rationale") or "").strip() or (builds_on or description)

        items.append(
            {
                "lesson_number": lesson_number,
                "subject_focus": subject_focus,
                "description": description,
                "teaching_approach_hint": teaching_approach_hint,
                "builds_on": builds_on,
                "concept_tags": concept_tags,
                "lesson_intention": lesson_intention,
                "end_understanding": end_understanding,
                "sequence_rationale": sequence_rationale,
                "builds_on_lessons": builds_on_lessons,
                "paragraph_indices": paragraph_indices,
            }
        )

    items.sort(key=lambda item: item["lesson_number"])
    if num_lessons is not None and num_lessons > 0:
        by_number = {item["lesson_number"]: item for item in items}
        filled: list[dict[str, Any]] = []
        for lesson_number in range(1, num_lessons + 1):
            existing = by_number.get(lesson_number)
            if existing is not None:
                filled.append(existing)
                continue
            fallback_paragraph = []
            if paragraph_count and paragraph_count > 0:
                fallback_paragraph = [min(max(lesson_number - 1, 0), paragraph_count - 1)]
            filled.append(
                {
                    "lesson_number": lesson_number,
                    "subject_focus": f"Les {lesson_number}",
                    "description": "Samenvatting ontbreekt in oudere data.",
                    "teaching_approach_hint": _default_teaching_approach_hint(
                        lesson_number,
                        num_lessons,
                        f"Les {lesson_number}",
                        "Samenvatting ontbreekt in oudere data.",
                    ),
                    "builds_on": f"Bouwt voort op les {lesson_number - 1}" if lesson_number > 1 else "Start van de reeks",
                    "concept_tags": ["hoofdlijn", f"les {lesson_number}"],
                    "lesson_intention": "Lesintentie niet beschikbaar in oudere data.",
                    "end_understanding": "Eindbegrip niet beschikbaar in oudere data.",
                    "sequence_rationale": "Toegevoegd als fallback voor oudere data.",
                    "builds_on_lessons": [lesson_number - 1] if lesson_number > 1 else [],
                    "paragraph_indices": fallback_paragraph,
                }
            )
        items = filled

    if paragraph_count and paragraph_count > 0 and items:
        covered = {idx for item in items for idx in item["paragraph_indices"]}
        missing = [idx for idx in range(paragraph_count) if idx not in covered]
        for offset, paragraph_index in enumerate(missing):
            target = items[offset % len(items)]
            target["paragraph_indices"] = sorted(set([*target["paragraph_indices"], paragraph_index]))

    _diversify_teaching_approach_hints(items)

    return items


def _normalize_goal_coverage(value: Any, goals: list[str], lesson_numbers: list[int]) -> list[dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for raw in value:
            if not isinstance(raw, dict):
                continue
            goal = str(raw.get("goal") or "").strip()
            if not goal:
                continue
            lesson_refs = [number for number in _normalize_int_list(raw.get("lesson_numbers")) if number in lesson_numbers]
            if not lesson_refs and lesson_numbers:
                lesson_refs = [lesson_numbers[0]]
            rationale = str(raw.get("rationale") or "").strip() or "Leerdoel gekoppeld aan deze lessen."
            coverage[goal] = {
                "goal": goal,
                "lesson_numbers": lesson_refs,
                "rationale": rationale,
            }

    for goal in goals:
        if goal not in coverage:
            coverage[goal] = {
                "goal": goal,
                "lesson_numbers": lesson_numbers[:1] if lesson_numbers else [],
                "rationale": "Automatisch toegevoegd voor complete dekking.",
            }

    ordered: list[dict[str, Any]] = []
    for goal in goals:
        ordered.append(coverage[goal])
    return ordered


def _normalize_knowledge_coverage(
    value: Any,
    knowledge_items: list[str],
    lesson_numbers: list[int],
) -> list[dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for raw in value:
            if not isinstance(raw, dict):
                continue
            knowledge = str(raw.get("knowledge") or "").strip()
            if not knowledge:
                continue
            lesson_refs = [number for number in _normalize_int_list(raw.get("lesson_numbers")) if number in lesson_numbers]
            if not lesson_refs and lesson_numbers:
                lesson_refs = [lesson_numbers[0]]
            rationale = str(raw.get("rationale") or "").strip() or "Kernkennis gekoppeld aan deze lessen."
            coverage[knowledge] = {
                "knowledge": knowledge,
                "lesson_numbers": lesson_refs,
                "rationale": rationale,
            }

    for knowledge in knowledge_items:
        if knowledge not in coverage:
            coverage[knowledge] = {
                "knowledge": knowledge,
                "lesson_numbers": lesson_numbers[:1] if lesson_numbers else [],
                "rationale": "Automatisch toegevoegd voor complete dekking.",
            }

    ordered: list[dict[str, Any]] = []
    for knowledge in knowledge_items:
        ordered.append(coverage[knowledge])
    return ordered


def _normalize_overview_payload(
    data: dict[str, Any],
    *,
    num_lessons: int | None = None,
    paragraph_count: int | None = None,
) -> dict[str, Any]:
    learning_goals = _normalize_learning_goals(data.get("learning_goals"))
    if not learning_goals:
        learning_goals = ["Leerlingen begrijpen de kern van de lessenreeks."]

    key_knowledge = _normalize_key_knowledge(data.get("key_knowledge"))
    lesson_outline = _normalize_lesson_outline(
        data.get("lesson_outline"),
        num_lessons=num_lessons,
        paragraph_count=paragraph_count,
    )
    if not key_knowledge:
        tag_fallbacks = []
        for item in lesson_outline:
            tag_fallbacks.extend(_normalize_string_list(item.get("concept_tags")))
        key_knowledge = tag_fallbacks[:6] or ["Kernbegrippen uit de geselecteerde paragrafen."]

    lesson_numbers = sorted(
        {
            int(item["lesson_number"])
            for item in lesson_outline
            if isinstance(item, dict) and isinstance(item.get("lesson_number"), int)
        }
    )

    series_summary = str(data.get("series_summary") or "").strip()
    if not series_summary:
        progression_text = str(data.get("learning_progression") or "").strip()
        series_summary = progression_text or "Samenvatting niet beschikbaar."

    series_themes = _normalize_string_list(data.get("series_themes"))
    if not series_themes:
        series_themes = key_knowledge[:5] if key_knowledge else ["Hoofdthema"]

    goal_coverage = _normalize_goal_coverage(data.get("goal_coverage"), learning_goals, lesson_numbers)
    knowledge_coverage = _normalize_knowledge_coverage(
        data.get("knowledge_coverage"),
        key_knowledge,
        lesson_numbers,
    )
    return {
        "title": str(data.get("title") or "").strip() or "Ongetitelde lessenreeks",
        "series_summary": series_summary,
        "series_themes": series_themes,
        "learning_goals": learning_goals,
        "key_knowledge": key_knowledge,
        "recommended_approach": str(data.get("recommended_approach") or "").strip(),
        "learning_progression": str(data.get("learning_progression") or "").strip(),
        "lesson_outline": lesson_outline,
        "goal_coverage": goal_coverage,
        "knowledge_coverage": knowledge_coverage,
        "didactic_approach": str(data.get("didactic_approach") or "").strip(),
    }


async def _lesson_response(session: AsyncSession, lesson: LessonPlan) -> LessonPlanResponse:
    todos_result = await session.execute(
        select(LessonPreparationTodo)
        .where(LessonPreparationTodo.lesson_plan_id == lesson.id)
        .order_by(LessonPreparationTodo.created_at.asc())  # type: ignore[union-attr]
    )
    todos = todos_result.scalars().all()
    return LessonPlanResponse(
        id=lesson.id,
        lesson_number=lesson.lesson_number,
        planned_date=lesson.planned_date,
        title=lesson.title,
        learning_objectives=lesson.learning_objectives,
        time_sections=[TimeSectionResponse(**item) for item in lesson.time_sections if isinstance(item, dict)],
        required_materials=lesson.required_materials,
        covered_paragraph_ids=lesson.covered_paragraph_ids,
        teacher_notes=lesson.teacher_notes,
        created_at=lesson.created_at,
        preparation_todos=[_todo_response(todo) for todo in todos],
    )


async def _build_context(session: AsyncSession, req: LesplanRequest) -> LesplanContext:
    classroom = await session.get(Class, req.class_id)
    book = await session.get(Book, req.book_id)
    if classroom is None or book is None:
        raise ValueError(f"Class {req.class_id} or Book {req.book_id} not found")

    method: Optional[Method] = None
    if book.method_id:
        method = await session.get(Method, book.method_id)

    subject_name = ""
    if book.subject_id:
        subject = await session.get(SubjectModel, book.subject_id)
        if subject is not None:
            subject_name = subject.name

    classroom_assets: list[str] | None = None
    if req.classroom_id:
        room = await session.get(Classroom, req.classroom_id)
        if room is not None:
            classroom_assets = room.assets or None

    paragraph_results = await session.execute(
        select(BookChapterParagraph).where(
            BookChapterParagraph.id.in_(req.selected_paragraph_ids)  # type: ignore[union-attr]
        )
    )
    paragraphs_by_id = {p.id: p for p in paragraph_results.scalars().all()}
    ordered_paragraphs = [
        {
            "index": paragraphs_by_id[pid].index,
            "title": paragraphs_by_id[pid].title,
            "synopsis": paragraphs_by_id[pid].synopsis,
        }
        for pid in req.selected_paragraph_ids
        if pid in paragraphs_by_id
    ]

    if len(ordered_paragraphs) != len(req.selected_paragraph_ids):
        raise ValueError("Some selected paragraphs could not be loaded")

    return LesplanContext(
        book_title=book.title,
        book_subject=subject_name,
        method_name=method.title if method else "",
        paragraphs=ordered_paragraphs,
        level=classroom.level.value,
        school_year=classroom.school_year.value,
        class_size=classroom.size,
        difficulty=classroom.difficulty.value if classroom.difficulty else None,
        attention_span_minutes=classroom.attention_span_minutes,
        support_challenge=classroom.support_challenge.value if classroom.support_challenge else None,
        class_notes=classroom.class_notes,
        num_lessons=req.num_lessons,
        lesson_duration_minutes=req.lesson_duration_minutes,
        classroom_assets=classroom_assets,
    )


async def _fetch_overview(session: AsyncSession, request_id: str) -> Optional[LesplanOverview]:
    result = await session.execute(select(LesplanOverview).where(LesplanOverview.request_id == request_id))
    return result.scalars().first()


async def _fetch_overview_response(
    session: AsyncSession,
    request_id: str,
) -> Optional[LesplanOverviewResponse]:
    overview = await _fetch_overview(session, request_id)
    if overview is None:
        return None

    lessons_result = await session.execute(
        select(LessonPlan)
        .where(LessonPlan.overview_id == overview.id)
        .order_by(LessonPlan.lesson_number.asc())  # type: ignore[union-attr]
    )
    lessons = lessons_result.scalars().all()
    request = await session.get(LesplanRequest, request_id)
    normalized_payload = _normalize_overview_payload(
        _raw_overview_payload_from_row(overview),
        num_lessons=request.num_lessons if request else None,
        paragraph_count=len(request.selected_paragraph_ids) if request else None,
    )

    lesson_responses = [await _lesson_response(session, lesson) for lesson in lessons]

    return LesplanOverviewResponse(
        id=overview.id,
        title=normalized_payload["title"],
        series_summary=normalized_payload["series_summary"],
        series_themes=normalized_payload["series_themes"],
        learning_goals=normalized_payload["learning_goals"],
        key_knowledge=normalized_payload["key_knowledge"],
        recommended_approach=normalized_payload["recommended_approach"],
        learning_progression=normalized_payload["learning_progression"],
        lesson_outline=[LessonOutlineItemResponse(**item) for item in normalized_payload["lesson_outline"]],
        goal_coverage=[GoalCoverageItemResponse(**item) for item in normalized_payload["goal_coverage"]],
        knowledge_coverage=[
            KnowledgeCoverageItemResponse(**item)
            for item in normalized_payload["knowledge_coverage"]
        ],
        didactic_approach=normalized_payload["didactic_approach"],
        lessons=lesson_responses,
    )


async def _build_response(session: AsyncSession, req: LesplanRequest) -> LesplanResponse:
    return LesplanResponse(
        id=req.id,
        user_id=req.user_id,
        class_id=req.class_id,
        book_id=req.book_id,
        selected_paragraph_ids=req.selected_paragraph_ids,
        num_lessons=req.num_lessons,
        lesson_duration_minutes=req.lesson_duration_minutes,
        status=req.status,
        created_at=req.created_at,
        updated_at=req.updated_at,
        overview=await _fetch_overview_response(session, req.id),
    )


async def _persist_overview(
    session: AsyncSession,
    request_id: str,
    data: dict[str, Any],
) -> LesplanOverview:
    request = await session.get(LesplanRequest, request_id)
    if request is None:
        raise NotFoundError("Lesplan not found")
    normalized = _normalize_overview_payload(
        data,
        num_lessons=request.num_lessons,
        paragraph_count=len(request.selected_paragraph_ids),
    )

    overview = await _fetch_overview(session, request_id)
    if overview is None:
        overview = LesplanOverview(
            request_id=request_id,
            title=normalized["title"],
            series_summary=normalized["series_summary"],
            series_themes=normalized["series_themes"],
            learning_goals=normalized["learning_goals"],
            key_knowledge=normalized["key_knowledge"],
            recommended_approach=normalized["recommended_approach"],
            learning_progression=normalized["learning_progression"],
            lesson_outline=normalized["lesson_outline"],
            goal_coverage=normalized["goal_coverage"],
            knowledge_coverage=normalized["knowledge_coverage"],
            didactic_approach=normalized["didactic_approach"],
        )
        session.add(overview)
    else:
        overview.title = normalized["title"]
        overview.series_summary = normalized["series_summary"]
        overview.series_themes = normalized["series_themes"]
        overview.learning_goals = normalized["learning_goals"]
        overview.key_knowledge = normalized["key_knowledge"]
        overview.recommended_approach = normalized["recommended_approach"]
        overview.learning_progression = normalized["learning_progression"]
        overview.lesson_outline = normalized["lesson_outline"]
        overview.goal_coverage = normalized["goal_coverage"]
        overview.knowledge_coverage = normalized["knowledge_coverage"]
        overview.didactic_approach = normalized["didactic_approach"]
    return overview


def _raw_overview_payload_from_row(overview: LesplanOverview) -> dict[str, Any]:
    return {
        "title": overview.title,
        "series_summary": overview.series_summary,
        "series_themes": overview.series_themes,
        "learning_goals": _normalize_learning_goals(overview.learning_goals),
        "key_knowledge": _normalize_key_knowledge(overview.key_knowledge),
        "recommended_approach": overview.recommended_approach,
        "learning_progression": overview.learning_progression,
        "lesson_outline": overview.lesson_outline,
        "goal_coverage": overview.goal_coverage,
        "knowledge_coverage": overview.knowledge_coverage,
        "didactic_approach": overview.didactic_approach,
    }


def _overview_payload_from_row(overview: LesplanOverview) -> dict[str, Any]:
    return _normalize_overview_payload(_raw_overview_payload_from_row(overview))


def _generated_overview_from_row(
    overview: LesplanOverview,
    *,
    num_lessons: int,
    paragraph_count: int,
) -> GeneratedLesplanOverview:
    normalized = _normalize_overview_payload(
        _raw_overview_payload_from_row(overview),
        num_lessons=num_lessons,
        paragraph_count=paragraph_count,
    )
    return GeneratedLesplanOverview(
        title=normalized["title"],
        series_summary=normalized["series_summary"],
        series_themes=normalized["series_themes"],
        learning_goals=normalized["learning_goals"],
        key_knowledge=normalized["key_knowledge"],
        recommended_approach=normalized["recommended_approach"],
        learning_progression=normalized["learning_progression"],
        lesson_outline=[LessonOutlineItem(**item) for item in normalized["lesson_outline"]],
        goal_coverage=[GoalCoverageItem(**item) for item in normalized["goal_coverage"]],
        knowledge_coverage=[KnowledgeCoverageItem(**item) for item in normalized["knowledge_coverage"]],
        didactic_approach=normalized["didactic_approach"],
    )


async def _generate_and_persist_overview(
    session: AsyncSession,
    req: LesplanRequest,
) -> None:
    """Generate the initial overview and persist it."""
    ctx = await _build_context(session, req)
    overview = await generate_overview(ctx)
    await _persist_overview(session, req.id, overview.model_dump(mode="json"))
    req.status = LesplanStatus.OVERVIEW_READY
    await session.commit()
    await session.refresh(req)
    logger.info("Overview generated for lesplan %s", req.id)


async def _submit_feedback(
    session: AsyncSession,
    req: LesplanRequest,
    feedback_items: list[FeedbackItem],
) -> None:
    """Apply structured feedback to the overview using the feedback agent."""
    overview = await _fetch_overview(session, req.id)
    if overview is None:
        raise NotFoundError("Overview not found")

    ctx = await _build_context(session, req)
    current_overview = _generated_overview_from_row(
        overview,
        num_lessons=req.num_lessons,
        paragraph_count=len(req.selected_paragraph_ids),
    )

    items_dicts = [
        {
            "field_name": item.field_name,
            "specific_part": item.specific_part,
            "user_feedback": item.user_feedback,
        }
        for item in feedback_items
    ]

    updated_fields = await apply_feedback(ctx, current_overview, items_dicts)

    # Merge updated fields into the existing overview payload
    current_payload = _raw_overview_payload_from_row(overview)
    current_payload.update(updated_fields)

    # Re-persist with normalization
    await _persist_overview(session, req.id, current_payload)
    req.status = LesplanStatus.OVERVIEW_READY
    await session.commit()
    await session.refresh(req)

    logger.info("Feedback applied for lesplan %s, updated fields: %s", req.id, list(updated_fields.keys()))


async def _run_lessons_generation(request_id: str) -> None:
    try:
        # Phase 1: fetch data (short-lived session)
        async with SessionLocal() as session:
            req = await session.get(LesplanRequest, request_id)
            if req is None:
                logger.error("LesplanRequest %s not found for lesson generation", request_id)
                return

            overview = await _fetch_overview(session, request_id)
            if overview is None:
                raise ValueError(f"No overview found for request {request_id}")

            ctx = await _build_context(session, req)
            approved_overview = _generated_overview_from_row(
                overview,
                num_lessons=req.num_lessons,
                paragraph_count=len(req.selected_paragraph_ids),
            )
            overview_id = overview.id
            selected_paragraph_ids = list(req.selected_paragraph_ids)

        # Phase 2: AI generation (no DB connection held)
        generated_lessons = await generate_lessons(ctx, approved_overview)

        # Phase 3: persist each lesson (short-lived sessions)
        total_todos = 0
        for lesson in generated_lessons:
            covered_ids = [
                selected_paragraph_ids[idx]
                for idx in lesson.covered_paragraph_indices
                if 0 <= idx < len(selected_paragraph_ids)
            ]

            # Generate preparation todos (no DB connection held)
            todos = []
            try:
                prep_ctx = PreparationContext(
                    lesson_number=lesson.lesson_number,
                    title=lesson.title,
                    learning_objectives=lesson.learning_objectives,
                    time_sections=[s.model_dump(mode="json") for s in lesson.time_sections],
                    required_materials=lesson.required_materials,
                    teacher_notes=lesson.teacher_notes,
                )
                todos = await generate_preparation_todos(prep_ctx)
                total_todos += len(todos)
                logger.info(
                    "Generated %d preparation todos for lesson %d (%s)",
                    len(todos),
                    lesson.lesson_number,
                    lesson.title,
                )
            except Exception:
                logger.error(
                    "Preparation todo generation failed for lesson %d:\n%s",
                    lesson.lesson_number,
                    traceback.format_exc(),
                )

            # Save lesson + todos (short-lived session)
            async with SessionLocal() as session:
                lesson_plan = LessonPlan(
                    overview_id=overview_id,
                    lesson_number=lesson.lesson_number,
                    title=lesson.title,
                    learning_objectives=lesson.learning_objectives,
                    time_sections=[section.model_dump(mode="json") for section in lesson.time_sections],
                    required_materials=lesson.required_materials,
                    covered_paragraph_ids=covered_ids,
                    teacher_notes=lesson.teacher_notes,
                )
                session.add(lesson_plan)
                await session.flush()

                for todo in todos:
                    session.add(
                        LessonPreparationTodo(
                            lesson_plan_id=lesson_plan.id,
                            title=todo.title,
                            description=todo.description,
                            why=todo.why,
                        )
                    )
                await session.commit()
                logger.info(
                    "Committed lesson %d/%d with todos for request %s",
                    lesson.lesson_number,
                    len(generated_lessons),
                    request_id,
                )

        async with SessionLocal() as session:
            req = await session.get(LesplanRequest, request_id)
            if req is not None:
                req.status = LesplanStatus.COMPLETED
                await session.commit()
        logger.info(
            "All lessons completed: %d todos total for request %s",
            total_todos,
            request_id,
        )
    except Exception:
        logger.error(
            "Lesson generation failed for request %s:\n%s",
            request_id,
            traceback.format_exc(),
        )
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is not None:
                    req.status = LesplanStatus.FAILED
                    await session.commit()
        except Exception:
            logger.error("Failed to mark lesplan %s as FAILED", request_id)
