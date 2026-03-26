import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session, run_read_with_retry
from app.models.classroom import Class
from app.models.enums import ClassDifficulty, Level, SchoolYear, Subject

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("/", response_model=list[Class])
async def list_classes(
    user_id: Optional[str] = Query(default=None),
    subject: Optional[Subject] = Query(default=None),
    level: Optional[Level] = Query(default=None),
    school_year: Optional[SchoolYear] = Query(default=None),
    difficulty: Optional[ClassDifficulty] = Query(default=None),
):
    async def operation(session: AsyncSession) -> list[Class]:
        stmt = select(Class).order_by(Class.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(Class.user_id == user_id)
        if subject is not None:
            stmt = stmt.where(Class.subject == subject)
        if level is not None:
            stmt = stmt.where(Class.level == level)
        if school_year is not None:
            stmt = stmt.where(Class.school_year == school_year)
        if difficulty is not None:
            stmt = stmt.where(Class.difficulty == difficulty)

        result = await session.execute(stmt)
        classes = result.scalars().all()
        logger.debug("Listed %d classes", len(classes))
        return classes

    return await run_read_with_retry(operation)


@router.get("/{class_id}", response_model=Class)
async def get_class(class_id: str):
    async def operation(session: AsyncSession) -> Class:
        classroom = await session.get(Class, class_id)
        if not classroom:
            logger.warning("Class not found: id=%s", class_id)
            raise HTTPException(status_code=404, detail="Class not found")
        logger.debug("Fetched class: id=%s", class_id)
        return classroom

    return await run_read_with_retry(operation)


@router.post("/", response_model=Class, status_code=201)
async def create_class(data: Class, session: AsyncSession = Depends(get_session)):
    classroom = Class.model_validate(data)
    session.add(classroom)
    await session.commit()
    await session.refresh(classroom)
    logger.info("Created class: id=%s user_id=%s", classroom.id, classroom.user_id)
    return classroom


@router.patch("/{class_id}", response_model=Class)
async def update_class(class_id: str, data: Class, session: AsyncSession = Depends(get_session)):
    classroom = await session.get(Class, class_id)
    if not classroom:
        logger.warning("Update failed, class not found: id=%s", class_id)
        raise HTTPException(status_code=404, detail="Class not found")

    update = data.model_dump(exclude_unset=True, exclude={"id"})
    classroom.sqlmodel_update(update)
    await session.commit()
    await session.refresh(classroom)
    logger.info("Updated class: id=%s fields=%s", class_id, list(update.keys()))
    return classroom


@router.delete("/{class_id}", status_code=204)
async def delete_class(class_id: str, session: AsyncSession = Depends(get_session)):
    classroom = await session.get(Class, class_id)
    if not classroom:
        logger.warning("Delete failed, class not found: id=%s", class_id)
        raise HTTPException(status_code=404, detail="Class not found")

    await session.delete(classroom)
    await session.commit()
    logger.info("Deleted class: id=%s", class_id)
