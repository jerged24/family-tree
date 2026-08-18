"""Tests for pilot improvements: sample data, merge-on-import, and media."""

from __future__ import annotations

from importlib import resources

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.models import Media, Pedigree, Person, Relationship, RelationshipRole
from backend.app.parsers import export_gedcom, import_gedcom


def _sample_text() -> str:
    return resources.files("backend.app.data").joinpath("sample.ged").read_text(encoding="utf-8")


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --------------------------------------------------------------------------- sample data
def test_bundled_sample_imports(db):
    result = import_gedcom(db, _sample_text(), merge=True)
    db.commit()
    assert result.persons == 9
    assert result.families == 3
    # Emily is the adopted child in the sample.
    emily = db.scalar(select(Person).where(Person.given_name == "Emily"))
    rel = db.scalar(
        select(Relationship).where(
            Relationship.person_id == emily.id, Relationship.role == RelationshipRole.CHILD
        )
    )
    assert rel.pedigree == Pedigree.ADOPTED


# --------------------------------------------------------------------------- merge-on-import
def test_merge_import_is_idempotent(db):
    first = import_gedcom(db, _sample_text(), merge=True)
    db.commit()
    assert first.persons == 9

    second = import_gedcom(db, _sample_text(), merge=True)
    db.commit()
    # Nothing new created the second time.
    assert (second.persons, second.families, second.relationships, second.events) == (0, 0, 0, 0)
    assert _count(db, Person) == 9  # no duplicates


def test_append_import_conflicts_on_duplicate_xref(db):
    import_gedcom(db, _sample_text(), merge=False)
    db.commit()
    with pytest.raises(IntegrityError):
        import_gedcom(db, _sample_text(), merge=False)
        db.commit()


def test_merge_updates_scalar_fields(db):
    import_gedcom(db, _sample_text(), merge=True)
    db.commit()
    robert = db.scalar(select(Person).where(Person.given_name == "Robert"))
    robert.surname = "Changed"
    db.commit()
    # Re-importing restores the surname from the file.
    import_gedcom(db, _sample_text(), merge=True)
    db.commit()
    db.refresh(robert)
    assert robert.surname == "King"


# --------------------------------------------------------------------------- media
def test_photo_url_prefers_primary(db):
    p = Person(given_name="Ana", surname="Vega")
    db.add(p)
    db.flush()
    db.add_all(
        [
            Media(person_id=p.id, url="https://x/first.jpg"),
            Media(person_id=p.id, url="https://x/primary.jpg", is_primary=True),
        ]
    )
    db.commit()
    assert p.photo_url == "https://x/primary.jpg"


def test_media_gedcom_round_trip(db, new_session):
    ged = (
        "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n"
        "0 @I1@ INDI\n1 NAME Ida /Photo/\n1 SEX F\n"
        "1 OBJE\n2 FILE https://example.com/ida.jpg\n3 FORM image/jpeg\n"
        "2 TITL Ida portrait\n2 _PRIM Y\n"
        "0 TRLR\n"
    )
    result = import_gedcom(db, ged, merge=True)
    db.commit()
    assert result.media == 1
    ida = db.scalar(select(Person).where(Person.given_name == "Ida"))
    assert ida.photo_url == "https://example.com/ida.jpg"
    assert ida.media[0].caption == "Ida portrait"
    assert ida.media[0].is_primary is True

    # Export → OBJE emitted → re-import preserves the media.
    out = export_gedcom(db)
    assert "1 OBJE" in out and "2 FILE https://example.com/ida.jpg" in out
    db2 = new_session()
    try:
        import_gedcom(db2, out, merge=True)
        db2.commit()
        ida2 = db2.scalar(select(Person).where(Person.given_name == "Ida"))
        assert ida2.photo_url == "https://example.com/ida.jpg"
    finally:
        db2.close()
