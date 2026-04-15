from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import (
    get_current_user,
    get_org_membership,
    require_platform_admin,
)
from app.database import get_session
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.enums import InviteStatus, OrganizationRole, UserRole
from app.models.organization import Organization
from app.models.organization_invite import OrganizationInvite
from app.models.organization_membership import OrganizationMembership
from app.models.user import User

router = APIRouter(tags=["organization-invites"])


# --- Schemas ---


class InviteCreate(PydanticBaseModel):
    email: str
    role: OrganizationRole = OrganizationRole.MEMBER


class InviteRead(PydanticBaseModel):
    id: str
    organization_id: str
    organization_name: str
    email: str
    role: OrganizationRole
    status: InviteStatus
    invited_by_user_id: str
    created_at: str


# --- Admin routes: manage invites for an org ---


@router.post(
    "/organizations/{org_id}/invites",
    response_model=InviteRead,
    status_code=201,
)
async def create_invite(
    org_id: str,
    data: InviteCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InviteRead:
    """Invite a user by email. Requires platform admin or org admin."""
    await _require_invite_admin(session, current_user, org_id)

    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")

    # Check for existing pending invite
    existing = await session.execute(
        select(OrganizationInvite).where(
            OrganizationInvite.organization_id == org_id,
            OrganizationInvite.email == data.email,
            OrganizationInvite.status == InviteStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("A pending invite already exists for this email")

    # Check if user is already a member
    user_result = await session.execute(
        select(User).where(User.email == data.email)
    )
    target_user = user_result.scalar_one_or_none()
    if target_user:
        existing_membership = await get_org_membership(session, target_user.id)
        if existing_membership is not None:
            raise ConflictError("This user is already a member of an organization")

    invite = OrganizationInvite(
        organization_id=org_id,
        email=data.email,
        role=data.role,
        invited_by_user_id=current_user.id,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    return _invite_to_read(invite, org.name)


@router.get(
    "/organizations/{org_id}/invites",
    response_model=list[InviteRead],
)
async def list_org_invites(
    org_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[InviteRead]:
    """List pending invites for an org. Requires platform admin or org admin."""
    await _require_invite_admin(session, current_user, org_id)

    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")

    result = await session.execute(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.organization_id == org_id,
            OrganizationInvite.status == InviteStatus.PENDING,
        )
        .order_by(OrganizationInvite.created_at.desc())  # type: ignore[union-attr]
    )
    return [_invite_to_read(inv, org.name) for inv in result.scalars().all()]


@router.delete("/organizations/{org_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(
    org_id: str,
    invite_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke a pending invite. Requires platform admin or org admin."""
    await _require_invite_admin(session, current_user, org_id)

    invite = await session.get(OrganizationInvite, invite_id)
    if invite is None or invite.organization_id != org_id:
        raise NotFoundError("Invite not found")
    if invite.status != InviteStatus.PENDING:
        raise ValidationError("Only pending invites can be revoked")

    await session.delete(invite)
    await session.commit()


# --- User-facing: view and respond to my invites ---


@router.get("/invites/mine", response_model=list[InviteRead])
async def list_my_invites(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[InviteRead]:
    """List pending invites for the current user (matched by email)."""
    result = await session.execute(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.email == current_user.email,
            OrganizationInvite.status == InviteStatus.PENDING,
        )
        .order_by(OrganizationInvite.created_at.desc())  # type: ignore[union-attr]
    )
    invites = result.scalars().all()

    reads: list[InviteRead] = []
    for inv in invites:
        org = await session.get(Organization, inv.organization_id)
        org_name = org.name if org else "Unknown"
        reads.append(_invite_to_read(inv, org_name))
    return reads


@router.post("/invites/{invite_id}/accept", response_model=InviteRead)
async def accept_invite(
    invite_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InviteRead:
    """Accept an invite. User must not already be in an organization."""
    invite = await _get_my_pending_invite(session, invite_id, current_user)

    # Check user is not already in an org
    existing = await get_org_membership(session, current_user.id)
    if existing is not None:
        raise ConflictError("You are already a member of an organization")

    # Create membership
    membership = OrganizationMembership(
        user_id=current_user.id,
        organization_id=invite.organization_id,
        role=invite.role,
    )
    session.add(membership)

    invite.status = InviteStatus.ACCEPTED
    session.add(invite)

    await session.commit()
    await session.refresh(invite)

    org = await session.get(Organization, invite.organization_id)
    org_name = org.name if org else "Unknown"
    return _invite_to_read(invite, org_name)


@router.post("/invites/{invite_id}/decline", response_model=InviteRead)
async def decline_invite(
    invite_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InviteRead:
    """Decline an invite."""
    invite = await _get_my_pending_invite(session, invite_id, current_user)

    invite.status = InviteStatus.DECLINED
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    org = await session.get(Organization, invite.organization_id)
    org_name = org.name if org else "Unknown"
    return _invite_to_read(invite, org_name)


# --- Helpers ---


async def _require_invite_admin(
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


async def _get_my_pending_invite(
    session: AsyncSession, invite_id: str, user: User
) -> OrganizationInvite:
    invite = await session.get(OrganizationInvite, invite_id)
    if invite is None or invite.email != user.email:
        raise NotFoundError("Invite not found")
    if invite.status != InviteStatus.PENDING:
        raise ValidationError("This invite is no longer pending")
    return invite


def _invite_to_read(invite: OrganizationInvite, org_name: str) -> InviteRead:
    return InviteRead(
        id=invite.id,
        organization_id=invite.organization_id,
        organization_name=org_name,
        email=invite.email,
        role=invite.role,
        status=invite.status,
        invited_by_user_id=invite.invited_by_user_id,
        created_at=invite.created_at.isoformat(),
    )
