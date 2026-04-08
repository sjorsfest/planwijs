from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.event import Event, EventCreate
from app.models.user import User
from app.services import event as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=list[Event])
async def list_events(
    current_user: User = Depends(get_current_user),
) -> list[Event]:
    return await event_service.list_events(current_user.id)


@router.get("/{event_id}", response_model=Event)
async def get_event(
    event_id: str, current_user: User = Depends(get_current_user)
) -> Event:
    return await event_service.get_event(current_user.id, event_id)


@router.post("/", response_model=Event, status_code=201)
async def create_event(
    data: EventCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Event:
    return await event_service.create_event(session, data, current_user.id)


@router.patch("/{event_id}", response_model=Event)
async def update_event(
    event_id: str,
    data: Event,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Event:
    return await event_service.update_event(session, event_id, data, current_user.id)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await event_service.delete_event(session, event_id, current_user.id)
