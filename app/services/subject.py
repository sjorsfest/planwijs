import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_read_with_retry
from app.exceptions import NotFoundError
from app.models.enums import SubjectCategory
from app.models.subject import Subject
from app.repositories import subject as subject_repo

logger = logging.getLogger(__name__)


async def list_subjects(
    *, category: Optional[SubjectCategory] = None
) -> list[Subject]:
    async def _op(session: AsyncSession) -> list[Subject]:
        return await subject_repo.list_all(session, category=category)

    return await run_read_with_retry(_op)


async def get_subject(subject_id: str) -> Subject:
    async def _op(session: AsyncSession) -> Subject:
        subject = await subject_repo.get_by_id(session, subject_id)
        if not subject:
            raise NotFoundError("Subject not found")
        return subject

    return await run_read_with_retry(_op)


async def create_subject(session: AsyncSession, data: Subject) -> Subject:
    subject = Subject.model_validate(data)
    subject = await subject_repo.save(session, subject)
    logger.info("Created subject: id=%s slug=%s", subject.id, subject.slug)
    return subject


async def update_subject(
    session: AsyncSession, subject_id: str, data: Subject
) -> Subject:
    subject = await subject_repo.get_by_id(session, subject_id)
    if not subject:
        raise NotFoundError("Subject not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    subject.sqlmodel_update(update)
    await session.commit()
    await session.refresh(subject)
    logger.info("Updated subject: id=%s fields=%s", subject_id, list(update.keys()))
    return subject


async def delete_subject(session: AsyncSession, subject_id: str) -> None:
    subject = await subject_repo.get_by_id(session, subject_id)
    if not subject:
        raise NotFoundError("Subject not found")
    await subject_repo.delete(session, subject)
    logger.info("Deleted subject: id=%s", subject_id)
