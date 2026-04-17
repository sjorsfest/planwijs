from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.database import get_session
from app.models.subject import Subject as SubjectModel
from app.models.user import User
from app.models.user_subject import UserSubject
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


# --- User Subjects ---


class SubjectResponse(PydanticBaseModel):
    id: str
    slug: str
    name: str
    category: str


class SetUserSubjectsRequest(PydanticBaseModel):
    subject_ids: list[str]


@router.get("/me/subjects", response_model=list[SubjectResponse])
async def get_my_subjects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SubjectResponse]:
    result = await session.execute(
        select(SubjectModel)
        .join(UserSubject, UserSubject.subject_id == SubjectModel.id)
        .where(UserSubject.user_id == current_user.id)
        .order_by(SubjectModel.name)
    )
    subjects = result.scalars().all()
    return [
        SubjectResponse(id=s.id, slug=s.slug, name=s.name, category=s.category.value)
        for s in subjects
    ]


@router.put("/me/subjects", response_model=list[SubjectResponse])
async def set_my_subjects(
    data: SetUserSubjectsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SubjectResponse]:
    # Remove existing
    existing = await session.execute(
        select(UserSubject).where(UserSubject.user_id == current_user.id)
    )
    for us in existing.scalars().all():
        await session.delete(us)
    await session.flush()

    # Add new
    for subject_id in data.subject_ids:
        session.add(UserSubject(user_id=current_user.id, subject_id=subject_id))

    await session.commit()

    # Return updated list
    result = await session.execute(
        select(SubjectModel)
        .join(UserSubject, UserSubject.subject_id == SubjectModel.id)
        .where(UserSubject.user_id == current_user.id)
        .order_by(SubjectModel.name)
    )
    subjects = result.scalars().all()
    return [
        SubjectResponse(id=s.id, slug=s.slug, name=s.name, category=s.category.value)
        for s in subjects
    ]
