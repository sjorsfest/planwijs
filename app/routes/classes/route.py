from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.school_class import Class
from app.models.enums import ClassDifficulty, Level, SchoolYear, Subject
from app.models.user import User
from app.services import classroom as classroom_service
from app.services.visibility import get_user_org_id

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("/", response_model=list[Class])
async def list_classes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    subject: Optional[Subject] = Query(default=None),
    level: Optional[Level] = Query(default=None),
    school_year: Optional[SchoolYear] = Query(default=None),
    difficulty: Optional[ClassDifficulty] = Query(default=None),
) -> list[Class]:
    org_id = await get_user_org_id(session, current_user.id)
    return await classroom_service.list_classes(
        current_user.id,
        org_id,
        subject=subject,
        level=level,
        school_year=school_year,
        difficulty=difficulty,
    )


@router.get("/{class_id}", response_model=Class)
async def get_class(
    class_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Class:
    org_id = await get_user_org_id(session, current_user.id)
    return await classroom_service.get_class(current_user.id, class_id, org_id)


@router.post("/", response_model=Class, status_code=201)
async def create_class(
    data: Class,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Class:
    return await classroom_service.create_class(session, data, current_user.id)


@router.patch("/{class_id}", response_model=Class)
async def update_class(
    class_id: str,
    data: Class,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Class:
    return await classroom_service.update_class(session, class_id, data, current_user.id)


@router.delete("/{class_id}", status_code=204)
async def delete_class(
    class_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await classroom_service.delete_class(session, class_id, current_user.id)
