import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)


async def update_user(session: AsyncSession, user: User, data: User) -> User:
    update = data.model_dump(exclude_unset=True, exclude={"id", "email", "google_id"})
    user.sqlmodel_update(update)
    await session.commit()
    await session.refresh(user)
    logger.info("Updated user: id=%s fields=%s", user.id, list(update.keys()))
    return user
