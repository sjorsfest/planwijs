from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.enums import SubjectCategory
from app.models.subject import Subject


async def list_all(
    session: AsyncSession,
    *,
    category: SubjectCategory | None = None,
) -> list[Subject]:
    stmt = select(Subject).order_by(Subject.category, Subject.name)
    if category is not None:
        stmt = stmt.where(Subject.category == category)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, subject_id: str) -> Subject | None:
    return await session.get(Subject, subject_id)


async def save(session: AsyncSession, subject: Subject) -> Subject:
    session.add(subject)
    await session.commit()
    await session.refresh(subject)
    return subject


async def delete(session: AsyncSession, subject: Subject) -> None:
    await session.delete(subject)
    await session.commit()
