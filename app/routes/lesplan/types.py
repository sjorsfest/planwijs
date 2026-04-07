from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import LesplanStatus, LessonPreparationStatus


class CreateLesplanRequest(BaseModel):
    class_id: str
    book_id: str
    selected_paragraph_ids: list[str] = Field(min_length=1)
    num_lessons: int = Field(ge=1)
    lesson_duration_minutes: int = Field(ge=1)


class FeedbackItem(BaseModel):
    field_name: str = Field(min_length=1)
    specific_part: str = ""
    user_feedback: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    items: list[FeedbackItem] = Field(min_length=1)


class TimeSectionResponse(BaseModel):
    start_min: int
    end_min: int
    activity: str
    description: str
    activity_type: str


class LessonPreparationTodoResponse(BaseModel):
    id: str
    title: str
    description: str
    why: str
    status: str
    due_date: date | None
    created_at: datetime


class CreateLessonPreparationTodoRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    why: str = Field(min_length=1)
    status: LessonPreparationStatus = LessonPreparationStatus.PENDING
    due_date: date | None = None


class UpdateLessonPreparationTodoRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    why: str | None = Field(default=None, min_length=1)
    status: LessonPreparationStatus | None = None
    due_date: date | None = None


class UpdateLessonPlannedDateRequest(BaseModel):
    planned_date: date | None = None


class LessonPlanResponse(BaseModel):
    id: str
    lesson_number: int
    planned_date: date | None
    title: str
    learning_objectives: list[str]
    time_sections: list[TimeSectionResponse]
    required_materials: list[str]
    covered_paragraph_ids: list[str]
    teacher_notes: str
    created_at: datetime
    preparation_todos: list[LessonPreparationTodoResponse]


class LessonOutlineItemResponse(BaseModel):
    lesson_number: int
    subject_focus: str
    description: str
    teaching_approach_hint: str = ""
    builds_on: str
    concept_tags: list[str] = Field(default_factory=list)
    lesson_intention: str = ""
    end_understanding: str = ""
    sequence_rationale: str = ""
    builds_on_lessons: list[int] = Field(default_factory=list)
    paragraph_indices: list[int] = Field(default_factory=list)


class GoalCoverageItemResponse(BaseModel):
    goal: str
    lesson_numbers: list[int] = Field(default_factory=list)
    rationale: str = ""


class KnowledgeCoverageItemResponse(BaseModel):
    knowledge: str
    lesson_numbers: list[int] = Field(default_factory=list)
    rationale: str = ""


class ApprovalReadinessResponse(BaseModel):
    ready_for_approval: bool = False
    rationale: str = ""
    checklist: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class LesplanOverviewResponse(BaseModel):
    id: str
    title: str
    series_summary: str
    series_themes: list[str]
    learning_goals: list[str]
    key_knowledge: list[str]
    recommended_approach: str
    learning_progression: str
    lesson_outline: list[LessonOutlineItemResponse]
    goal_coverage: list[GoalCoverageItemResponse]
    knowledge_coverage: list[KnowledgeCoverageItemResponse]
    approval_readiness: ApprovalReadinessResponse
    didactic_approach: str
    lessons: list[LessonPlanResponse]


class LesplanResponse(BaseModel):
    id: str
    user_id: str
    class_id: str
    book_id: str
    selected_paragraph_ids: list[str]
    num_lessons: int
    lesson_duration_minutes: int
    status: LesplanStatus
    created_at: datetime
    updated_at: datetime
    overview: LesplanOverviewResponse | None
