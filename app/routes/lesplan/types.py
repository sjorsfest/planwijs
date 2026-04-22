from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import LesplanStatus, LessonPreparationStatus


class CreateLesplanRequest(BaseModel):
    class_id: str
    book_id: str
    selected_paragraph_ids: list[str] = Field(min_length=1)
    num_lessons: int = Field(ge=1)
    classroom_id: str | None = None
    file_ids: list[str] = Field(default_factory=list)


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
    outdated: bool
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


class LearningGoalResponse(BaseModel):
    id: str
    text: str
    position: int


class LessonObjectiveResponse(BaseModel):
    id: str
    text: str
    position: int
    goal_ids: list[str] = Field(default_factory=list)


class LessonPlanResponse(BaseModel):
    id: str
    lesson_number: int
    planned_date: date | None
    title: str
    learning_objectives: list[str]
    lesson_objective_records: list[LessonObjectiveResponse] = Field(default_factory=list)
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


class LesplanOverviewResponse(BaseModel):
    id: str
    title: str
    series_summary: str
    series_themes: list[str]
    learning_goals: list[str]
    learning_goal_records: list[LearningGoalResponse] = Field(default_factory=list)
    key_knowledge: list[str]
    recommended_approach: str
    learning_progression: str
    lesson_outline: list[LessonOutlineItemResponse]
    goal_coverage: list[GoalCoverageItemResponse]
    knowledge_coverage: list[KnowledgeCoverageItemResponse]
    didactic_approach: str
    lessons: list[LessonPlanResponse]


class TaskSubmittedResponse(BaseModel):
    task_id: str
    resource_id: str
    task_type: str
    status: str


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
