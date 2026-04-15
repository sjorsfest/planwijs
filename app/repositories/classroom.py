from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.school_class import Class
from app.models.enums import ClassDifficulty, Level, SchoolYear, Subject
from app.services.visibility import visible_filter


async def list_visible(
    session: AsyncSession,
    user_id: str,
    org_id: str | None,
    *,
    subject: Subject | None = None,
    level: Level | None = None,
    school_year: SchoolYear | None = None,
    difficulty: ClassDifficulty | None = None,
) -> list[Class]:
    stmt = (
        select(Class)
        .where(visible_filter(Class, user_id, org_id))
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
