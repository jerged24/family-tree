"""Endpoints for attaching media (photos/documents) to a person."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Media, Person
from backend.app.schemas import MediaCreate, MediaRead

router = APIRouter(tags=["media"])


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
