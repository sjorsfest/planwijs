from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.school_class import Class
from app.models.enums import ClassDifficulty, Level, SchoolYear, Subject


async def list_for_user(
    session: AsyncSession,
    user_id: str,
    *,
    subject: Subject | None = None,
    level: Level | None = None,
    school_year: SchoolYear | None = None,
    difficulty: ClassDifficulty | None = None,
) -> list[Class]:
    stmt = (
        select(Class)
        .where(Class.user_id == user_id)
        .order_by(Class.created_at.desc())  # type: ignore[union-attr]
    )
    if subject is not None:
        stmt = stmt.where(Class.subject == subject)
    if level is not None:
        stmt = stmt.where(Class.level == level)
    if school_year is not None:
        stmt = stmt.where(Class.school_year == school_year)
    if difficulty is not None:
        stmt = stmt.where(Class.difficulty == difficulty)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, class_id: str) -> Class | None:
    return await session.get(Class, class_id)


async def save(session: AsyncSession, classroom: Class) -> Class:
    session.add(classroom)
    await session.commit()
    await session.refresh(classroom)
    return classroom


async def delete(session: AsyncSession, classroom: Class) -> None:
    await session.delete(classroom)
    await session.commit()
