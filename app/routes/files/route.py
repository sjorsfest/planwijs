from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.database import get_session
from app.exceptions import NotFoundError
from app.integrations.r2_store import R2Store, get_private_store
from app.models.file import File, FileBucket, FileStatus
from app.models.user import User
from app.services.visibility import get_user_org_id, visible_filter

router = APIRouter(prefix="/files", tags=["files"])


# --- Request / Response schemas ---


class FileUploadRequest(PydanticBaseModel):
    filename: str
    content_type: str
    size_bytes: int
    folder_id: Optional[str] = None
    lesplan_request_id: Optional[str] = None
    class_id: Optional[str] = None


class FileUploadResponse(PydanticBaseModel):
    file_id: str
    upload_url: str
    upload_method: str
    upload_headers: dict[str, str]
    object_key: str


class FileMoveRequest(PydanticBaseModel):
    folder_id: Optional[str] = None


class FileUpdateRequest(PydanticBaseModel):
    class_id: Optional[str] = None


class FileRead(PydanticBaseModel):
    id: str
    name: str
    content_type: str
    size_bytes: int
    bucket: FileBucket
    status: FileStatus
    folder_id: Optional[str]
    lesplan_request_id: Optional[str]
    class_id: Optional[str]
    has_extracted_text: bool
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
        folder_id=body.folder_id,
        lesplan_request_id=body.lesplan_request_id,
        class_id=body.class_id,
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
    folder_id: Optional[str] = None,
    lesplan_request_id: Optional[str] = None,
    class_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FileRead]:
    """List files visible to the current user (personal + org-shared)."""
    org_id = await get_user_org_id(session, current_user.id)
    stmt = select(File).where(
        visible_filter(File, current_user.id, org_id),
        File.status == FileStatus.UPLOADED,
    )
    if folder_id is not None:
        stmt = stmt.where(File.folder_id == folder_id)
    if lesplan_request_id:
        stmt = stmt.where(File.lesplan_request_id == lesplan_request_id)
    if class_id:
        stmt = stmt.where(File.class_id == class_id)
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
    org_id = await get_user_org_id(session, current_user.id)
    stmt = select(File).where(File.id == file_id, visible_filter(File, current_user.id, org_id))
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    store = _store_for_bucket(file.bucket)
    return _file_to_read(file, store)


@router.post("/{file_id}/confirm-upload", response_model=FileRead)
async def confirm_upload(
    file_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileRead:
    """Confirm that the file was uploaded to R2. Sets status to UPLOADED and triggers text extraction."""
    from app.services.file_extraction import extract_text

    stmt = select(File).where(File.id == file_id, File.user_id == current_user.id)
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    file.status = FileStatus.UPLOADED
    store = _store_for_bucket(file.bucket)
    extracted = await extract_text(store, file.object_key, file.content_type)
    if extracted is not None:
        file.extracted_text = extracted

    session.add(file)
    await session.commit()
    await session.refresh(file)

    return _file_to_read(file, store)


@router.post("/{file_id}/upload-failed", status_code=204)
async def mark_upload_failed(
    file_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Mark a file upload as failed. Cleans up the file record."""
    stmt = select(File).where(File.id == file_id, File.user_id == current_user.id)
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    await session.delete(file)
    await session.commit()


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


@router.patch("/{file_id}/move", response_model=FileRead)
async def move_file(
    file_id: str,
    body: FileMoveRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileRead:
    """Move a file to a different folder (or root if folder_id is null)."""
    stmt = select(File).where(File.id == file_id, File.user_id == current_user.id)
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    if body.folder_id:
        from app.models.folder import Folder
        folder_stmt = select(Folder).where(
            Folder.id == body.folder_id, Folder.user_id == current_user.id
        )
        folder_result = await session.execute(folder_stmt)
        if not folder_result.scalar_one_or_none():
            raise NotFoundError("Folder not found")

    file.folder_id = body.folder_id
    session.add(file)
    await session.commit()
    await session.refresh(file)

    store = _store_for_bucket(file.bucket)
    return _file_to_read(file, store)


@router.patch("/{file_id}", response_model=FileRead)
async def update_file(
    file_id: str,
    body: FileUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileRead:
    """Update file metadata (e.g. link/unlink a class)."""
    stmt = select(File).where(File.id == file_id, File.user_id == current_user.id)
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()
    if not file:
        raise NotFoundError("File not found")

    if body.class_id is not None:
        from app.models.school_class import Class
        class_stmt = select(Class).where(
            Class.id == body.class_id, Class.user_id == current_user.id
        )
        class_result = await session.execute(class_stmt)
        if not class_result.scalar_one_or_none():
            raise NotFoundError("Class not found")

    file.class_id = body.class_id
    session.add(file)
    await session.commit()
    await session.refresh(file)

    store = _store_for_bucket(file.bucket)
    return _file_to_read(file, store)


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
        status=file.status,
        folder_id=file.folder_id,
        lesplan_request_id=file.lesplan_request_id,
        class_id=file.class_id,
        has_extracted_text=bool(file.extracted_text),
        created_at=file.created_at.isoformat(),
        url=store.get_access_url(file.object_key),
    )
