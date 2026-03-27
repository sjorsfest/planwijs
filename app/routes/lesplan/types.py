from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import LesplanStatus, LessonPreparationStatus


class CreateLesplanRequest(BaseModel):
    user_id: str
    class_id: str
    book_id: str
    selected_paragraph_ids: list[str] = Field(min_length=1)
    num_lessons: int = Field(ge=1)
    lesson_duration_minutes: int = Field(ge=1)


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=1)


class FeedbackMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


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
    builds_on: str


class LesplanOverviewResponse(BaseModel):
    id: str
    title: str
    learning_goals: list[str]
    key_knowledge: list[str]
    recommended_approach: str
    learning_progression: str
    lesson_outline: list[LessonOutlineItemResponse]
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
    feedback_messages: list[FeedbackMessageResponse]
