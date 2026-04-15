from typing import Any

from sqlalchemy import ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.organization_membership import OrganizationMembership


async def get_user_org_id(session: AsyncSession, user_id: str) -> str | None:
    """Return the user's organization_id, or None if not in an org."""
    result = await session.execute(
        select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


def visible_filter(model_class: Any, user_id: str, org_id: str | None) -> ColumnElement[bool]:
    """WHERE clause: user's own resources OR shared via their org."""
    if org_id is None:
        return model_class.user_id == user_id  # type: ignore[return-value]
    return or_(
        model_class.user_id == user_id,
        model_class.organization_id == org_id,
    )
