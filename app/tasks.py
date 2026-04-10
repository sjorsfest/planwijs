"""ARQ task functions for background lesplan generation."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from redis.asyncio import Redis

from app.agents.lesplan.feedback_agent import apply_feedback
from app.agents.lesplan.overview_identity_agent import get_overview_identity_agent
from app.agents.lesplan.overview_learning_goals_agent import get_overview_learning_goals_agent
from app.agents.lesplan.overview_sequence_agent import get_overview_sequence_agent
from app.agents.lesplan.overview_teacher_notes_agent import get_overview_teacher_notes_agent
from app.agents.lesplan.pipeline import _generate_learning_goals, generate_lessons
from app.agents.lesplan.types import (
    GeneratedOverviewIdentity,
    GeneratedOverviewSequence,
    GeneratedOverviewTeacherNotes,
)
from app.agents.lesplan.utils import (
    _build_identity_prompt,
    _build_sequence_prompt,
    _build_teacher_notes_prompt,
    _compose_overview_from_parts,
    _ensure_series_summary_includes_delivery,
    _normalize_lesson_outline_for_context,
    _unique_non_empty,
    _validate_overview_for_context,
)
from app.agents.preparation_agent import PreparationContext, generate_preparation_todos
from app.config import settings
from app.database import SessionLocal
from app.models.enums import LesplanStatus
from app.models.lesplan import LesplanRequest, LessonPlan, LessonPreparationTodo
from app.redis import get_redis_pool
from app.task_state import TaskStatus, TaskStep, TaskState, set_task_state, update_task_progress

logger = logging.getLogger(__name__)

OVERVIEW_STEPS = [
    "Loading context",
    "Generating identity",
    "Generating learning goals",
    "Generating sequence",
    "Generating teacher notes",
    "Persisting overview",
]

FEEDBACK_STEPS = [
    "Loading context",
    "Applying feedback",
    "Persisting changes",
]

LESSONS_STEPS = [
    "Loading context",
    "Generating lessons",
    "Generating preparation",
    "Persisting lessons",
]


async def _get_redis() -> Redis:  # type: ignore[type-arg]
    return await get_redis_pool()


async def generate_overview_task(ctx: dict[str, Any], task_id: str, request_id: str) -> None:
    redis = await _get_redis()
    ttl = settings.redis_task_ttl_seconds

    try:
        # --- Step 1: Load context ---
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.RUNNING,
            current_step="Loading context",
            progress_pct=0,
            step_name="Loading context",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        # Import here to avoid circular imports at module level
        from app.routes.lesplan.util import (
            _build_context,
            _fetch_overview,
            _persist_overview,
        )

        async with SessionLocal() as session:
            req = await session.get(LesplanRequest, request_id)
            if req is None:
                raise ValueError(f"LesplanRequest {request_id} not found")
            lesplan_ctx = await _build_context(session, req)

        await update_task_progress(
            redis, task_id,
            step_name="Loading context",
            step_status=TaskStatus.COMPLETED,
            progress_pct=5,
            ttl=ttl,
        )

        # --- Step 2: Identity agent ---
        await update_task_progress(
            redis, task_id,
            current_step="Generating identity",
            progress_pct=10,
            step_name="Generating identity",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        # Rolling payload accumulates partial overview data for intermediate persistence
        rolling_payload: dict[str, Any] = {}

        identity_result = await get_overview_identity_agent().run(
            _build_identity_prompt(lesplan_ctx)
        )
        identity = identity_result.output
        identity_data = GeneratedOverviewIdentity(
            title=identity.title.strip(),
            series_summary=identity.series_summary.strip(),
            series_themes=_unique_non_empty(identity.series_themes, limit=6),
        )

        # Persist partial: identity fields
        rolling_payload.update({
            "title": identity_data.title,
            "series_summary": identity_data.series_summary,
            "series_themes": identity_data.series_themes,
        })
        async with SessionLocal() as session:
            await _persist_overview(session, request_id, rolling_payload)
            await session.commit()

        await update_task_progress(
            redis, task_id,
            step_name="Generating identity",
            step_status=TaskStatus.COMPLETED,
            progress_pct=25,
            ttl=ttl,
        )

        # --- Step 3: Learning goals agent ---
        await update_task_progress(
            redis, task_id,
            current_step="Generating learning goals",
            progress_pct=30,
            step_name="Generating learning goals",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        learning_goals = await _generate_learning_goals(lesplan_ctx, identity_data)

        # Persist partial: learning goals
        rolling_payload["learning_goals"] = learning_goals
        async with SessionLocal() as session:
            await _persist_overview(session, request_id, rolling_payload)
            await session.commit()

        await update_task_progress(
            redis, task_id,
            step_name="Generating learning goals",
            step_status=TaskStatus.COMPLETED,
            progress_pct=45,
            ttl=ttl,
        )

        # --- Step 4: Sequence agent ---
        await update_task_progress(
            redis, task_id,
            current_step="Generating sequence",
            progress_pct=55,
            step_name="Generating sequence",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        sequence_result = await get_overview_sequence_agent().run(
            _build_sequence_prompt(lesplan_ctx, identity_data, learning_goals)
        )
        sequence = sequence_result.output
        sequence_knowledge = _unique_non_empty(sequence.key_knowledge, limit=10)
        sequence_outline = _normalize_lesson_outline_for_context(
            sequence.lesson_outline, lesplan_ctx, sequence_knowledge
        )
        sequence_struct = GeneratedOverviewSequence(
            key_knowledge=sequence_knowledge,
            lesson_outline=sequence_outline,
        )

        # Persist partial: sequence fields
        rolling_payload.update({
            "key_knowledge": sequence_knowledge,
            "lesson_outline": [item.model_dump(mode="json") for item in sequence_outline],
        })
        async with SessionLocal() as session:
            await _persist_overview(session, request_id, rolling_payload)
            await session.commit()

        await update_task_progress(
            redis, task_id,
            step_name="Generating sequence",
            step_status=TaskStatus.COMPLETED,
            progress_pct=70,
            ttl=ttl,
        )

        # --- Step 5: Teacher notes agent ---
        await update_task_progress(
            redis, task_id,
            current_step="Generating teacher notes",
            progress_pct=80,
            step_name="Generating teacher notes",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        teacher_result = await get_overview_teacher_notes_agent().run(
            _build_teacher_notes_prompt(lesplan_ctx, identity_data, sequence_struct, learning_goals)
        )
        teacher_notes = teacher_result.output

        series_summary = _ensure_series_summary_includes_delivery(
            series_summary=identity_data.series_summary,
            learning_progression=teacher_notes.learning_progression.strip(),
            recommended_approach=teacher_notes.recommended_approach.strip(),
            didactic_approach=teacher_notes.didactic_approach.strip(),
            ctx=lesplan_ctx,
        )
        identity_data = GeneratedOverviewIdentity(
            title=identity_data.title,
            series_summary=series_summary,
            series_themes=identity_data.series_themes,
        )

        overview = _compose_overview_from_parts(
            lesplan_ctx,
            identity_data,
            sequence_struct,
            learning_goals,
            GeneratedOverviewTeacherNotes(
                recommended_approach=teacher_notes.recommended_approach.strip(),
                learning_progression=teacher_notes.learning_progression.strip(),
                didactic_approach=teacher_notes.didactic_approach.strip(),
            ),
        )
        _validate_overview_for_context(overview, lesplan_ctx)

        await update_task_progress(
            redis, task_id,
            step_name="Generating teacher notes",
            step_status=TaskStatus.COMPLETED,
            progress_pct=90,
            ttl=ttl,
        )

        # --- Step 6: Persist final overview ---
        await update_task_progress(
            redis, task_id,
            current_step="Persisting overview",
            progress_pct=95,
            step_name="Persisting overview",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        async with SessionLocal() as session:
            await _persist_overview(session, request_id, overview.model_dump(mode="json"))
            req = await session.get(LesplanRequest, request_id)
            if req is not None:
                req.status = LesplanStatus.OVERVIEW_READY
            await session.commit()

        await update_task_progress(
            redis, task_id,
            status=TaskStatus.COMPLETED,
            current_step="Complete",
            progress_pct=100,
            step_name="Persisting overview",
            step_status=TaskStatus.COMPLETED,
            ttl=ttl,
        )
        logger.info("Overview generation completed for lesplan %s", request_id)

    except Exception:
        logger.error(
            "Overview generation failed for %s:\n%s", request_id, traceback.format_exc()
        )
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.FAILED,
            error="Overview generation failed",
            ttl=ttl,
        )
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is not None:
                    req.status = LesplanStatus.FAILED
                    await session.commit()
        except Exception:
            logger.error("Failed to mark lesplan %s as FAILED", request_id)


async def apply_feedback_task(
    ctx: dict[str, Any],
    task_id: str,
    request_id: str,
    feedback_items: list[dict[str, str]],
) -> None:
    redis = await _get_redis()
    ttl = settings.redis_task_ttl_seconds

    try:
        # --- Step 1: Load context ---
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.RUNNING,
            current_step="Loading context",
            progress_pct=0,
            step_name="Loading context",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        from app.routes.lesplan.util import (
            _build_context,
            _fetch_overview,
            _generated_overview_from_row,
            _persist_overview,
            _raw_overview_payload_from_row,
        )

        async with SessionLocal() as session:
            req = await session.get(LesplanRequest, request_id)
            if req is None:
                raise ValueError(f"LesplanRequest {request_id} not found")

            overview_row = await _fetch_overview(session, request_id)
            if overview_row is None:
                raise ValueError(f"No overview found for request {request_id}")

            lesplan_ctx = await _build_context(session, req)
            current_overview = _generated_overview_from_row(
                overview_row,
                num_lessons=req.num_lessons,
                paragraph_count=len(req.selected_paragraph_ids),
            )
            raw_payload = _raw_overview_payload_from_row(overview_row)

        await update_task_progress(
            redis, task_id,
            step_name="Loading context",
            step_status=TaskStatus.COMPLETED,
            progress_pct=10,
            ttl=ttl,
        )

        # --- Step 2: Run feedback agent ---
        await update_task_progress(
            redis, task_id,
            current_step="Applying feedback",
            progress_pct=20,
            step_name="Applying feedback",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        updated_fields = await apply_feedback(lesplan_ctx, current_overview, feedback_items)

        await update_task_progress(
            redis, task_id,
            step_name="Applying feedback",
            step_status=TaskStatus.COMPLETED,
            progress_pct=75,
            ttl=ttl,
        )

        # --- Step 3: Persist changes ---
        await update_task_progress(
            redis, task_id,
            current_step="Persisting changes",
            progress_pct=80,
            step_name="Persisting changes",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        raw_payload.update(updated_fields)

        async with SessionLocal() as session:
            await _persist_overview(session, request_id, raw_payload)
            req = await session.get(LesplanRequest, request_id)
            if req is not None:
                req.status = LesplanStatus.OVERVIEW_READY
            await session.commit()

        await update_task_progress(
            redis, task_id,
            status=TaskStatus.COMPLETED,
            current_step="Complete",
            progress_pct=100,
            step_name="Persisting changes",
            step_status=TaskStatus.COMPLETED,
            ttl=ttl,
        )
        logger.info("Feedback applied for lesplan %s, updated: %s", request_id, list(updated_fields.keys()))

    except Exception:
        logger.error(
            "Feedback task failed for %s:\n%s", request_id, traceback.format_exc()
        )
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.FAILED,
            error="Feedback processing failed",
            ttl=ttl,
        )
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is not None:
                    req.status = LesplanStatus.OVERVIEW_READY
                    await session.commit()
        except Exception:
            logger.error("Failed to reset lesplan %s status after feedback failure", request_id)


async def generate_lessons_task(ctx: dict[str, Any], task_id: str, request_id: str) -> None:
    redis = await _get_redis()
    ttl = settings.redis_task_ttl_seconds

    try:
        # --- Step 1: Load context ---
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.RUNNING,
            current_step="Loading context",
            progress_pct=0,
            step_name="Loading context",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        from app.routes.lesplan.util import (
            _build_context,
            _fetch_overview,
            _generated_overview_from_row,
        )

        async with SessionLocal() as session:
            req = await session.get(LesplanRequest, request_id)
            if req is None:
                raise ValueError(f"LesplanRequest {request_id} not found")

            overview_row = await _fetch_overview(session, request_id)
            if overview_row is None:
                raise ValueError(f"No overview found for request {request_id}")

            lesplan_ctx = await _build_context(session, req)
            approved_overview = _generated_overview_from_row(
                overview_row,
                num_lessons=req.num_lessons,
                paragraph_count=len(req.selected_paragraph_ids),
            )
            overview_id = overview_row.id
            selected_paragraph_ids = list(req.selected_paragraph_ids)

        await update_task_progress(
            redis, task_id,
            step_name="Loading context",
            step_status=TaskStatus.COMPLETED,
            progress_pct=5,
            ttl=ttl,
        )

        # --- Step 2: Generate lessons ---
        await update_task_progress(
            redis, task_id,
            current_step="Generating lessons",
            progress_pct=10,
            step_name="Generating lessons",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        generated_lessons = await generate_lessons(lesplan_ctx, approved_overview)

        await update_task_progress(
            redis, task_id,
            step_name="Generating lessons",
            step_status=TaskStatus.COMPLETED,
            progress_pct=40,
            ttl=ttl,
        )

        # --- Step 3: Generate preparation todos + persist each lesson ---
        await update_task_progress(
            redis, task_id,
            current_step="Generating preparation",
            progress_pct=40,
            step_name="Generating preparation",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        total_lessons = len(generated_lessons)
        for i, lesson in enumerate(generated_lessons):
            progress = 40 + int((i / max(total_lessons, 1)) * 50)
            await update_task_progress(
                redis, task_id,
                current_step=f"Preparing lesson {lesson.lesson_number}/{total_lessons}",
                progress_pct=progress,
                ttl=ttl,
            )

            covered_ids = [
                selected_paragraph_ids[idx]
                for idx in lesson.covered_paragraph_indices
                if 0 <= idx < len(selected_paragraph_ids)
            ]

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
            except Exception:
                logger.error(
                    "Preparation todo generation failed for lesson %d:\n%s",
                    lesson.lesson_number,
                    traceback.format_exc(),
                )

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

        await update_task_progress(
            redis, task_id,
            step_name="Generating preparation",
            step_status=TaskStatus.COMPLETED,
            progress_pct=95,
            ttl=ttl,
        )

        # --- Step 4: Mark complete ---
        async with SessionLocal() as session:
            req = await session.get(LesplanRequest, request_id)
            if req is not None:
                req.status = LesplanStatus.COMPLETED
                await session.commit()

        await update_task_progress(
            redis, task_id,
            status=TaskStatus.COMPLETED,
            current_step="Complete",
            progress_pct=100,
            step_name="Persisting lessons",
            step_status=TaskStatus.COMPLETED,
            ttl=ttl,
        )
        logger.info("Lesson generation completed for lesplan %s", request_id)

    except Exception:
        logger.error(
            "Lesson generation failed for %s:\n%s", request_id, traceback.format_exc()
        )
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.FAILED,
            error="Lesson generation failed",
            ttl=ttl,
        )
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is not None:
                    req.status = LesplanStatus.FAILED
                    await session.commit()
        except Exception:
            logger.error("Failed to mark lesplan %s as FAILED", request_id)
