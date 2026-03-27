from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.subject import Subject as SubjectModel


async def _subject_exists(session: AsyncSession, subject_id: str) -> bool:
    result = await session.execute(select(SubjectModel.id).where(SubjectModel.id == subject_id))
    return result.scalars().first() is not None
