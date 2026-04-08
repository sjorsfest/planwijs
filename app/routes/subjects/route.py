from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.enums import SubjectCategory
from app.models.subject import Subject
from app.services import subject as subject_service

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/", response_model=list[Subject])
async def list_subjects(
    category: Optional[SubjectCategory] = Query(default=None),
) -> list[Subject]:
    return await subject_service.list_subjects(category=category)


@router.get("/{subject_id}", response_model=Subject)
async def get_subject(subject_id: str) -> Subject:
    return await subject_service.get_subject(subject_id)


@router.post("/", response_model=Subject, status_code=201)
async def create_subject(
    data: Subject, session: AsyncSession = Depends(get_session)
) -> Subject:
    return await subject_service.create_subject(session, data)


@router.patch("/{subject_id}", response_model=Subject)
async def update_subject(
    subject_id: str, data: Subject, session: AsyncSession = Depends(get_session)
) -> Subject:
    return await subject_service.update_subject(session, subject_id, data)


@router.delete("/{subject_id}", status_code=204)
async def delete_subject(
    subject_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await subject_service.delete_subject(session, subject_id)
