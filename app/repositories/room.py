from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.classroom import Classroom


async def list_for_user(session: AsyncSession, user_id: str) -> list[Classroom]:
    result = await session.execute(
        select(Classroom)
        .where(Classroom.user_id == user_id)
        .order_by(Classroom.created_at.desc())  # type: ignore[union-attr]
    )
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, classroom_id: str) -> Classroom | None:
    return await session.get(Classroom, classroom_id)


async def save(session: AsyncSession, classroom: Classroom) -> Classroom:
    session.add(classroom)
    await session.commit()
    await session.refresh(classroom)
    return classroom


async def delete(session: AsyncSession, classroom: Classroom) -> None:
    await session.delete(classroom)
    await session.commit()
