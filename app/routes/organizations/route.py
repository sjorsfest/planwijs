import re
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user, require_platform_admin
from app.database import get_session
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.enums import OrganizationRole
from app.models.user import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


# --- Request / Response schemas ---


class OrganizationCreate(PydanticBaseModel):
    name: str
    slug: str


class OrganizationUpdate(PydanticBaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None


class OrganizationRead(PydanticBaseModel):
    id: str
    name: str
    slug: str
    created_at: str
    updated_at: str
    member_count: int


_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_slug(slug: str) -> None:
    if not _SLUG_PATTERN.match(slug):
        raise ValidationError(
            "Slug must be lowercase alphanumeric with hyphens (e.g. 'my-school')"
        )


# --- Routes (Platform Admin only) ---


@router.post("/", response_model=OrganizationRead, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    _validate_slug(data.slug)

    existing = await session.execute(
        select(Organization).where(Organization.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise ConflictError("An organization with this slug already exists")

    org = Organization(name=data.name, slug=data.slug)
    session.add(org)
    await session.flush()
    await session.commit()
    await session.refresh(org)

    return _org_to_read(org, member_count=0)


@router.get("/", response_model=list[OrganizationRead])
async def list_organizations(
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> list[OrganizationRead]:
    result = await session.execute(
        select(Organization).order_by(Organization.name)
    )
    orgs = result.scalars().all()

    reads: list[OrganizationRead] = []
    for org in orgs:
        count_result = await session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org.id
            )
        )
        member_count = len(count_result.scalars().all())
        reads.append(_org_to_read(org, member_count=member_count))
    return reads


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_organization(
    org_id: str,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    org = await _get_org_or_404(session, org_id)
    count_result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id
        )
    )
    member_count = len(count_result.scalars().all())
    return _org_to_read(org, member_count=member_count)


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    org = await _get_org_or_404(session, org_id)

    if data.name is not None:
        org.name = data.name
    if data.slug is not None:
        _validate_slug(data.slug)
        existing = await session.execute(
            select(Organization).where(
                Organization.slug == data.slug,
                Organization.id != org.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("An organization with this slug already exists")
        org.slug = data.slug

    session.add(org)
    await session.commit()
    await session.refresh(org)

    count_result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id
        )
    )
    member_count = len(count_result.scalars().all())
    return _org_to_read(org, member_count=member_count)


@router.delete("/{org_id}", status_code=204)
async def delete_organization(
    org_id: str,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    org = await _get_org_or_404(session, org_id)
    await session.delete(org)
    await session.commit()


# --- User-facing: get my organization ---


@router.get("/me/organization", response_model=OrganizationRead | None)
async def get_my_organization(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead | None:
    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == current_user.id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return None

    org = await session.get(Organization, membership.organization_id)
    if org is None:
        return None

    count_result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id
        )
    )
    member_count = len(count_result.scalars().all())
    return _org_to_read(org, member_count=member_count)


# --- Helpers ---


async def _get_org_or_404(session: AsyncSession, org_id: str) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org


def _org_to_read(org: Organization, member_count: int) -> OrganizationRead:
    return OrganizationRead(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at.isoformat(),
        updated_at=org.updated_at.isoformat(),
        member_count=member_count,
    )
