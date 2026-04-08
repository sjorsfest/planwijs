import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_read_with_retry
from app.exceptions import NotFoundError
from app.models.event import Event, EventCreate
from app.repositories import event as event_repo

logger = logging.getLogger(__name__)


async def list_events(user_id: str) -> list[Event]:
    async def _op(session: AsyncSession) -> list[Event]:
        return await event_repo.list_for_user(session, user_id)

    return await run_read_with_retry(_op)


async def get_event(user_id: str, event_id: str) -> Event:
    async def _op(session: AsyncSession) -> Event:
        event = await event_repo.get_by_id(session, event_id)
        if not event or event.user_id != user_id:
            raise NotFoundError("Event not found")
        return event

    return await run_read_with_retry(_op)


async def create_event(
    session: AsyncSession, data: EventCreate, user_id: str
) -> Event:
    event = Event.model_validate(data, update={"user_id": user_id})
    event = await event_repo.save(session, event)
    logger.info(
        "Created event: id=%s name=%s user_id=%s", event.id, event.name, event.user_id
    )
    return event


async def update_event(
    session: AsyncSession, event_id: str, data: Event, user_id: str
) -> Event:
    event = await event_repo.get_by_id(session, event_id)
    if not event or event.user_id != user_id:
        raise NotFoundError("Event not found")
    update = data.model_dump(exclude_unset=True, exclude={"id", "user_id"})
    event.sqlmodel_update(update)
    await session.commit()
    await session.refresh(event)
    logger.info("Updated event: id=%s fields=%s", event_id, list(update.keys()))
    return event


async def delete_event(session: AsyncSession, event_id: str, user_id: str) -> None:
    event = await event_repo.get_by_id(session, event_id)
    if not event or event.user_id != user_id:
        raise NotFoundError("Event not found")
    await event_repo.delete(session, event)
    logger.info("Deleted event: id=%s", event_id)
