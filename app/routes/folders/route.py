from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_user
from app.database import get_session
from app.exceptions import NotFoundError, ValidationError
from app.integrations.r2_store import R2Store, get_private_store
from app.models.file import File, FileBucket, FileStatus
from app.models.folder import Folder
from app.models.user import User
from app.services.visibility import get_user_org_id, visible_filter

router = APIRouter(prefix="/folders", tags=["folders"])


# --- Request / Response schemas ---


class FolderCreate(PydanticBaseModel):
    name: str
    parent_id: Optional[str] = None


class FolderUpdate(PydanticBaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None


class FolderFileRead(PydanticBaseModel):
    id: str
    name: str
    content_type: str
    size_bytes: int
    bucket: FileBucket
    folder_id: Optional[str]
    lesplan_request_id: Optional[str]
    has_extracted_text: bool
    created_at: str
    url: str


class FolderRead(PydanticBaseModel):
    id: str
    name: str
    parent_id: Optional[str]
    created_at: str
    updated_at: str
    children: list["FolderRead"]
    files: list[FolderFileRead]


# --- Routes ---


@router.post("/", response_model=FolderRead, status_code=201)
async def create_folder(
    body: FolderCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FolderRead:
    if body.parent_id:
        await _get_owned_folder(session, current_user.id, body.parent_id)

    folder = Folder(
        user_id=current_user.id,
        name=body.name,
        parent_id=body.parent_id,
    )
    session.add(folder)
    await session.commit()
    await session.refresh(folder)

    return _folder_to_read(folder, children=[], files=[])


@router.get("/", response_model=list[FolderRead])
async def list_root_folders(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FolderRead]:
    """List root-level folders (no parent) with their immediate children and files."""
    org_id = await get_user_org_id(session, current_user.id)
    return await _get_folder_tree(session, current_user.id, org_id, parent_id=None)


@router.get("/{folder_id}", response_model=FolderRead)
async def get_folder(
    folder_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FolderRead:
    """Get a folder with its immediate children and files."""
    org_id = await get_user_org_id(session, current_user.id)
    folder = await _get_visible_folder(session, current_user.id, org_id, folder_id)
    children = await _get_folder_tree(session, current_user.id, org_id, parent_id=folder.id)
    files = await _get_folder_files(session, current_user.id, org_id, folder.id)
    return _folder_to_read(folder, children=children, files=files)


@router.patch("/{folder_id}", response_model=FolderRead)
async def update_folder(
    folder_id: str,
    body: FolderUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FolderRead:
    folder = await _get_owned_folder(session, current_user.id, folder_id)

    if body.parent_id is not None:
        if body.parent_id == folder.id:
            raise ValidationError("A folder cannot be its own parent")
        if body.parent_id:
            await _get_owned_folder(session, current_user.id, body.parent_id)
            await _check_no_circular_ref(session, current_user.id, folder.id, body.parent_id)
        folder.parent_id = body.parent_id

    if body.name is not None:
        folder.name = body.name

    session.add(folder)
    await session.commit()
    await session.refresh(folder)

    org_id = await get_user_org_id(session, current_user.id)
    children = await _get_folder_tree(session, current_user.id, org_id, parent_id=folder.id)
    files = await _get_folder_files(session, current_user.id, org_id, folder.id)
    return _folder_to_read(folder, children=children, files=files)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a folder. Moves contained files and subfolders to the parent (or root)."""
    folder = await _get_owned_folder(session, current_user.id, folder_id)

    # Move child folders to parent
    child_folders_stmt = select(Folder).where(
        Folder.user_id == current_user.id,
        Folder.parent_id == folder.id,
    )
    result = await session.execute(child_folders_stmt)
    for child in result.scalars().all():
        child.parent_id = folder.parent_id
        session.add(child)

    # Move files to parent folder
    files_stmt = select(File).where(
        File.user_id == current_user.id,
        File.folder_id == folder.id,
    )
    result = await session.execute(files_stmt)
    for file in result.scalars().all():
        file.folder_id = folder.parent_id
        session.add(file)

    await session.delete(folder)
    await session.commit()


# --- Helpers ---


async def _get_owned_folder(
    session: AsyncSession, user_id: str, folder_id: str
) -> Folder:
    """Get a folder that the user owns (for mutations)."""
    stmt = select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
    result = await session.execute(stmt)
    folder = result.scalar_one_or_none()
    if not folder:
        raise NotFoundError("Folder not found")
    return folder


async def _get_visible_folder(
    session: AsyncSession, user_id: str, org_id: str | None, folder_id: str
) -> Folder:
    """Get a folder visible to the user (own or org-shared)."""
    stmt = select(Folder).where(
        Folder.id == folder_id,
        visible_filter(Folder, user_id, org_id),
    )
    result = await session.execute(stmt)
    folder = result.scalar_one_or_none()
    if not folder:
        raise NotFoundError("Folder not found")
    return folder


async def _get_folder_tree(
    session: AsyncSession, user_id: str, org_id: str | None, parent_id: str | None
) -> list[FolderRead]:
    stmt = select(Folder).where(
        visible_filter(Folder, user_id, org_id),
        Folder.parent_id == parent_id,
    ).order_by(Folder.name)
    result = await session.execute(stmt)
    folders = result.scalars().all()

    items: list[FolderRead] = []
    for folder in folders:
        children = await _get_folder_tree(session, user_id, org_id, parent_id=folder.id)
        files = await _get_folder_files(session, user_id, org_id, folder.id)
        items.append(_folder_to_read(folder, children=children, files=files))
    return items


async def _get_folder_files(
    session: AsyncSession, user_id: str, org_id: str | None, folder_id: str
) -> list[FolderFileRead]:
    stmt = select(File).where(
        visible_filter(File, user_id, org_id),
        File.folder_id == folder_id,
        File.status == FileStatus.UPLOADED,
    ).order_by(File.name)
    result = await session.execute(stmt)
    files = result.scalars().all()

    store = get_private_store()
    return [_file_to_folder_read(f, store) for f in files]


async def _check_no_circular_ref(
    session: AsyncSession, user_id: str, folder_id: str, new_parent_id: str
) -> None:
    """Walk up from new_parent_id to ensure folder_id is not an ancestor."""
    current_id: str | None = new_parent_id
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            break
        visited.add(current_id)
        if current_id == folder_id:
            raise ValidationError("Moving this folder would create a circular reference")
        parent = await _get_owned_folder(session, user_id, current_id)
        current_id = parent.parent_id


def _folder_to_read(
    folder: Folder,
    children: list[FolderRead],
    files: list[FolderFileRead],
) -> FolderRead:
    return FolderRead(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        created_at=folder.created_at.isoformat(),
        updated_at=folder.updated_at.isoformat(),
        children=children,
        files=files,
    )


def _file_to_folder_read(file: File, store: R2Store) -> FolderFileRead:
    return FolderFileRead(
        id=file.id,
        name=file.name,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        bucket=file.bucket,
        folder_id=file.folder_id,
        lesplan_request_id=file.lesplan_request_id,
        has_extracted_text=bool(file.extracted_text),
        created_at=file.created_at.isoformat(),
        url=store.get_access_url(file.object_key),
    )
