"""Shared utility functions for lesplan generation."""

from __future__ import annotations

import re
from typing import Any

from .types import (
    ApprovalReadiness,
    GeneratedLesplanOverview,
    GeneratedOverviewIdentity,
    GeneratedOverviewSequence,
    GeneratedOverviewTeacherNotes,
    GoalCoverageItem,
    KnowledgeCoverageItem,
    LesplanContext,
    LessonOutlineItem,
)

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
    attention_str = f"{ctx.attention_span_minutes} minuten" if ctx.attention_span_minutes else "niet opgegeven"
    support_str = ctx.support_challenge or "niet opgegeven"
    notes_line = f"Docentnotities over de klas: {ctx.class_notes}\n" if ctx.class_notes else ""
    return (
        f"Boek: {ctx.book_title} ({ctx.book_subject}) - Methode: {ctx.method_name}\n"
        f"Niveau: {ctx.level}, Leerjaar: {ctx.school_year}, "
        f"Klasgrootte: {ctx.class_size} leerlingen\n"
        f"Moeilijkheidsgraad klas: {difficulty_str}\n"
        f"Aandachtsspanne: {attention_str}\n"
        f"Ondersteuning/uitdaging: {support_str}\n"
        f"{notes_line}"
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


_LEARNING_GOAL_OBSERVABLE_VERBS = (
    "benoemen",
    "noemen",
    "identificeren",
    "herkennen",
    "koppelen",
    "matchen",
    "sorteren",
    "labelen",
    "beschrijven",
    "uitleggen",
    "samenvatten",
    "classificeren",
    "vergelijken",
    "ordenen",
    "beargumenteren",
    "onderbouwen",
    "berekenen",
    "oplossen",
    "toepassen",
    "kiezen",
    "invullen",
)
_LEARNING_GOAL_VAGUE_VERBS = (
    "begrijpen",
    "snappen",
    "weten",
    "kennen",
    "leren over",
    "vertrouwd raken met",
    "inzicht krijgen in",
    "verkennen",
    "exploreren",
)
_LEARNING_GOAL_VISIBLE_OUTPUT_MARKERS = (
    "zichtbaar in",
    "aangetoond door",
    "via",
    "door",
    "met",
    "in een",
    "uitleg",
    "toelichting",
    "tabel",
    "schema",
    "antwoord",
    "uitwerking",
    "vergelijking",
    "diagram",
    "kaart",
    "bron",
    "zinnen",
    "samenvatting",
)
_LEARNING_GOAL_HIGH_LEVEL_VERBS = (
    "evalueren",
    "beoordelen",
    "wegen",
    "kritisch",
)


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


def _is_introductory_level(ctx: LesplanContext) -> bool:
    level = (ctx.level or "").lower()
    year = (ctx.school_year or "").lower()
    return "vmbo" in level or year in {"leerjaar_1", "leerjaar_2"}


def _extract_goal_topic(goal: str) -> str:
    topic = _squash_text(goal)
    topic = re.sub(r"^leerlingen\s+(?:kunnen\s+)?", "", topic, flags=re.IGNORECASE)
    topic = re.sub(
        r"^(?:begrijpen|snappen|weten|kennen|leren over|vertrouwd raken met|inzicht krijgen in|verkennen)\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r",?\s*(zichtbaar in|aangetoond door).*$", "", topic, flags=re.IGNORECASE)
    return topic.strip(" .,:;")


def _goal_has_observable_verb(goal: str) -> bool:
    normalized = goal.lower()
    for verb in _LEARNING_GOAL_OBSERVABLE_VERBS:
        if re.search(rf"\b{re.escape(verb)}\w*\b", normalized):
            return True
    return False


def _goal_has_vague_verb(goal: str) -> bool:
    normalized = goal.lower()
    for verb in _LEARNING_GOAL_VAGUE_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", normalized):
            return True
    return False


def _goal_quality_issues(goal: str, *, ctx: LesplanContext) -> list[str]:
    normalized = _squash_text(goal).lower()
    issues: list[str] = []
    if not normalized:
        return ["Leeg leerdoel."]
    if _goal_has_vague_verb(goal):
        issues.append("Gebruik een observeerbaar werkwoord.")
    if not _goal_has_observable_verb(goal):
        issues.append("Noem expliciet wat leerlingen doen.")
    if not any(marker in normalized for marker in _LEARNING_GOAL_VISIBLE_OUTPUT_MARKERS):
        issues.append("Maak succes zichtbaar met een concrete output.")
    if normalized.count(" en ") >= 3:
        issues.append("Splits gecombineerde doelen op in één hoofdactie.")
    if len(normalized.split()) < 8:
        issues.append("Maak inhoud specifieker en afgebakend.")
    if _is_introductory_level(ctx):
        for verb in _LEARNING_GOAL_HIGH_LEVEL_VERBS:
            if re.search(rf"\b{re.escape(verb)}\w*\b", normalized):
                issues.append("Cognitief niveau lijkt te hoog voor deze doelgroep/fase.")
                break
    return issues


def _fallback_learning_goal_topic(
    index: int,
    *,
    ctx: LesplanContext,
    sequence: GeneratedOverviewSequence | None = None,
) -> str:
    paragraph_titles = [
        str(paragraph.get("title") or "").strip()
        for paragraph in ctx.paragraphs
        if str(paragraph.get("title") or "").strip()
    ]
    if paragraph_titles:
        return _short_topic(paragraph_titles[index % len(paragraph_titles)], max_words=12)

    if sequence is None:
        if ctx.book_subject:
            return ctx.book_subject
        return "de kern van de geselecteerde stof"

    if sequence.lesson_outline:
        lesson = sequence.lesson_outline[index % len(sequence.lesson_outline)]
        return _derive_lesson_topic(lesson, ctx, sequence.key_knowledge)
    if sequence.key_knowledge:
        return _short_topic(sequence.key_knowledge[index % len(sequence.key_knowledge)], max_words=12)
    if ctx.book_subject:
        return ctx.book_subject
    return "de kern van de geselecteerde stof"


def _rewrite_weak_learning_goal(
    goal: str,
    *,
    index: int,
    ctx: LesplanContext,
    sequence: GeneratedOverviewSequence | None = None,
) -> str:
    topic = _extract_goal_topic(goal)
    if len(topic.split()) < 3:
        topic = _fallback_learning_goal_topic(index, ctx=ctx, sequence=sequence)
    topic = (
        topic[:1].lower() + topic[1:]
        if topic
        else _fallback_learning_goal_topic(index, ctx=ctx, sequence=sequence)
    )
    if _is_introductory_level(ctx):
        return (
            f"Leerlingen kunnen kernbegrippen over {topic} benoemen en koppelen aan de juiste uitleg, "
            "zichtbaar in een korte sorteer- of koppelopdracht."
        )
    return (
        f"Leerlingen kunnen {topic} uitleggen met passende vakbegrippen, "
        "zichtbaar in een korte schriftelijke of mondelinge toelichting."
    )


def _normalize_learning_goals_for_context(
    goals: list[str],
    *,
    ctx: LesplanContext,
    sequence: GeneratedOverviewSequence | None = None,
) -> list[str]:
    cleaned = _unique_non_empty(goals, limit=6)
    if not cleaned:
        return [
            _rewrite_weak_learning_goal(
                "",
                index=0,
                ctx=ctx,
                sequence=sequence,
            )
        ]

    normalized: list[str] = []
    for index, goal in enumerate(cleaned):
        compact_goal = _squash_text(goal)
        if not compact_goal:
            continue
        issues = _goal_quality_issues(compact_goal, ctx=ctx)
        if issues:
            normalized.append(
                _rewrite_weak_learning_goal(
                    compact_goal,
                    index=index,
                    ctx=ctx,
                    sequence=sequence,
                )
            )
            continue
        normalized.append(compact_goal)

    normalized = _unique_non_empty(normalized, limit=6)
    if normalized:
        return normalized

    return [
        _rewrite_weak_learning_goal(
            "",
            index=0,
            ctx=ctx,
            sequence=sequence,
        )
    ]


def _learning_goal_feedback_lines(goals: list[str], *, ctx: LesplanContext) -> list[str]:
    feedback: list[str] = []
    for index, goal in enumerate(goals, start=1):
        issues = _goal_quality_issues(goal, ctx=ctx)
        if not issues:
            continue
        issue_text = "; ".join(issues[:3])
        feedback.append(f"Doel {index} ({goal}): {issue_text}")
    return feedback


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

    profile_hints = []
    if ctx.attention_span_minutes:
        profile_hints.append(f"max {ctx.attention_span_minutes} min instructie per blok")
    if ctx.support_challenge == "Meer ondersteuning":
        profile_hints.append("meer scaffolding en begeleiding")
    elif ctx.support_challenge == "Meer uitdaging":
        profile_hints.append("meer complexiteit en zelfstandigheid")
    extra = f", {', '.join(profile_hints)}" if profile_hints else ""

    return (
        "Didactische hoofdroute: start elke les met een korte activering, geef daarna gerichte instructie, "
        f"laat leerlingen begeleid verwerken en sluit af met een check op begrip, bij {subject}, afgestemd op "
        f"{level} {year} ({ctx.class_size} leerlingen{difficulty_hint}{extra})."
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
    # Strip any pre-existing "Onderwerp:" prefixes to prevent duplication
    plain_base = re.sub(r"^(Onderwerp:\s*)+", "", plain_base, flags=re.IGNORECASE).strip()
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
    if ctx.attention_span_minutes:
        profile_bits.append(f"aandachtsspanne: {ctx.attention_span_minutes} min")
    if ctx.support_challenge:
        profile_bits.append(f"ondersteuning/uitdaging: {ctx.support_challenge}")
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
    learning_goals: list[str],
    teacher_notes: GeneratedOverviewTeacherNotes,
) -> GeneratedLesplanOverview:
    subject_label = (ctx.book_subject or "dit onderwerp").strip()
    learning_goals = _normalize_learning_goals_for_context(
        learning_goals,
        ctx=ctx,
        sequence=sequence,
    )
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
    learning_goals: list[str],
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
    goals_block = "\n".join(f"- {goal}" for goal in learning_goals)
    return (
        f"{background}\n\n{identity_block}\n\n## Learning goals\n{goals_block}\n\n"
        "Schrijf alleen key_knowledge en lesson_outline voor deze reviewfase. "
        "Gebruik de learning_goals als leidraad voor de inhoudelijke opbouw van de reeks. "
        "Zorg dat elke les een korte teaching_approach_hint bevat (hoe de docent deze stof aanbiedt), "
        "met zichtbare variatie in werkvorm tussen lessen."
    )


def _build_learning_goals_prompt(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
    draft_goals: list[str] | None = None,
    quality_feedback: list[str] | None = None,
) -> str:
    background = _build_overview_background(ctx, current_overview=current_overview, history=history)
    context_block = (
        "## Reekscontext voor leerdoelen\n"
        f"Titel: {identity.title}\n"
        f"Thema's: {', '.join(identity.series_themes)}"
    )
    rewrite_block = ""
    if draft_goals:
        draft_lines = "\n".join(f"- {goal}" for goal in draft_goals)
        rewrite_block = f"\n\n## Huidige leerdoelen\n{draft_lines}"
    feedback_block = ""
    if quality_feedback:
        feedback_lines = "\n".join(f"- {line}" for line in quality_feedback)
        feedback_block = (
            "\n\n## Kwaliteitsfeedback die je moet verwerken\n"
            f"{feedback_lines}\n"
            "Herschrijf ALLE leerdoelen zodat ze aan alle punten voldoen."
        )

    return (
        f"{background}\n\n{context_block}{rewrite_block}{feedback_block}\n\n"
        "Schrijf alleen learning_goals. Formuleer ze direct toetsbaar voor in de les."
    )


def _build_teacher_notes_prompt(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
    sequence: GeneratedOverviewSequence,
    learning_goals: list[str],
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
        f"Leerdoelen: {len(learning_goals)}\n"
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


