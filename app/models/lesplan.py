from datetime import date
from typing import Any, List, Optional

from sqlalchemy import Column, Date, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from app.models.base import BaseModel
from app.models.enums import LesplanStatus, LessonPreparationStatus

class LesplanRequest(BaseModel, table=True):
    __tablename__ = "lesplan_request"

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    class_id: str = Field(
        sa_column=Column(String, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    book_id: str = Field(
        sa_column=Column(String, ForeignKey("book.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    classroom_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("classroom.id", ondelete="CASCADE"), nullable=True, index=True),
    )
    selected_paragraph_ids: List[str] = Field(
        default_factory=list,
        sa_column=Column("selected_paragraph_ids", JSONB, nullable=False, server_default="[]"),
    )
    num_lessons: int = Field(ge=1)
    lesson_duration_minutes: int = Field(ge=1)
    status: LesplanStatus = Field(
        default=LesplanStatus.PENDING,
        sa_column=Column(
            SAEnum(LesplanStatus, name="lesplan_status", create_type=False),
            nullable=False,
        ),
    )

    overview: Optional["LesplanOverview"] = Relationship(back_populates="request")


class LesplanOverview(BaseModel, table=True):
    __tablename__ = "lesplan_overview"

    request_id: str = Field(
        sa_column=Column(String, ForeignKey("lesplan_request.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    )
    title: str
    series_summary: str
    series_themes: List[str] = Field(
        default_factory=list,
        sa_column=Column("series_themes", JSONB, nullable=False, server_default="[]"),
    )
    learning_goals: List[str] = Field(
        default_factory=list,
        sa_column=Column("learning_goals", JSONB, nullable=False, server_default="[]"),
    )
    key_knowledge: List[str] = Field(
        default_factory=list,
        sa_column=Column("key_knowledge", JSONB, nullable=False, server_default="[]"),
    )
    recommended_approach: str
    learning_progression: str
    lesson_outline: List[Any] = Field(
        default_factory=list,
        sa_column=Column("lesson_outline", JSONB, nullable=False, server_default="[]"),
    )
    goal_coverage: List[Any] = Field(
        default_factory=list,
        sa_column=Column("goal_coverage", JSONB, nullable=False, server_default="[]"),
    )
    knowledge_coverage: List[Any] = Field(
        default_factory=list,
        sa_column=Column("knowledge_coverage", JSONB, nullable=False, server_default="[]"),
    )
    didactic_approach: str

    request: Optional["LesplanRequest"] = Relationship(back_populates="overview")
    lessons: List["LessonPlan"] = Relationship(back_populates="overview")


class LessonPlan(BaseModel, table=True):
    __tablename__ = "lesson_plan"

    overview_id: str = Field(
        sa_column=Column(String, ForeignKey("lesplan_overview.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    lesson_number: int = Field(ge=1)
    planned_date: Optional[date] = Field(
        default=None,
        sa_column=Column(Date, nullable=True),
    )
    title: str
    learning_objectives: List[str] = Field(
        default_factory=list,
        sa_column=Column("learning_objectives", JSONB, nullable=False, server_default="[]"),
    )
    time_sections: List[Any] = Field(
        default_factory=list,
        sa_column=Column("time_sections", JSONB, nullable=False, server_default="[]"),
    )
    required_materials: List[str] = Field(
        default_factory=list,
        sa_column=Column("required_materials", JSONB, nullable=False, server_default="[]"),
    )
    covered_paragraph_ids: List[str] = Field(
        default_factory=list,
        sa_column=Column("covered_paragraph_ids", JSONB, nullable=False, server_default="[]"),
    )
    teacher_notes: str

    overview: Optional["LesplanOverview"] = Relationship(back_populates="lessons")
    preparation_todos: List["LessonPreparationTodo"] = Relationship(back_populates="lesson_plan")


class LessonPreparationTodo(BaseModel, table=True):
    __tablename__ = "lesson_preparation_todo"

    lesson_plan_id: str = Field(
        sa_column=Column(String, ForeignKey("lesson_plan.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    title: str
    description: str
    why: str
    status: LessonPreparationStatus = Field(
        default=LessonPreparationStatus.PENDING,
        sa_column=Column(
            SAEnum(LessonPreparationStatus, name="lesson_preparation_status", create_type=False),
            nullable=False,
        ),
    )
    due_date: Optional[date] = Field(
        default=None,
        sa_column=Column(Date, nullable=True),
    )

    lesson_plan: Optional["LessonPlan"] = Relationship(back_populates="preparation_todos")


