from enum import Enum
from typing import Optional

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel


class FileBucket(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class File(BaseModel, table=True):
    __tablename__ = "file"

    user_id: str = Field(foreign_key="user.id", index=True)
    name: str
    content_type: str
    size_bytes: int
    bucket: FileBucket = Field(
        sa_column=Column(
            SAEnum(FileBucket, name="file_bucket", create_type=False),
            nullable=False,
        ),
    )
    object_key: str = Field(unique=True)

    # Optional link to a lesplan request (or other entities in the future)
    lesplan_request_id: Optional[str] = Field(
        default=None, foreign_key="lesplan_request.id", index=True
    )
