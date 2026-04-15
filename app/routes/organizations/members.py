from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import (
    get_current_user,
    get_org_membership,
    require_org_admin,
    require_org_membership,
    require_platform_admin,
)
from app.database import get_session
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.enums import OrganizationRole, UserRole
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.user import User

router = APIRouter(tags=["organization-members"])


# --- Schemas ---


class MemberRead(PydanticBaseModel):
    user_id: str
    user_name: str
    user_email: str
    role: OrganizationRole
    joined_at: str


class MemberAdd(PydanticBaseModel):
    user_id: str
    role: OrganizationRole = OrganizationRole.MEMBER


class MemberRoleUpdate(PydanticBaseModel):
    role: OrganizationRole


# --- Routes ---


@router.get("/organizations/me/members", response_model=list[MemberRead])
async def list_my_org_members(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MemberRead]:
    """List members of the current user's organization."""
    membership = await require_org_membership(session, current_user.id)

    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == membership.organization_id
        )
    )
    memberships = result.scalars().all()
    return [await _membership_to_read(session, m) for m in memberships]


@router.post(
    "/organizations/{org_id}/members",
    response_model=MemberRead,
    status_code=201,
)
async def add_member(
    org_id: str,
    data: MemberAdd,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> MemberRead:
    """Add a user to an organization directly (platform admin only)."""
    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")

    user = await session.get(User, data.user_id)
    if user is None:
        raise NotFoundError("User not found")

    existing = await get_org_membership(session, data.user_id)
    if existing is not None:
        raise ConflictError("User is already a member of an organization")

    membership = OrganizationMembership(
        user_id=data.user_id,
        organization_id=org_id,
        role=data.role,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)

    return await _membership_to_read(session, membership)


@router.patch(
    "/organizations/{org_id}/members/{user_id}",
    response_model=MemberRead,
)
async def update_member_role(
    org_id: str,
    user_id: str,
    data: MemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemberRead:
    """Change a member's role. Requires platform admin or org admin."""
    await _require_admin_for_org(session, current_user, org_id)

    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Member not found in this organization")

    membership.role = data.role
    session.add(membership)
    await session.commit()
    await session.refresh(membership)

    return await _membership_to_read(session, membership)


@router.delete("/organizations/{org_id}/members/{user_id}", status_code=204)
async def remove_member(
    org_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a member. Platform admin, org admin, or self (leave)."""
    is_self = current_user.id == user_id
    if not is_self:
        await _require_admin_for_org(session, current_user, org_id)

    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Member not found in this organization")

    await session.delete(membership)
    await session.commit()


# --- Helpers ---


async def _require_admin_for_org(
    session: AsyncSession, user: User, org_id: str
) -> None:
    """Check that user is platform admin or org admin for the given org."""
    if user.user_role == UserRole.ADMIN:
        return

    membership = await get_org_membership(session, user.id)
    if (
        membership is None
        or membership.organization_id != org_id
        or membership.role != OrganizationRole.ADMIN
    ):
        raise ForbiddenError("Admin access required")


async def _membership_to_read(
    session: AsyncSession, membership: OrganizationMembership
) -> MemberRead:
    user = await session.get(User, membership.user_id)
    assert user is not None
    return MemberRead(
        user_id=membership.user_id,
        user_name=user.name,
        user_email=user.email,
        role=membership.role,
        joined_at=membership.created_at.isoformat(),
    )
