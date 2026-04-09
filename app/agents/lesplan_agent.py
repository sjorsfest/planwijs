"""Backward-compatible exports for lesplan agents.

Implementation now lives in `app.agents.lesplan`.
"""

from __future__ import annotations

from app.agents.lesplan import (
    GeneratedLessonPlan,
    GeneratedLessons,
    GeneratedLesplanOverview,
    GeneratedOverviewIdentity,
    GeneratedOverviewLearningGoals,
    GeneratedOverviewSequence,
    GeneratedOverviewTeacherNotes,
    GeneratedTimeSectionItem,
    GoalCoverageItem,
    KnowledgeCoverageItem,
    LesplanContext,
    LessonOutlineItem,
    _normalize_learning_goals_for_context,
    _normalize_lesson_outline_for_context,
    _validate_overview_for_context,
    generate_lessons,
    stream_overview,
)

__all__ = [
    "GeneratedLessonPlan",
    "GeneratedLessons",
    "GeneratedLesplanOverview",
    "GeneratedOverviewIdentity",
    "GeneratedOverviewLearningGoals",
    "GeneratedOverviewSequence",
    "GeneratedOverviewTeacherNotes",
    "GeneratedTimeSectionItem",
    "GoalCoverageItem",
    "KnowledgeCoverageItem",
    "LesplanContext",
    "LessonOutlineItem",
    "_normalize_learning_goals_for_context",
    "_normalize_lesson_outline_for_context",
    "_validate_overview_for_context",
    "generate_lessons",
    "stream_overview",
]
