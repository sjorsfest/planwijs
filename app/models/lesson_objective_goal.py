from typing import Optional

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, Relationship

from app.models.base import BaseModel


class LessonObjectiveGoal(BaseModel, table=True):
    __tablename__ = "lesson_objective_goal"
    __table_args__ = (
        UniqueConstraint("lesson_objective_id", "learning_goal_id", name="uq_lesson_objective_goal"),
    )

    lesson_objective_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("lesson_objective.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    learning_goal_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("learning_goal.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Resolved at runtime by SQLModel via the shared model registry (app/models/__init__.py).
    # Do NOT use `from __future__ import annotations` or TYPE_CHECKING imports — breaks SQLAlchemy's mapper.
    lesson_objective: Optional["LessonObjective"] = Relationship(back_populates="goal_links")  # type: ignore[name-defined]
    learning_goal: Optional["LearningGoal"] = Relationship(back_populates="objective_links")  # type: ignore[name-defined]
