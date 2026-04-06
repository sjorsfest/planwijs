"""Data models for the lesplan agents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

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
    key_knowledge: list[str] = Field(default_factory=list)
    lesson_outline: list[LessonOutlineItem] = Field(default_factory=list)

    @field_validator("key_knowledge", "lesson_outline", mode="before")
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


class GeneratedOverviewLearningGoals(BaseModel):
    learning_goals: list[str] = Field(default_factory=list)

    @field_validator("learning_goals", mode="before")
    @classmethod
    def _parse_json_list(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                return []
            except json.JSONDecodeError:
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
    attention_span_minutes: int | None = None
    support_challenge: str | None = None
    class_notes: str | None = None
