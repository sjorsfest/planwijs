from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.database import get_session
from app.models.enums import Level, SchoolType
from app.models.organization_membership import OrganizationMembership
from app.models.school_config import SchoolConfig
from app.models.school_config_method import SchoolConfigMethod
from app.models.user import User

router = APIRouter(prefix="/school-config", tags=["school-config"])


# --- Request / Response schemas ---


class SchoolConfigUpdate(PydanticBaseModel):
    default_lesson_duration_minutes: int | None = Field(default=None, ge=1)
    levels: list[Level] | None = None
    school_type: SchoolType | None = None
    context_notes: str | None = None
    method_ids: list[str] | None = None


class SchoolConfigResponse(PydanticBaseModel):
    id: str
    organization_id: str | None = None
    user_id: str | None = None
    default_lesson_duration_minutes: int
    levels: list[Level]
    school_type: SchoolType | None = None
    context_notes: str | None = None
    method_ids: list[str] = []


# --- Helpers ---


async def _get_effective_config(
    session: AsyncSession, user_id: str
) -> tuple[SchoolConfig | None, str | None]:
    """Return (config, org_id) for the current user."""
    result = await session.execute(
        select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user_id
        )
    )
    org_id = result.scalar_one_or_none()

    if org_id:
        cfg_result = await session.execute(
            select(SchoolConfig).where(SchoolConfig.organization_id == org_id)
        )
        return cfg_result.scalar_one_or_none(), org_id

    cfg_result = await session.execute(
        select(SchoolConfig).where(SchoolConfig.user_id == user_id)
    )
    return cfg_result.scalar_one_or_none(), None


async def _get_method_ids(session: AsyncSession, config_id: str) -> list[str]:
    result = await session.execute(
        select(SchoolConfigMethod.method_id).where(
            SchoolConfigMethod.school_config_id == config_id
        )
    )
    return list(result.scalars().all())


async def _sync_method_ids(
    session: AsyncSession, config_id: str, method_ids: list[str]
) -> None:
    """Replace the current set of method links with the given method_ids."""
    result = await session.execute(
        select(SchoolConfigMethod).where(
            SchoolConfigMethod.school_config_id == config_id
        )
    )
    existing = {link.method_id: link for link in result.scalars().all()}

    desired = set(method_ids)
    # Remove links no longer wanted
    for method_id, link in existing.items():
        if method_id not in desired:
            await session.delete(link)
    # Add new links
    for method_id in desired:
        if method_id not in existing:
            session.add(SchoolConfigMethod(
                school_config_id=config_id,
                method_id=method_id,
            ))


# --- Routes ---


@router.get("/", response_model=SchoolConfigResponse | None)
async def get_school_config(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SchoolConfigResponse | None:
    config, _ = await _get_effective_config(session, current_user.id)
    if config is None:
        return None
    method_ids = await _get_method_ids(session, config.id)
    return _to_response(config, method_ids=method_ids)


@router.put("/", response_model=SchoolConfigResponse)
async def upsert_school_config(
    data: SchoolConfigUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SchoolConfigResponse:
    config, org_id = await _get_effective_config(session, current_user.id)

    if config is None:
        config = SchoolConfig(
            organization_id=org_id,
            user_id=None if org_id else current_user.id,
        )

    if data.default_lesson_duration_minutes is not None:
        config.default_lesson_duration_minutes = data.default_lesson_duration_minutes
    if data.levels is not None:
        config.levels = data.levels  # type: ignore[assignment]
    if data.school_type is not None:
        config.school_type = data.school_type
    if data.context_notes is not None:
        config.context_notes = data.context_notes

    session.add(config)
    await session.flush()

    if data.method_ids is not None:
        await _sync_method_ids(session, config.id, data.method_ids)

    await session.commit()
    await session.refresh(config)
    method_ids = await _get_method_ids(session, config.id)
    return _to_response(config, method_ids=method_ids)


def _to_response(
    config: SchoolConfig, *, method_ids: list[str] | None = None
) -> SchoolConfigResponse:
    return SchoolConfigResponse(
        id=config.id,
        organization_id=config.organization_id,
        user_id=config.user_id,
        default_lesson_duration_minutes=config.default_lesson_duration_minutes,
        levels=config.levels,
        school_type=config.school_type,
        context_notes=config.context_notes,
        method_ids=method_ids or [],
    )
