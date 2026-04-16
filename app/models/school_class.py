from typing import Optional

from pydantic import model_validator
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import ClassDifficulty, ClassSupportChallenge, Level, SchoolYear, Subject

_ENUM_FIELDS: dict[str, type] = {
    "subject": Subject,
    "level": Level,
    "school_year": SchoolYear,
    "difficulty": ClassDifficulty,
    "support_challenge": ClassSupportChallenge,
}


class Class(BaseModel, table=True):
    __tablename__ = "class"

    @model_validator(mode="before")
    @classmethod
    def _coerce_enums(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        for field, enum_cls in _ENUM_FIELDS.items():
            v = values.get(field)
            if isinstance(v, str):
                values[field] = enum_cls(v)
        return values

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    name: str
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
    attention_span_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        description="Geschatte maximale aandachtsspanne in minuten voordat leerlingen een activiteitswisseling nodig hebben.",
    )
    support_challenge: Optional[ClassSupportChallenge] = Field(
        default=None,
        description=(
            "Meer ondersteuning = meer scaffolding en begeleiding; "
            "Gebalanceerd = standaard; "
            "Meer uitdaging = complexere taken en meer zelfstandigheid."
        ),
        sa_column=Column(SAEnum(ClassSupportChallenge, name="class_support_challenge", create_type=False), nullable=True),
    )
    class_notes: Optional[str] = Field(
        default=None,
        description="Vrije notities van de docent over de klas (bijv. bijzonderheden, werkhouding, samenstelling).",
    )
    organization_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("organization.id", ondelete="SET NULL"), nullable=True, index=True),
    )
