import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_read_with_retry
from app.exceptions import NotFoundError
from app.models.school_class import Class
from app.models.enums import ClassDifficulty, Level, SchoolYear
from app.repositories import classroom as classroom_repo
from app.services.visibility import visible_filter

logger = logging.getLogger(__name__)


async def list_classes(
    user_id: str,
    org_id: str | None,
    *,
    level: Optional[Level] = None,
    school_year: Optional[SchoolYear] = None,
    difficulty: Optional[ClassDifficulty] = None,
) -> list[Class]:
    async def _op(session: AsyncSession) -> list[Class]:
        return await classroom_repo.list_visible(
            session,
            user_id,
            org_id,
            level=level,
            school_year=school_year,
            difficulty=difficulty,
        )

    return await run_read_with_retry(_op)


async def get_class(user_id: str, class_id: str, org_id: str | None = None) -> Class:
    async def _op(session: AsyncSession) -> Class:
        classroom = await classroom_repo.get_by_id(session, class_id)
        if not classroom:
            raise NotFoundError("Class not found")
        # Visible if user owns it or it's shared via their org
        if classroom.user_id != user_id and classroom.organization_id != org_id:
            raise NotFoundError("Class not found")
        return classroom

    return await run_read_with_retry(_op)


async def create_class(session: AsyncSession, data: Class, user_id: str) -> Class:
    obj = data.model_dump(exclude_unset=True, exclude={"id", "user_id"})
    obj["user_id"] = user_id
    classroom = Class.model_validate(obj)
    classroom = await classroom_repo.save(session, classroom)
    logger.info("Created class: id=%s user_id=%s", classroom.id, classroom.user_id)
    return classroom


async def update_class(
    session: AsyncSession, class_id: str, data: Class, user_id: str
) -> Class:
    classroom = await classroom_repo.get_by_id(session, class_id)
    if not classroom or classroom.user_id != user_id:
        raise NotFoundError("Class not found")

    update = data.model_dump(exclude_unset=True, exclude={"id", "user_id"})
    classroom.sqlmodel_update(update)
    await session.commit()
    await session.refresh(classroom)
    logger.info("Updated class: id=%s fields=%s", class_id, list(update.keys()))
    return classroom


async def delete_class(session: AsyncSession, class_id: str, user_id: str) -> None:
    classroom = await classroom_repo.get_by_id(session, class_id)
    if not classroom or classroom.user_id != user_id:
        raise NotFoundError("Class not found")
    await classroom_repo.delete(session, classroom)
    logger.info("Deleted class: id=%s", class_id)
