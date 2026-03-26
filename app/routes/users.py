import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session, run_read_with_retry
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[User])
async def list_users():
    async def operation(session: AsyncSession) -> list[User]:
        result = await session.execute(select(User))
        users = result.scalars().all()
        logger.debug("Listed %d users", len(users))
        return users

    return await run_read_with_retry(operation)


@router.get("/{user_id}", response_model=User)
async def get_user(user_id: str):
    async def operation(session: AsyncSession) -> User:
        user = await session.get(User, user_id)
        if not user:
            logger.warning("User not found: id=%s", user_id)
            raise HTTPException(status_code=404, detail="User not found")
        logger.debug("Fetched user: id=%s", user_id)
        return user

    return await run_read_with_retry(operation)


@router.post("/", response_model=User, status_code=201)
async def create_user(user: User, session: AsyncSession = Depends(get_session)):
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Created user: id=%s email=%s", user.id, user.email)
    return user


@router.patch("/{user_id}", response_model=User)
async def update_user(user_id: str, data: User, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        logger.warning("Update failed, user not found: id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    update = data.model_dump(exclude_unset=True, exclude={"id"})
    user.sqlmodel_update(update)
    await session.commit()
    await session.refresh(user)
    logger.info("Updated user: id=%s fields=%s", user_id, list(update.keys()))
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        logger.warning("Delete failed, user not found: id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
    logger.info("Deleted user: id=%s", user_id)
