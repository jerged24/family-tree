"""Endpoints for attaching media (photos/documents) to a person."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Media, Person
from backend.app.schemas import MediaCreate, MediaRead
from backend.app.storage import ALLOWED_IMAGE_TYPES, save_upload

router = APIRouter(tags=["media"])

# Bounded read so a huge upload can't exhaust memory.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/persons/{person_id}/media",
    response_model=MediaRead,
    status_code=status.HTTP_201_CREATED,
)
def add_media(person_id: int, payload: MediaCreate, db: Session = Depends(get_db)) -> Media:
    if db.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    if payload.is_primary:
        # Only one primary photo per person.
        for existing in db.scalars(select(Media).where(Media.person_id == person_id)):
            existing.is_primary = False
    item = Media(person_id=person_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/persons/{person_id}/media/upload",
    response_model=MediaRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    person_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db),
) -> Media:
    if db.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "Unsupported media type; images only")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 10 MB)")
    _, url = save_upload(data, file.content_type, file.filename)
    if is_primary:
        for existing in db.scalars(select(Media).where(Media.person_id == person_id)):
            existing.is_primary = False
    item = Media(
        person_id=person_id,
        url=url,
        caption=caption,
        mime_type=file.content_type,
        is_primary=is_primary,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/persons/{person_id}/media", response_model=list[MediaRead])
def list_media(person_id: int, db: Session = Depends(get_db)) -> list[Media]:
    if db.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    return list(db.scalars(select(Media).where(Media.person_id == person_id).order_by(Media.id)))


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(media_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(Media, media_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Media {media_id} not found")
    db.delete(item)
    db.commit()
