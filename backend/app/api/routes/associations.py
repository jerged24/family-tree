"""Endpoints for person→person associations (godparents and similar)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Association, Person
from backend.app.schemas import AssociationCreate, AssociationRead

router = APIRouter(tags=["associations"])


@router.post(
    "/persons/{person_id}/associations",
    response_model=AssociationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_association(
    person_id: int, payload: AssociationCreate, db: Session = Depends(get_db)
) -> Association:
    """Create a link from ``person_id`` to ``to_person_id`` (e.g. godparent → godchild)."""
    if db.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    if db.get(Person, payload.to_person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {payload.to_person_id} not found")
    if payload.to_person_id == person_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "A person cannot associate with themselves"
        )

    assoc = Association(
        from_person_id=person_id, to_person_id=payload.to_person_id, type=payload.type
    )
    db.add(assoc)
    db.commit()
    db.refresh(assoc)
    return assoc


@router.get("/persons/{person_id}/associations", response_model=list[AssociationRead])
def list_associations(person_id: int, db: Session = Depends(get_db)) -> list[Association]:
    """All associations touching this person (as source or target)."""
    if db.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    return list(
        db.scalars(
            select(Association).where(
                or_(
                    Association.from_person_id == person_id,
                    Association.to_person_id == person_id,
                )
            )
        )
    )


@router.delete("/associations/{association_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_association(association_id: int, db: Session = Depends(get_db)) -> None:
    assoc = db.get(Association, association_id)
    if assoc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Association {association_id} not found")
    db.delete(assoc)
    db.commit()
