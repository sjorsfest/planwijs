from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.event import Event


async def list_for_user(session: AsyncSession, user_id: str) -> list[Event]:
    result = await session.execute(select(Event).where(Event.user_id == user_id))
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, event_id: str) -> Event | None:
    return await session.get(Event, event_id)


async def save(session: AsyncSession, event: Event) -> Event:
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def delete(session: AsyncSession, event: Event) -> None:
    await session.delete(event)
    await session.commit()
