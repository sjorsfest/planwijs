from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


class SchoolConfigMethod(BaseModel, table=True):
    __tablename__ = "school_config_method"
    __table_args__ = (
        UniqueConstraint("school_config_id", "method_id", name="uq_school_config_method"),
    )

    school_config_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("school_config.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    method_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("method.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
