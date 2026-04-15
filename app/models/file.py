from enum import Enum
from typing import Optional

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel


class FileBucket(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class FileStatus(str, Enum):
    PENDING = "PENDING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class File(BaseModel, table=True):
    __tablename__ = "file"  # type: ignore[assignment]

    user_id: str = Field(
        sa_column=Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
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
    status: FileStatus = Field(
        default=FileStatus.PENDING,
        sa_column=Column(
            SAEnum(FileStatus, name="file_status", create_type=False),
            nullable=False,
            server_default="PENDING",
        ),
    )
    folder_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("folder.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    extracted_text: Optional[str] = Field(default=None)

    # Optional link to a lesplan request (or other entities in the future)
    lesplan_request_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("lesplan_request.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    # Optional link to a class (extra context documents for this class)
    class_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("class.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    organization_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("organization.id", ondelete="SET NULL"), nullable=True, index=True),
    )
