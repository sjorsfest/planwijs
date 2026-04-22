from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.book import Book
from app.models.enums import Level, SchoolYear
from app.models.user import User
from app.routes.school_config.route import _get_effective_config, _get_method_ids
from app.services import book as book_service

from .types import BookDetailResponse

router = APIRouter(prefix="/books", tags=["books"])


@router.get("/", response_model=list[Book])
async def list_books(
    method_id: Optional[str] = Query(default=None),
    subject_id: Optional[str] = Query(default=None),
    level: Optional[Level] = Query(default=None),
    school_year: Optional[SchoolYear] = Query(default=None),
    for_school_config: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Book]:
    books = await book_service.list_books(
        method_id=method_id,
        subject_id=subject_id,
        level=level,
        school_year=school_year,
    )
    if for_school_config:
        config, _ = await _get_effective_config(session, current_user.id)
        if config:
            selected = set(await _get_method_ids(session, config.id))
            books = [b for b in books if b.method_id in selected]
        else:
            books = []
    return books


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(book_id: str) -> BookDetailResponse:
    return await book_service.get_book_detail(book_id)


@router.post("/", response_model=Book, status_code=201)
async def create_book(
    data: Book, session: AsyncSession = Depends(get_session)
) -> Book:
    return await book_service.create_book(session, data)


@router.patch("/{book_id}", response_model=Book)
async def update_book(
    book_id: str, data: Book, session: AsyncSession = Depends(get_session)
) -> Book:
    return await book_service.update_book(session, book_id, data)


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await book_service.delete_book(session, book_id)
