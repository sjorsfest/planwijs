from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlmodel import Field, Relationship

from app.models.base import BaseModel


class LessonObjective(BaseModel, table=True):
    __tablename__ = "lesson_objective"

    lesson_plan_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("lesson_plan.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    text: str = Field(sa_column=Column(Text, nullable=False))
    position: int = Field(sa_column=Column(Integer, nullable=False))

    lesson_plan: Optional["LessonPlan"] = Relationship(back_populates="lesson_objective_records")
    goal_links: List["LessonObjectiveGoal"] = Relationship(back_populates="lesson_objective")
