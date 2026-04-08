from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.enums import Subject
from app.models.method import Method
from app.services import method as method_service

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("/", response_model=list[Method])
async def list_methods(
    subject: Optional[Subject] = Query(default=None),
) -> list[Method]:
    return await method_service.list_methods(subject=subject)


@router.get("/{method_id}", response_model=Method)
async def get_method(method_id: str) -> Method:
    return await method_service.get_method(method_id)


@router.post("/", response_model=Method, status_code=201)
async def create_method(
    data: Method, session: AsyncSession = Depends(get_session)
) -> Method:
    return await method_service.create_method(session, data)


@router.patch("/{method_id}", response_model=Method)
async def update_method(
    method_id: str, data: Method, session: AsyncSession = Depends(get_session)
) -> Method:
    return await method_service.update_method(session, method_id, data)


@router.delete("/{method_id}", status_code=204)
async def delete_method(
    method_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await method_service.delete_method(session, method_id)
