from typing import Optional

from sqlalchemy import Column, Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import ClassDifficulty, Level, SchoolYear, Subject


class Class(BaseModel, table=True):
    __tablename__ = "class"

    user_id: str = Field(foreign_key="user.id", index=True)
    subject: Subject = Field(
        default=Subject.UNKNOWN,
        sa_column=Column(SAEnum(Subject, name="subject", create_type=False), nullable=False),
    )
    level: Level = Field(
        default=Level.UNKNOWN,
        sa_column=Column(SAEnum(Level, name="level", create_type=False), nullable=False),
    )
    school_year: SchoolYear = Field(
        default=SchoolYear.UNKNOWN,
        sa_column=Column(SAEnum(SchoolYear, name="school_year", create_type=False), nullable=False),
    )
    size: int = Field(ge=0)
    difficulty: Optional[ClassDifficulty] = Field(
        default=None,
        description=(
            "Verkeerslichtmodel. "
            "Groen = goed hanteerbaar; "
            "Oranje = vraagt extra aandacht; "
            "Rood = uitdagend / intensieve begeleiding nodig."
        ),
        sa_column=Column(SAEnum(ClassDifficulty, name="class_difficulty", create_type=False), nullable=True),
    )
