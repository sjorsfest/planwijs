import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_read_with_retry
from app.exceptions import NotFoundError
from app.models.enums import Subject
from app.models.method import Method
from app.repositories import method as method_repo

logger = logging.getLogger(__name__)


async def list_methods(*, subject: Optional[Subject] = None) -> list[Method]:
    async def _op(session: AsyncSession) -> list[Method]:
        return await method_repo.list_all(session, subject=subject)

    return await run_read_with_retry(_op)


async def get_method(method_id: str) -> Method:
    async def _op(session: AsyncSession) -> Method:
        method = await method_repo.get_by_id(session, method_id)
        if not method:
            raise NotFoundError("Method not found")
        return method

    return await run_read_with_retry(_op)


async def create_method(session: AsyncSession, data: Method) -> Method:
    method = Method.model_validate(data)
    method = await method_repo.save(session, method)
    logger.info("Created method: id=%s slug=%s", method.id, method.slug)
    return method


async def update_method(
    session: AsyncSession, method_id: str, data: Method
) -> Method:
    method = await method_repo.get_by_id(session, method_id)
    if not method:
        raise NotFoundError("Method not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    method.sqlmodel_update(update)
    await session.commit()
    await session.refresh(method)
    logger.info("Updated method: id=%s fields=%s", method_id, list(update.keys()))
    return method


async def delete_method(session: AsyncSession, method_id: str) -> None:
    method = await method_repo.get_by_id(session, method_id)
    if not method:
        raise NotFoundError("Method not found")
    await method_repo.delete(session, method)
    logger.info("Deleted method: id=%s", method_id)
