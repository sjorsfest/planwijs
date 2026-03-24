from datetime import datetime, timezone

from cuid2 import Cuid
from sqlalchemy import event
from sqlmodel import Field, SQLModel

_cuid = Cuid()


def _utcnow() -> datetime:
    """Return current time as naive UTC (TIMESTAMP WITHOUT TIME ZONE)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseModel(SQLModel):
    id: str = Field(default_factory=_cuid.generate, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


@event.listens_for(BaseModel, "before_update", propagate=True)
def _set_updated_at(mapper: object, connection: object, target: BaseModel) -> None:
    target.updated_at = _utcnow()
