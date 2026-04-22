"""ARQ task functions for background lesplan generation."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from redis.asyncio import Redis

from app.agents.lesplan.feedback_agent import apply_feedback
from app.agents.lesplan.lesson_feedback_agent import apply_lesson_feedback
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
    _normalize_lesson_outline_for_context,
    _unique_non_empty,
    _validate_overview_for_context,
)
from app.agents.preparation_agent import PreparationContext, generate_preparation_todos
from app.config import settings
from app.database import SessionLocal
from app.models.enums import FeedbackTargetType, LesplanStatus
from app.models.feedback import Feedback
from app.models.learning_goal import LearningGoal
from app.models.lesson_objective import LessonObjective
from app.models.lesson_objective_goal import LessonObjectiveGoal
from app.models.lesplan import LesplanRequest, LessonPlan, LessonPreparationTodo
from app.redis import get_redis_pool
from sqlmodel import select
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


async def _get_redis() -> Redis:
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
            logger.error("Failed to mark lesplan %s as FAILED after lesson generation", request_id)


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

            user_id = req.user_id
            organization_id = req.organization_id

            overview_row = await _fetch_overview(session, request_id)
            if overview_row is None:
                raise ValueError(f"No overview found for request {request_id}")

            overview_id = overview_row.id
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
        logger.info(
            "Feedback agent returned %d updated field(s) for lesplan %s: %s",
            len(updated_fields), request_id, list(updated_fields.keys()),
        )

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

            for item in feedback_items:
                original_value = raw_payload.get(item["field_name"])
                feedback_record = Feedback(
                    user_id=user_id,
                    target_type=FeedbackTargetType.LESPLAN_OVERVIEW,
                    target_id=overview_id,
                    field_name=item["field_name"],
                    original_text=str(original_value) if original_value is not None else None,
                    feedback_text=item["user_feedback"],
                    organization_id=organization_id,
                )
                session.add(feedback_record)
            logger.info(
                "Saving %d feedback record(s) for overview %s by user %s",
                len(feedback_items), overview_id, user_id,
            )

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

        # Load LearningGoal records for linking objectives to goals
        async with SessionLocal() as session:
            goal_results = await session.execute(
                select(LearningGoal)
                .where(LearningGoal.overview_id == overview_id)
                .order_by(LearningGoal.position.asc())  # type: ignore[union-attr]
            )
            goal_records = list(goal_results.scalars().all())

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

            objective_texts = lesson.learning_objectives

            todos = []
            try:
                prep_ctx = PreparationContext(
                    lesson_number=lesson.lesson_number,
                    title=lesson.title,
                    learning_objectives=objective_texts,
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
                    learning_objectives=objective_texts,
                    time_sections=[section.model_dump(mode="json") for section in lesson.time_sections],
                    required_materials=lesson.required_materials,
                    covered_paragraph_ids=covered_ids,
                    teacher_notes=lesson.teacher_notes,
                )
                session.add(lesson_plan)
                await session.flush()

                # Create LessonObjective records with goal links
                goal_mapping = lesson.objective_goal_indices or []
                for pos, obj_text in enumerate(lesson.learning_objectives):
                    lo = LessonObjective(
                        lesson_plan_id=lesson_plan.id,
                        text=obj_text,
                        position=pos,
                    )
                    session.add(lo)
                    await session.flush()

                    indices = goal_mapping[pos] if pos < len(goal_mapping) else []
                    for goal_idx in indices:
                        if 0 <= goal_idx < len(goal_records):
                            session.add(LessonObjectiveGoal(
                                lesson_objective_id=lo.id,
                                learning_goal_id=goal_records[goal_idx].id,
                            ))

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


# ---------------------------------------------------------------------------
# Fields that trigger todo reconciliation when changed via lesson feedback
# ---------------------------------------------------------------------------
_TODO_TRIGGER_FIELDS = {"time_sections", "required_materials", "learning_objectives"}


async def apply_lesson_feedback_task(
    ctx: dict[str, Any],
    task_id: str,
    lesson_id: str,
    feedback_items: list[dict[str, str]],
    request_id: str,
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

        async with SessionLocal() as session:
            lesson = await session.get(LessonPlan, lesson_id)
            if lesson is None:
                raise ValueError(f"LessonPlan {lesson_id} not found")

            req = await session.get(LesplanRequest, request_id)
            if req is None:
                raise ValueError(f"LesplanRequest {request_id} not found")

            user_id = req.user_id
            organization_id = req.organization_id

            lesson_data: dict[str, Any] = {
                "title": lesson.title,
                "learning_objectives": lesson.learning_objectives,
                "time_sections": lesson.time_sections,
                "required_materials": lesson.required_materials,
                "teacher_notes": lesson.teacher_notes,
            }
            lesson_number = lesson.lesson_number

        await update_task_progress(
            redis, task_id,
            step_name="Loading context",
            step_status=TaskStatus.COMPLETED,
            progress_pct=10,
            ttl=ttl,
        )

        # --- Step 2: Run lesson feedback agent ---
        await update_task_progress(
            redis, task_id,
            current_step="Applying feedback",
            progress_pct=20,
            step_name="Applying feedback",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        updated_fields = await apply_lesson_feedback(lesson_data, feedback_items)
        logger.info(
            "Lesson feedback agent returned %d updated field(s) for lesson %s: %s",
            len(updated_fields), lesson_id, list(updated_fields.keys()),
        )

        await update_task_progress(
            redis, task_id,
            step_name="Applying feedback",
            step_status=TaskStatus.COMPLETED,
            progress_pct=50,
            ttl=ttl,
        )

        # --- Step 3: Reconcile preparation todos ---
        await update_task_progress(
            redis, task_id,
            current_step="Reconciling preparation",
            progress_pct=55,
            step_name="Reconciling preparation",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        new_todos: list[Any] = []
        needs_todo_reconciliation = bool(_TODO_TRIGGER_FIELDS & set(updated_fields.keys()))

        if needs_todo_reconciliation:
            merged = {**lesson_data, **updated_fields}
            time_sections_dicts = [
                s if isinstance(s, dict) else s
                for s in merged.get("time_sections", [])
            ]
            prep_ctx = PreparationContext(
                lesson_number=lesson_number,
                title=merged.get("title", lesson_data["title"]),
                learning_objectives=merged.get("learning_objectives", []),
                time_sections=time_sections_dicts,
                required_materials=merged.get("required_materials", []),
                teacher_notes=merged.get("teacher_notes", ""),
            )
            try:
                new_todos = await generate_preparation_todos(prep_ctx)
            except Exception:
                logger.error(
                    "Preparation todo regeneration failed for lesson %s:\n%s",
                    lesson_id, traceback.format_exc(),
                )

        await update_task_progress(
            redis, task_id,
            step_name="Reconciling preparation",
            step_status=TaskStatus.COMPLETED,
            progress_pct=80,
            ttl=ttl,
        )

        # --- Step 4: Persist changes ---
        await update_task_progress(
            redis, task_id,
            current_step="Persisting changes",
            progress_pct=85,
            step_name="Persisting changes",
            step_status=TaskStatus.RUNNING,
            ttl=ttl,
        )

        from sqlalchemy.orm.attributes import flag_modified

        async with SessionLocal() as session:
            lesson = await session.get(LessonPlan, lesson_id)
            if lesson is None:
                raise ValueError(f"LessonPlan {lesson_id} not found")

            for field_name, value in updated_fields.items():
                setattr(lesson, field_name, value)
                if field_name in ("learning_objectives", "time_sections", "required_materials"):
                    flag_modified(lesson, field_name)

            # Sync LessonObjective records when objectives are updated
            if "learning_objectives" in updated_fields:
                old_objectives_result = await session.execute(
                    select(LessonObjective).where(
                        LessonObjective.lesson_plan_id == lesson_id
                    )
                )
                for old_obj in old_objectives_result.scalars().all():
                    await session.delete(old_obj)
                await session.flush()

                new_objectives = updated_fields["learning_objectives"]
                if isinstance(new_objectives, list):
                    for pos, obj_text in enumerate(new_objectives):
                        text = obj_text if isinstance(obj_text, str) else str(obj_text)
                        session.add(LessonObjective(
                            lesson_plan_id=lesson_id,
                            text=text,
                            position=pos,
                        ))

            if needs_todo_reconciliation:
                from app.models.enums import LessonPreparationStatus

                todos_result = await session.execute(
                    select(LessonPreparationTodo).where(
                        LessonPreparationTodo.lesson_plan_id == lesson_id
                    )
                )
                existing_todos = todos_result.scalars().all()
                for todo in existing_todos:
                    if todo.status == LessonPreparationStatus.PENDING:
                        await session.delete(todo)
                    elif todo.status == LessonPreparationStatus.DONE:
                        todo.outdated = True

                for todo in new_todos:
                    session.add(
                        LessonPreparationTodo(
                            lesson_plan_id=lesson_id,
                            title=todo.title,
                            description=todo.description,
                            why=todo.why,
                        )
                    )

            for item in feedback_items:
                original_value = lesson_data.get(item["field_name"])
                feedback_record = Feedback(
                    user_id=user_id,
                    target_type=FeedbackTargetType.LESSON_PLAN,
                    target_id=lesson_id,
                    field_name=item["field_name"],
                    original_text=str(original_value) if original_value is not None else None,
                    feedback_text=item["user_feedback"],
                    organization_id=organization_id,
                )
                session.add(feedback_record)

            logger.info(
                "Saving %d feedback record(s) for lesson %s by user %s",
                len(feedback_items), lesson_id, user_id,
            )

            req = await session.get(LesplanRequest, request_id)
            if req is not None:
                req.status = LesplanStatus.COMPLETED
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
        logger.info("Lesson feedback applied for lesson %s, updated: %s", lesson_id, list(updated_fields.keys()))

    except Exception:
        logger.error(
            "Lesson feedback task failed for %s:\n%s", lesson_id, traceback.format_exc()
        )
        await update_task_progress(
            redis, task_id,
            status=TaskStatus.FAILED,
            error="Lesson feedback processing failed",
            ttl=ttl,
        )
        try:
            async with SessionLocal() as session:
                req = await session.get(LesplanRequest, request_id)
                if req is not None:
                    req.status = LesplanStatus.COMPLETED
                    await session.commit()
        except Exception:
            logger.error("Failed to reset lesplan %s status after lesson feedback failure", request_id)
