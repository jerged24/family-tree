"""CRUD endpoints for persons."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Event, Person, Relationship
from backend.app.schemas import (
    EventRead,
    PersonCreate,
    PersonRead,
    PersonUpdate,
    RelationshipRead,
)

router = APIRouter(prefix="/persons", tags=["persons"])


def _get_or_404(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    return person


@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
def create_person(payload: PersonCreate, db: Session = Depends(get_db)) -> Person:
    person = Person(**payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.get("", response_model=list[PersonRead])
def list_persons(
    surname: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[Person]:
    stmt = select(Person).order_by(Person.id)
    if surname:
        stmt = stmt.where(Person.surname == surname)
    return list(db.scalars(stmt.offset(offset).limit(limit)))


@router.get("/{person_id}", response_model=PersonRead)
def get_person(person_id: int, db: Session = Depends(get_db)) -> Person:
    return _get_or_404(db, person_id)


@router.patch("/{person_id}", response_model=PersonRead)
def update_person(person_id: int, payload: PersonUpdate, db: Session = Depends(get_db)) -> Person:
    person = _get_or_404(db, person_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(person_id: int, db: Session = Depends(get_db)) -> None:
    person = _get_or_404(db, person_id)
    db.delete(person)  # cascades memberships & events
    db.commit()


@router.get("/{person_id}/events", response_model=list[EventRead])
def person_events(person_id: int, db: Session = Depends(get_db)) -> list[Event]:
    _get_or_404(db, person_id)
    return list(db.scalars(select(Event).where(Event.person_id == person_id)))


@router.get("/{person_id}/memberships", response_model=list[RelationshipRead])
def person_memberships(person_id: int, db: Session = Depends(get_db)) -> list[Relationship]:
    """The person's family memberships (which families, as PARTNER or CHILD)."""
    _get_or_404(db, person_id)
    return list(db.scalars(select(Relationship).where(Relationship.person_id == person_id)))
