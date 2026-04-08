import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session, run_read_with_retry
from app.models.enums import Subject
from app.models.method import Method

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("/", response_model=list[Method])
async def list_methods(
    subject: Optional[Subject] = Query(default=None),
):
    async def operation(session: AsyncSession) -> list[Method]:
        stmt = select(Method).order_by(Method.title)
        if subject is not None:
            stmt = stmt.where(Method.subject == subject)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    return await run_read_with_retry(operation)


@router.get("/{method_id}", response_model=Method)
async def get_method(method_id: str):
    async def operation(session: AsyncSession) -> Method:
        method = await session.get(Method, method_id)
        if not method:
            raise HTTPException(status_code=404, detail="Method not found")
        return method

    return await run_read_with_retry(operation)


@router.post("/", response_model=Method, status_code=201)
async def create_method(data: Method, session: AsyncSession = Depends(get_session)):
    method = Method.model_validate(data)
    session.add(method)
    await session.commit()
    await session.refresh(method)
    logger.info("Created method: id=%s slug=%s", method.id, method.slug)
    return method


@router.patch("/{method_id}", response_model=Method)
async def update_method(method_id: str, data: Method, session: AsyncSession = Depends(get_session)):
    method = await session.get(Method, method_id)
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    method.sqlmodel_update(update)
    await session.commit()
    await session.refresh(method)
    logger.info("Updated method: id=%s fields=%s", method_id, list(update.keys()))
    return method


@router.delete("/{method_id}", status_code=204)
async def delete_method(method_id: str, session: AsyncSession = Depends(get_session)):
    method = await session.get(Method, method_id)
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    await session.delete(method)
    await session.commit()
    logger.info("Deleted method: id=%s", method_id)
