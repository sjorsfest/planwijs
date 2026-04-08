from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.enums import Subject
from app.models.method import Method


async def list_all(
    session: AsyncSession,
    *,
    subject: Subject | None = None,
) -> list[Method]:
    stmt = select(Method).order_by(Method.title)
    if subject is not None:
        stmt = stmt.where(Method.subject == subject)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, method_id: str) -> Method | None:
    return await session.get(Method, method_id)


async def save(session: AsyncSession, method: Method) -> Method:
    session.add(method)
    await session.commit()
    await session.refresh(method)
    return method


async def delete(session: AsyncSession, method: Method) -> None:
    await session.delete(method)
    await session.commit()
