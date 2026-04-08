import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session, run_read_with_retry
from app.models.enums import SubjectCategory
from app.models.subject import Subject

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/", response_model=list[Subject])
async def list_subjects(
    category: Optional[SubjectCategory] = Query(default=None),
):
    async def operation(session: AsyncSession) -> list[Subject]:
        stmt = select(Subject).order_by(Subject.category, Subject.name)
        if category is not None:
            stmt = stmt.where(Subject.category == category)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    return await run_read_with_retry(operation)


@router.get("/{subject_id}", response_model=Subject)
async def get_subject(subject_id: str):
    async def operation(session: AsyncSession) -> Subject:
        subject = await session.get(Subject, subject_id)
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        return subject

    return await run_read_with_retry(operation)


@router.post("/", response_model=Subject, status_code=201)
async def create_subject(data: Subject, session: AsyncSession = Depends(get_session)):
    subject = Subject.model_validate(data)
    session.add(subject)
    await session.commit()
    await session.refresh(subject)
    logger.info("Created subject: id=%s slug=%s", subject.id, subject.slug)
    return subject


@router.patch("/{subject_id}", response_model=Subject)
async def update_subject(subject_id: str, data: Subject, session: AsyncSession = Depends(get_session)):
    subject = await session.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    subject.sqlmodel_update(update)
    await session.commit()
    await session.refresh(subject)
    logger.info("Updated subject: id=%s fields=%s", subject_id, list(update.keys()))
    return subject


@router.delete("/{subject_id}", status_code=204)
async def delete_subject(subject_id: str, session: AsyncSession = Depends(get_session)):
    subject = await session.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    await session.delete(subject)
    await session.commit()
    logger.info("Deleted subject: id=%s", subject_id)
