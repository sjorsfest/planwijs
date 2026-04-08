from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.user import User
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.patch("/me", response_model=User)
async def update_current_user(
    data: User,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    return await user_service.update_user(session, current_user, data)
