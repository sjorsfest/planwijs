from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import Event, EventCreate

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=list[Event])
async def list_events(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Event))
    return result.scalars().all()


@router.get("/{event_id}", response_model=Event)
async def get_event(event_id: str, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/", response_model=Event, status_code=201)
async def create_event(data: EventCreate, session: AsyncSession = Depends(get_session)):
    event = Event.model_validate(data)
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.patch("/{event_id}", response_model=Event)
async def update_event(event_id: str, data: Event, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    event.sqlmodel_update(update)
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: str, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await session.delete(event)
    await session.commit()
