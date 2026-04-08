from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User


async def get_by_id(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def get_by_google_id(session: AsyncSession, google_id: str) -> User | None:
    result = await session.execute(select(User).where(User.google_id == google_id))
    return result.scalar_one_or_none()


async def save(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
