"""CRUD endpoints for families and their member relationships."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Family, Person, Relationship
from backend.app.schemas import (
    FamilyCreate,
    FamilyRead,
    FamilyUpdate,
    RelationshipCreate,
    RelationshipRead,
)

router = APIRouter(prefix="/families", tags=["families"])


def _get_or_404(db: Session, family_id: int) -> Family:
    family = db.get(Family, family_id)
    if family is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Family {family_id} not found")
    return family


@router.post("", response_model=FamilyRead, status_code=status.HTTP_201_CREATED)
def create_family(payload: FamilyCreate, db: Session = Depends(get_db)) -> Family:
    family = Family(**payload.model_dump())
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


@router.get("", response_model=list[FamilyRead])
def list_families(db: Session = Depends(get_db)) -> list[Family]:
    return list(db.scalars(select(Family).order_by(Family.id)))


@router.get("/{family_id}", response_model=FamilyRead)
def get_family(family_id: int, db: Session = Depends(get_db)) -> Family:
    return _get_or_404(db, family_id)


@router.patch("/{family_id}", response_model=FamilyRead)
def update_family(family_id: int, payload: FamilyUpdate, db: Session = Depends(get_db)) -> Family:
    family = _get_or_404(db, family_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(family, field, value)
    db.commit()
    db.refresh(family)
    return family


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family(family_id: int, db: Session = Depends(get_db)) -> None:
    family = _get_or_404(db, family_id)
    db.delete(family)  # cascades memberships & family events
    db.commit()


@router.get("/{family_id}/members", response_model=list[RelationshipRead])
def family_members(family_id: int, db: Session = Depends(get_db)) -> list[Relationship]:
    _get_or_404(db, family_id)
    return list(db.scalars(select(Relationship).where(Relationship.family_id == family_id)))


@router.post(
    "/{family_id}/members",
    response_model=RelationshipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    family_id: int, payload: RelationshipCreate, db: Session = Depends(get_db)
) -> Relationship:
    """Attach a person to this family as a PARTNER or CHILD."""
    if payload.family_id != family_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "family_id in body must match URL")
    _get_or_404(db, family_id)
    if db.get(Person, payload.person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {payload.person_id} not found")

    rel = Relationship(**payload.model_dump())
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


@router.delete("/members/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(relationship_id: int, db: Session = Depends(get_db)) -> None:
    rel = db.get(Relationship, relationship_id)
    if rel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Relationship {relationship_id} not found")
    db.delete(rel)
    db.commit()
