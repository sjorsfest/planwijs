from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.classroom import Classroom, ClassroomCreate
from app.models.user import User
from app.services import room as room_service
from app.services.visibility import get_user_org_id

router = APIRouter(prefix="/classrooms", tags=["classrooms"])


@router.get("/", response_model=list[Classroom])
async def list_classrooms(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Classroom]:
    org_id = await get_user_org_id(session, current_user.id)
    return await room_service.list_classrooms(current_user.id, org_id)


@router.get("/{classroom_id}", response_model=Classroom)
async def get_classroom(
    classroom_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Classroom:
    org_id = await get_user_org_id(session, current_user.id)
    return await room_service.get_classroom(current_user.id, classroom_id, org_id)


@router.post("/", response_model=Classroom, status_code=201)
async def create_classroom(
    data: ClassroomCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Classroom:
    return await room_service.create_classroom(session, data, current_user.id)


@router.patch("/{classroom_id}", response_model=Classroom)
async def update_classroom(
    classroom_id: str,
    data: Classroom,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Classroom:
    return await room_service.update_classroom(session, classroom_id, data, current_user.id)


@router.delete("/{classroom_id}", status_code=204)
async def delete_classroom(
    classroom_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await room_service.delete_classroom(session, classroom_id, current_user.id)
