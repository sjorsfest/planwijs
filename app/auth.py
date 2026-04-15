import logging

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.exceptions import AuthenticationError, ForbiddenError
from app.models.enums import OrganizationRole, UserRole
from app.models.organization_membership import OrganizationMembership
from app.models.user import User

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise AuthenticationError("Invalid token")
    except JWTError:
        raise AuthenticationError("Invalid token")

    user = await session.get(User, user_id)
    if user is None:
        raise AuthenticationError("User not found")
    return user


async def require_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency: raises 403 if the user is not a platform admin."""
    if current_user.user_role != UserRole.ADMIN:
        raise ForbiddenError("Platform admin access required")
    return current_user


async def get_org_membership(
    session: AsyncSession,
    user_id: str,
) -> OrganizationMembership | None:
    """Return the user's org membership, or None."""
    result = await session.execute(
        select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def require_org_membership(
    session: AsyncSession,
    user_id: str,
) -> OrganizationMembership:
    """Return the user's org membership, or raise 403."""
    membership = await get_org_membership(session, user_id)
    if membership is None:
        raise ForbiddenError("You are not a member of any organization")
    return membership


async def require_org_admin(
    session: AsyncSession,
    user_id: str,
) -> OrganizationMembership:
    """Return the user's org membership if they are an org admin, or raise 403."""
    membership = await require_org_membership(session, user_id)
    if membership.role != OrganizationRole.ADMIN:
        raise ForbiddenError("Organization admin access required")
    return membership
