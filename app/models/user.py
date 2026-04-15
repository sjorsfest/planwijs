from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.enums import UserRole


class User(BaseModel, table=True):
    name: str
    email: str = Field(unique=True)
    google_id: str = Field(unique=True)
    user_role: UserRole = Field(
        default=UserRole.USER,
        sa_column=Column(
            SAEnum(UserRole, name="user_role", create_type=False),
            nullable=False,
            server_default="USER",
        ),
    )
