from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlmodel import Field, Relationship

from app.models.base import BaseModel


class LearningGoal(BaseModel, table=True):
    __tablename__ = "learning_goal"

    overview_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("lesplan_overview.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    text: str = Field(sa_column=Column(Text, nullable=False))
    position: int = Field(sa_column=Column(Integer, nullable=False))

    overview: Optional["LesplanOverview"] = Relationship(back_populates="learning_goal_records")
    objective_links: List["LessonObjectiveGoal"] = Relationship(back_populates="learning_goal")
