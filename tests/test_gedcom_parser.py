"""Tests for the GEDCOM 5.5.1 reader and writer, including round-trip fidelity."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from backend.app.models import (
    Event,
    EventType,
    Family,
    PartnerType,
    Pedigree,
    Person,
    Relationship,
    RelationshipRole,
    Sex,
    Source,
)
from backend.app.parsers import export_gedcom, import_gedcom
from backend.app.parsers.dates import parse_gedcom_date


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def test_import_counts(db, sample_ged):
    result = import_gedcom(db, sample_ged)
    db.commit()
    assert result.persons == 4
    assert result.families == 1
    assert result.sources == 1
    assert result.relationships == 4  # 2 partners + 2 children
    # BIRT x3 + DEAT x1 + OCCU x1 + MARR x1
    assert result.events == 6
    assert result.warnings == []


def test_import_parses_names_and_suffix(db, sample_ged):
    import_gedcom(db, sample_ged)
    john = db.scalar(select(Person).where(Person.xref_id == "@I1@"))
    assert (john.given_name, john.surname) == ("John", "Smith")
    assert john.display_name == "John Smith"

    david = db.scalar(select(Person).where(Person.xref_id == "@I4@"))
    assert david.given_name == "David"
    assert david.surname == "Smith"
    assert david.name_suffix == "Jr"


def test_import_parses_sex(db, sample_ged):
    import_gedcom(db, sample_ged)
    assert db.scalar(select(Person).where(Person.xref_id == "@I1@")).sex == Sex.MALE
    assert db.scalar(select(Person).where(Person.xref_id == "@I2@")).sex == Sex.FEMALE


def test_partner_and_child_relationships(db, sample_ged):
    import_gedcom(db, sample_ged)
    fam = db.scalar(select(Family).where(Family.xref_id == "@F1@"))
    partners = {r.person.given_name: r.partner_type for r in fam.partners}
    assert partners == {"John": PartnerType.HUSBAND, "Mary": PartnerType.WIFE}
    children = {r.person.given_name for r in fam.children}
    assert children == {"Carol", "David"}


def test_adoption_pedigree_from_famc(db, sample_ged):
    import_gedcom(db, sample_ged)
    rels = db.scalars(select(Relationship).where(Relationship.role == RelationshipRole.CHILD)).all()
    ped = {r.person.given_name: r.pedigree for r in rels}
    assert ped["Carol"] == Pedigree.BIRTH  # default
    assert ped["David"] == Pedigree.ADOPTED  # from 2 PEDI adopted


def test_family_marriage_event_with_place(db, sample_ged):
    import_gedcom(db, sample_ged)
    marr = db.scalar(select(Event).where(Event.type == EventType.MARRIAGE))
    assert marr.family_id is not None and marr.person_id is None
    assert marr.date_value == "12 JUN 1928"
    assert marr.place == "Boston, Massachusetts"
    assert marr.date_sort == date(1928, 6, 12)


def test_individual_birth_event_and_date_sort(db, sample_ged):
    import_gedcom(db, sample_ged)
    john = db.scalar(select(Person).where(Person.xref_id == "@I1@"))
    births = [e for e in john.events if e.type == EventType.BIRTH]
    assert len(births) == 1
    assert births[0].date_sort == date(1900, 1, 1)


def test_source_and_citation_linked_to_event(db, sample_ged):
    import_gedcom(db, sample_ged)
    src = db.scalar(select(Source).where(Source.xref_id == "@S1@"))
    assert src.title == "Massachusetts Marriage Records"
    marr = db.scalar(select(Event).where(Event.type == EventType.MARRIAGE))
    assert len(marr.citations) == 1
    assert marr.citations[0].source_id == src.id
    assert marr.citations[0].page == "p.42"


def test_family_note_imported(db, sample_ged):
    import_gedcom(db, sample_ged)
    fam = db.scalar(select(Family).where(Family.xref_id == "@F1@"))
    assert fam.notes == "Married in a small ceremony."


# --------------------------------------------------------------------------- #
# Date parsing
# --------------------------------------------------------------------------- #
def test_parse_gedcom_dates():
    assert parse_gedcom_date("1 JAN 1900") == date(1900, 1, 1)
    assert parse_gedcom_date("MAR 1905") == date(1905, 3, 1)
    assert parse_gedcom_date("1970") == date(1970, 1, 1)
    assert parse_gedcom_date("ABT 1930") == date(1930, 1, 1)
    assert parse_gedcom_date("BET 1900 AND 1910") == date(1900, 1, 1)
    assert parse_gedcom_date("") is None
    assert parse_gedcom_date("unknown") is None


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_export_has_header_and_trailer(db, sample_ged):
    import_gedcom(db, sample_ged)
    out = export_gedcom(db)
    assert out.startswith("0 HEAD")
    assert "2 VERS 5.5.1" in out
    assert out.rstrip().endswith("0 TRLR")


def test_export_version_7_header(db, sample_ged):
    import_gedcom(db, sample_ged)
    out = export_gedcom(db, gedcom_version="7.0")
    assert "2 VERS 7.0" in out


def test_export_writes_pedigree_under_famc(db, sample_ged):
    import_gedcom(db, sample_ged)
    out = export_gedcom(db)
    lines = out.splitlines()
    # David's FAMC should be followed by a PEDI adopted line.
    famc_idx = [i for i, ln in enumerate(lines) if ln.startswith("1 FAMC")]
    assert any(lines[i + 1].strip() == "2 PEDI adopted" for i in famc_idx)


# --------------------------------------------------------------------------- #
# Round-trip
# --------------------------------------------------------------------------- #
def _facts(session):
    """A comparable snapshot of the genealogically meaningful content."""
    people = {
        p.display_name: (p.sex, sorted((e.type.value, e.date_value) for e in p.events))
        for p in session.scalars(select(Person))
    }
    child_ped = {
        r.person.display_name: r.pedigree
        for r in session.scalars(
            select(Relationship).where(Relationship.role == RelationshipRole.CHILD)
        )
    }
    marriages = sorted(
        (e.date_value, e.place)
        for e in session.scalars(select(Event).where(Event.type == EventType.MARRIAGE))
    )
    return people, child_ped, marriages


def test_round_trip_preserves_facts(db, sample_ged, new_session):
    import_gedcom(db, sample_ged)
    db.commit()
    before = _facts(db)

    exported = export_gedcom(db)

    db2 = new_session()
    try:
        import_gedcom(db2, exported)
        db2.commit()
        after = _facts(db2)
    finally:
        db2.close()

    assert before == after


def test_round_trip_is_stable_on_second_export(db, sample_ged, new_session):
    """export → import → export should be textually identical (idempotent)."""
    import_gedcom(db, sample_ged)
    first = export_gedcom(db)

    db2 = new_session()
    try:
        import_gedcom(db2, first)
        second = export_gedcom(db2)
    finally:
        db2.close()

    assert first == second


# --------------------------------------------------------------------------- #
# Non-traditional families
# --------------------------------------------------------------------------- #
def test_same_sex_partners_export_to_husb_wife_slots(db):
    """Two SPOUSE partners with unknown sex still round-trip through the slots."""
    a = Person(given_name="Alex", surname="Rivera", sex=Sex.UNKNOWN, xref_id="@I1@")
    b = Person(given_name="Sam", surname="Rivera", sex=Sex.UNKNOWN, xref_id="@I2@")
    fam = Family(xref_id="@F1@")
    db.add_all([a, b, fam])
    db.flush()
    db.add_all(
        [
            Relationship(
                person_id=a.id,
                family_id=fam.id,
                role=RelationshipRole.PARTNER,
                partner_type=PartnerType.SPOUSE,
            ),
            Relationship(
                person_id=b.id,
                family_id=fam.id,
                role=RelationshipRole.PARTNER,
                partner_type=PartnerType.SPOUSE,
            ),
        ]
    )
    db.commit()

    out = export_gedcom(db)
    assert "1 HUSB @I1@" in out
    assert "1 WIFE @I2@" in out  # second SPOUSE fills the empty WIFE slot
