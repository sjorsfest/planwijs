import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session, run_read_with_retry
from app.models import Event, EventCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=list[Event])
async def list_events():
    async def operation(session: AsyncSession) -> list[Event]:
        result = await session.execute(select(Event))
        events = result.scalars().all()
        logger.debug("Listed %d events", len(events))
        return events

    return await run_read_with_retry(operation)


@router.get("/{event_id}", response_model=Event)
async def get_event(event_id: str):
    async def operation(session: AsyncSession) -> Event:
        event = await session.get(Event, event_id)
        if not event:
            logger.warning("Event not found: id=%s", event_id)
            raise HTTPException(status_code=404, detail="Event not found")
        logger.debug("Fetched event: id=%s", event_id)
        return event

    return await run_read_with_retry(operation)


@router.post("/", response_model=Event, status_code=201)
async def create_event(data: EventCreate, session: AsyncSession = Depends(get_session)):
    event = Event.model_validate(data)
    session.add(event)
    await session.commit()
    await session.refresh(event)
    logger.info("Created event: id=%s name=%s", event.id, event.name)
    return event


@router.patch("/{event_id}", response_model=Event)
async def update_event(event_id: str, data: Event, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        logger.warning("Update failed, event not found: id=%s", event_id)
        raise HTTPException(status_code=404, detail="Event not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    event.sqlmodel_update(update)
    await session.commit()
    await session.refresh(event)
    logger.info("Updated event: id=%s fields=%s", event_id, list(update.keys()))
    return event


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: str, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        logger.warning("Delete failed, event not found: id=%s", event_id)
        raise HTTPException(status_code=404, detail="Event not found")
    await session.delete(event)
    await session.commit()
    logger.info("Deleted event: id=%s", event_id)
