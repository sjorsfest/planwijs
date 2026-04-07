import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=User)
async def get_current_user_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=User)
async def update_current_user(
    data: User,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    update = data.model_dump(exclude_unset=True, exclude={"id", "email", "google_id"})
    current_user.sqlmodel_update(update)
    await session.commit()
    await session.refresh(current_user)
    logger.info("Updated user: id=%s fields=%s", current_user.id, list(update.keys()))
    return current_user
