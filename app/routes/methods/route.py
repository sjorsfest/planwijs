from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.enums import Subject
from app.models.method import Method
from app.models.user import User
from app.routes.school_config.route import _get_effective_config, _get_method_ids
from app.services import method as method_service

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("/", response_model=list[Method])
async def list_methods(
    subject: Optional[Subject] = Query(default=None),
    for_school_config: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Method]:
    methods = await method_service.list_methods(subject=subject)
    if for_school_config:
        config, _ = await _get_effective_config(session, current_user.id)
        if config:
            selected = set(await _get_method_ids(session, config.id))
            methods = [m for m in methods if m.id in selected]
        else:
            methods = []
    return methods


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
