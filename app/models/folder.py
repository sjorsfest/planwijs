from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class Folder(BaseModel, table=True):
    __tablename__ = "folder"

    user_id: str = Field(foreign_key="user.id", index=True)
    name: str
    parent_id: Optional[str] = Field(
        default=None, foreign_key="folder.id", index=True
    )
