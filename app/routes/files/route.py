from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.database import get_session
from app.exceptions import NotFoundError
from app.integrations.r2_store import R2Store, get_private_store
from app.models.file import File, FileBucket
from app.models.user import User

router = APIRouter(prefix="/files", tags=["files"])


# --- Request / Response schemas ---


class FileUploadRequest(PydanticBaseModel):
    filename: str
    content_type: str
    size_bytes: int
    lesplan_request_id: Optional[str] = None


class FileUploadResponse(PydanticBaseModel):
    file_id: str
    upload_url: str
    upload_method: str
    upload_headers: dict[str, str]
    object_key: str


class FileRead(PydanticBaseModel):
    id: str
    name: str
    content_type: str
    size_bytes: int
    bucket: FileBucket
    lesplan_request_id: Optional[str]
    created_at: str
    url: str


# --- Routes ---


@router.post("/upload-url", response_model=FileUploadResponse, status_code=201)
async def create_upload_url(
    body: FileUploadRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileUploadResponse:
    """Request a signed upload URL. Creates a File record in pending state."""
    store = get_private_store()
    prefix = f"users/{current_user.id}/files"
    object_key = store.build_object_key(prefix=prefix, filename=body.filename)

    signed = store.create_signed_upload_url(
        object_key=object_key,
        content_type=body.content_type,
    )

    file = File(
        user_id=current_user.id,
        name=body.filename,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        bucket=FileBucket.PRIVATE,
        object_key=object_key,
        lesplan_request_id=body.lesplan_request_id,
    )
    session.add(file)
    await session.commit()
    await session.refresh(file)

    return FileUploadResponse(
        file_id=file.id,
        upload_url=signed["url"],
        upload_method=signed["method"],
        upload_headers=signed["headers"],
        object_key=object_key,
    )


@router.get("/", response_model=list[FileRead])
async def list_files(
    lesplan_request_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FileRead]:
    """List files for the current user, optionally filtered by lesplan request."""
    stmt = select(File).where(File.user_id == current_user.id)
    if lesplan_request_id:
        stmt = stmt.where(File.lesplan_request_id == lesplan_request_id)
    stmt = stmt.order_by(File.created_at.desc())  # type: ignore[union-attr]

    result = await session.execute(stmt)
    files = result.scalars().all()

    store = get_private_store()
    return [_file_to_read(f, store) for f in files]


@router.get("/{file_id}", response_model=FileRead)
async def get_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileRead:
    """Get a single file with a fresh access URL."""
    stmt = select(File).where(File.id == file_id, File.user_id == current_user.id)
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    store = _store_for_bucket(file.bucket)
    return _file_to_read(file, store)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a file record and its object from storage."""
    stmt = select(File).where(File.id == file_id, File.user_id == current_user.id)
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    store = _store_for_bucket(file.bucket)
    store.delete_object(file.object_key)

    await session.delete(file)
    await session.commit()


# --- Helpers ---


def _store_for_bucket(bucket: FileBucket) -> R2Store:
    if bucket == FileBucket.PRIVATE:
        return get_private_store()
    from app.integrations.r2_store import get_public_store
    return get_public_store()


def _file_to_read(file: File, store: R2Store) -> FileRead:
    return FileRead(
        id=file.id,
        name=file.name,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        bucket=file.bucket,
        lesplan_request_id=file.lesplan_request_id,
        created_at=file.created_at.isoformat(),
        url=store.get_access_url(file.object_key),
    )
