import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_read_with_retry
from app.exceptions import NotFoundError
from app.models.classroom import Classroom, ClassroomCreate
from app.repositories import room as room_repo

logger = logging.getLogger(__name__)


async def list_classrooms(user_id: str, org_id: str | None = None) -> list[Classroom]:
    async def _op(session: AsyncSession) -> list[Classroom]:
        return await room_repo.list_visible(session, user_id, org_id)

    return await run_read_with_retry(_op)


async def get_classroom(user_id: str, classroom_id: str, org_id: str | None = None) -> Classroom:
    async def _op(session: AsyncSession) -> Classroom:
        classroom = await room_repo.get_by_id(session, classroom_id)
        if not classroom:
            raise NotFoundError("Classroom not found")
        if classroom.user_id != user_id and classroom.organization_id != org_id:
            raise NotFoundError("Classroom not found")
        return classroom

    return await run_read_with_retry(_op)


async def create_classroom(
    session: AsyncSession, data: ClassroomCreate, user_id: str
) -> Classroom:
    classroom = Classroom.model_validate(data, update={"user_id": user_id})
    classroom = await room_repo.save(session, classroom)
    logger.info(
        "Created classroom: id=%s name=%s user_id=%s", classroom.id, classroom.name, classroom.user_id
    )
    return classroom


async def update_classroom(
    session: AsyncSession, classroom_id: str, data: Classroom, user_id: str
) -> Classroom:
    classroom = await room_repo.get_by_id(session, classroom_id)
    if not classroom or classroom.user_id != user_id:
        raise NotFoundError("Classroom not found")
    update = data.model_dump(exclude_unset=True, exclude={"id", "user_id"})
    classroom.sqlmodel_update(update)
    await session.commit()
    await session.refresh(classroom)
    logger.info("Updated classroom: id=%s fields=%s", classroom_id, list(update.keys()))
    return classroom


async def delete_classroom(session: AsyncSession, classroom_id: str, user_id: str) -> None:
    classroom = await room_repo.get_by_id(session, classroom_id)
    if not classroom or classroom.user_id != user_id:
        raise NotFoundError("Classroom not found")
    await room_repo.delete(session, classroom)
    logger.info("Deleted classroom: id=%s", classroom_id)
