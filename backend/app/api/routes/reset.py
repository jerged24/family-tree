"""Owner-only "start over" — permanently wipe all family data."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import (
    Association,
    Citation,
    Event,
    Family,
    Media,
    Person,
    Relationship,
    Source,
)

router = APIRouter(tags=["admin"])

# Deleted children-first so foreign keys are satisfied even with enforcement on.
_WIPE_ORDER = (Citation, Association, Relationship, Media, Event, Source, Person, Family)


@router.post("/admin/reset")
def reset_all(db: Session = Depends(get_db)) -> dict[str, int]:
    """Delete ALL people, families, events, photos, links, and sources. Irreversible."""
    deleted_people = db.query(Person).count()
    for model in _WIPE_ORDER:
        db.query(model).delete(synchronize_session=False)
    db.commit()
    return {"deleted_people": deleted_people}
