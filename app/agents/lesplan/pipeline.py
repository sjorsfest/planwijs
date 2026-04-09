from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from .lessons_agent import get_lessons_agent
from .overview_identity_agent import get_overview_identity_agent
from .overview_learning_goals_agent import get_overview_learning_goals_agent
from .overview_sequence_agent import get_overview_sequence_agent
from .overview_teacher_notes_agent import get_overview_teacher_notes_agent
from .types import (
    GeneratedLessonPlan,
    GeneratedLesplanOverview,
    GeneratedOverviewIdentity,
    GeneratedOverviewSequence,
    GeneratedOverviewTeacherNotes,
    LesplanContext,
)
from .utils import (
    _build_identity_prompt,
    _build_learning_goals_prompt,
    _build_lessons_prompt,
    _build_sequence_prompt,
    _build_teacher_notes_prompt,
    _compose_overview_from_parts,
    _ensure_series_summary_includes_delivery,
    _learning_goal_feedback_lines,
    _normalize_learning_goals_for_context,
    _normalize_lesson_outline_for_context,
    _unique_non_empty,
    _validate_overview_for_context,
)


async def _generate_learning_goals(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
) -> list[str]:
    draft_result = await get_overview_learning_goals_agent().run(
        _build_learning_goals_prompt(ctx, identity)
    )
    draft_goals = _unique_non_empty(draft_result.output.learning_goals, limit=6)
    quality_feedback = _learning_goal_feedback_lines(draft_goals, ctx=ctx)
    if quality_feedback:
        refined_result = await get_overview_learning_goals_agent().run(
            _build_learning_goals_prompt(
                ctx,
                identity,
                draft_goals=draft_goals,
                quality_feedback=quality_feedback,
            )
        )
        refined_goals = _unique_non_empty(refined_result.output.learning_goals, limit=6)
        if len(_learning_goal_feedback_lines(refined_goals, ctx=ctx)) <= len(quality_feedback):
            draft_goals = refined_goals

    return _normalize_learning_goals_for_context(draft_goals, ctx=ctx)


async def stream_overview(ctx: LesplanContext) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    """Stream the overview pipeline, yielding partial results after each step."""
    identity_result = await get_overview_identity_agent().run(
        _build_identity_prompt(ctx)
    )
    identity = identity_result.output
    identity_partial = {
        "title": identity.title.strip(),
        "series_summary": identity.series_summary.strip(),
        "series_themes": _unique_non_empty(identity.series_themes, limit=6),
    }
    yield identity_partial, False

    identity_data = GeneratedOverviewIdentity(**identity_partial)

    learning_goals = await _generate_learning_goals(ctx, identity_data)
    yield {"learning_goals": learning_goals}, False

    sequence_result = await get_overview_sequence_agent().run(
        _build_sequence_prompt(ctx, identity_data, learning_goals)
    )
    sequence = sequence_result.output
    sequence_knowledge = _unique_non_empty(sequence.key_knowledge, limit=10)
    sequence_outline = _normalize_lesson_outline_for_context(sequence.lesson_outline, ctx, sequence_knowledge)
    sequence_struct = GeneratedOverviewSequence(
        key_knowledge=sequence_knowledge,
        lesson_outline=sequence_outline,
    )
    yield {
        "key_knowledge": sequence_knowledge,
        "lesson_outline": [item.model_dump(mode="json") for item in sequence_outline],
    }, False

    teacher_result = await get_overview_teacher_notes_agent().run(
        _build_teacher_notes_prompt(ctx, identity_data, sequence_struct, learning_goals)
    )
    teacher_notes = teacher_result.output
    teacher_partial = {
        "recommended_approach": teacher_notes.recommended_approach.strip(),
        "learning_progression": teacher_notes.learning_progression.strip(),
        "didactic_approach": teacher_notes.didactic_approach.strip(),
    }
    series_summary = _ensure_series_summary_includes_delivery(
        series_summary=identity_partial["series_summary"],
        learning_progression=teacher_partial["learning_progression"],
        recommended_approach=teacher_partial["recommended_approach"],
        didactic_approach=teacher_partial["didactic_approach"],
        ctx=ctx,
    )
    teacher_partial["series_summary"] = series_summary
    yield teacher_partial, False

    identity_data = GeneratedOverviewIdentity(
        title=identity_partial["title"],
        series_summary=series_summary,
        series_themes=identity_partial["series_themes"],
    )
    composed = _compose_overview_from_parts(
        ctx,
        identity_data,
        sequence_struct,
        learning_goals,
        GeneratedOverviewTeacherNotes(
            recommended_approach=teacher_partial["recommended_approach"],
            learning_progression=teacher_partial["learning_progression"],
            didactic_approach=teacher_partial["didactic_approach"],
        ),
    )
    _validate_overview_for_context(composed, ctx)
    yield composed.model_dump(mode="json"), True


async def generate_overview(ctx: LesplanContext) -> GeneratedLesplanOverview:
    """Generate a full overview by running the 4-step pipeline (non-streaming)."""
    identity_result = await get_overview_identity_agent().run(
        _build_identity_prompt(ctx)
    )
    identity = identity_result.output
    identity_data = GeneratedOverviewIdentity(
        title=identity.title.strip(),
        series_summary=identity.series_summary.strip(),
        series_themes=_unique_non_empty(identity.series_themes, limit=6),
    )

    learning_goals = await _generate_learning_goals(ctx, identity_data)

    sequence_result = await get_overview_sequence_agent().run(
        _build_sequence_prompt(ctx, identity_data, learning_goals)
    )
    sequence = sequence_result.output
    sequence_knowledge = _unique_non_empty(sequence.key_knowledge, limit=10)
    sequence_outline = _normalize_lesson_outline_for_context(sequence.lesson_outline, ctx, sequence_knowledge)
    sequence_struct = GeneratedOverviewSequence(
        key_knowledge=sequence_knowledge,
        lesson_outline=sequence_outline,
    )

    teacher_result = await get_overview_teacher_notes_agent().run(
        _build_teacher_notes_prompt(ctx, identity_data, sequence_struct, learning_goals)
    )
    teacher_notes = teacher_result.output

    series_summary = _ensure_series_summary_includes_delivery(
        series_summary=identity_data.series_summary,
        learning_progression=teacher_notes.learning_progression.strip(),
        recommended_approach=teacher_notes.recommended_approach.strip(),
        didactic_approach=teacher_notes.didactic_approach.strip(),
        ctx=ctx,
    )
    identity_data = GeneratedOverviewIdentity(
        title=identity_data.title,
        series_summary=series_summary,
        series_themes=identity_data.series_themes,
    )

    overview = _compose_overview_from_parts(
        ctx,
        identity_data,
        sequence_struct,
        learning_goals,
        GeneratedOverviewTeacherNotes(
            recommended_approach=teacher_notes.recommended_approach.strip(),
            learning_progression=teacher_notes.learning_progression.strip(),
            didactic_approach=teacher_notes.didactic_approach.strip(),
        ),
    )
    _validate_overview_for_context(overview, ctx)
    return overview


async def generate_lessons(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
) -> list[GeneratedLessonPlan]:
    _validate_overview_for_context(overview, ctx)
    prompt = _build_lessons_prompt(ctx, overview)
    result = await get_lessons_agent().run(prompt)
    return result.output.lessons
