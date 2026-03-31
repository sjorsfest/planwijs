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
    _build_revision_assistant_message,
    _build_sequence_prompt,
    _build_teacher_notes_prompt,
    _compose_overview_from_parts,
    _ensure_series_summary_includes_delivery,
    _learning_goal_feedback_lines,
    _normalize_approval_readiness,
    _normalize_learning_goals_for_context,
    _normalize_lesson_outline_for_context,
    _unique_non_empty,
    _validate_overview_for_context,
)


async def _generate_learning_goals(
    ctx: LesplanContext,
    identity: GeneratedOverviewIdentity,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> list[str]:
    draft_result = await get_overview_learning_goals_agent().run(
        _build_learning_goals_prompt(
            ctx,
            identity,
            current_overview=current_overview,
            history=history,
        )
    )
    draft_goals = _unique_non_empty(draft_result.output.learning_goals, limit=6)
    quality_feedback = _learning_goal_feedback_lines(draft_goals, ctx=ctx)
    if quality_feedback:
        refined_result = await get_overview_learning_goals_agent().run(
            _build_learning_goals_prompt(
                ctx,
                identity,
                current_overview=current_overview,
                history=history,
                draft_goals=draft_goals,
                quality_feedback=quality_feedback,
            )
        )
        refined_goals = _unique_non_empty(refined_result.output.learning_goals, limit=6)
        if len(_learning_goal_feedback_lines(refined_goals, ctx=ctx)) <= len(quality_feedback):
            draft_goals = refined_goals

    return _normalize_learning_goals_for_context(
        draft_goals,
        ctx=ctx,
    )


async def _stream_overview_pipeline(
    ctx: LesplanContext,
    *,
    current_overview: GeneratedLesplanOverview | None = None,
    history: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    identity_result = await get_overview_identity_agent().run(
        _build_identity_prompt(ctx, current_overview=current_overview, history=history)
    )
    identity = identity_result.output
    identity_partial = {
        "title": identity.title.strip(),
        "series_summary": identity.series_summary.strip(),
        "series_themes": _unique_non_empty(identity.series_themes, limit=6),
    }
    yield identity_partial, False

    learning_goals = await _generate_learning_goals(
        ctx,
        identity,
        current_overview=current_overview,
        history=history,
    )
    goals_partial = {"learning_goals": learning_goals}
    yield goals_partial, False

    sequence_result = await get_overview_sequence_agent().run(
        _build_sequence_prompt(
            ctx,
            identity,
            learning_goals,
            current_overview=current_overview,
            history=history,
        )
    )
    sequence = sequence_result.output
    sequence_knowledge = _unique_non_empty(sequence.key_knowledge, limit=10)
    sequence_outline = _normalize_lesson_outline_for_context(sequence.lesson_outline, ctx, sequence_knowledge)
    sequence_struct = GeneratedOverviewSequence(
        key_knowledge=sequence_knowledge,
        lesson_outline=sequence_outline,
    )
    sequence_partial = {
        "key_knowledge": sequence_knowledge,
        "lesson_outline": [item.model_dump(mode="json") for item in sequence_outline],
    }
    yield sequence_partial, False

    teacher_result = await get_overview_teacher_notes_agent().run(
        _build_teacher_notes_prompt(
            ctx,
            identity,
            sequence_struct,
            learning_goals,
            current_overview=current_overview,
            history=history,
        )
    )
    teacher_notes = teacher_result.output
    readiness_partial = _normalize_approval_readiness(
        teacher_notes.approval_readiness,
        has_goals=bool(learning_goals),
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
        sequence_struct,
        learning_goals,
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
    async for payload, is_final in _stream_overview_pipeline(ctx):
        yield payload, is_final


async def stream_revision(
    ctx: LesplanContext,
    overview: GeneratedLesplanOverview,
    history: list[dict[str, Any]],
) -> AsyncGenerator[tuple[dict[str, Any], bool], None]:
    final_overview_payload: dict[str, Any] | None = None
    async for payload, is_final in _stream_overview_pipeline(
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
    result = await get_lessons_agent().run(prompt)
    return result.output.lessons
