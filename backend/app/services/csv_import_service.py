"""Import people from a simple spreadsheet (CSV).

Built for non-technical family members filling a shared sheet / Google Form: one
row per person, with plain "Father's name / Mother's name / Spouse's name" columns
that get resolved into the family DAG by name.

Design choices worth knowing:
- **Name matching, not IDs** — relatives never manage IDs. Relationship columns are
  matched against everyone already in the tree plus everyone in this upload.
- **Stubs for the missing** — a parent/spouse named but with no row of their own is
  added as a name-only person so the tree still connects; the duplicate-merge tool
  cleans those up if a real row for them arrives later.
- **Ambiguity is reported, not guessed** — a name that matches two people is left
  unlinked with a warning rather than linked to the wrong person.
- **Extra columns are ignored** — Google Forms adds Timestamp/Email columns; unknown
  headers are simply skipped.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Event, Family, Person, Relationship
from backend.app.models.base import EventType, PartnerType, Pedigree, RelationshipRole, Sex

# Canonical field -> accepted header spellings (compared lowercased & whitespace-collapsed).
_ALIASES: dict[str, set[str]] = {
    "first_name": {"first name", "first", "given name", "given", "firstname"},
    "last_name": {"last name", "last", "surname", "family name", "lastname"},
    "sex": {"sex", "gender"},
    "dob": {"date of birth", "birth date", "birthdate", "dob", "born"},
    "birthplace": {"birth place", "birthplace", "place of birth", "town", "city"},
    "dod": {"date of death", "death date", "dod", "died"},
    "father": {
        "father's full name",
        "fathers full name",
        "father",
        "father name",
        "father's name",
        "dad",
    },
    "mother": {
        "mother's full name",
        "mothers full name",
        "mother",
        "mother name",
        "mother's name",
        "mom",
        "mum",
    },
    "spouse": {
        "spouse's full name",
        "spouses full name",
        "spouse",
        "spouse name",
        "spouse's name",
        "husband",
        "wife",
        "partner",
    },
    "notes": {"notes", "note", "remarks", "comments"},
}

_SEX = {
    "m": Sex.MALE,
    "male": Sex.MALE,
    "f": Sex.FEMALE,
    "female": Sex.FEMALE,
    "x": Sex.INTERSEX,
    "intersex": Sex.INTERSEX,
}


@dataclass
class CsvImportResult:
    persons: int = 0
    stubs: int = 0
    families: int = 0
    relationships: int = 0
    events: int = 0
    warnings: list[str] = field(default_factory=list)


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip()


def _key(name: str) -> str:
    return _norm(name).lower()


def _display(p: Person) -> str:
    return _norm(f"{p.given_name or ''} {p.surname or ''}") or "(unnamed)"


def _map_headers(fieldnames: list[str] | None) -> dict[str, str]:
    """Map canonical field -> the actual header present in the file."""
    out: dict[str, str] = {}
    for header in fieldnames or []:
        h = _key(header)
        for canon, spellings in _ALIASES.items():
            if h in spellings and canon not in out:
                out[canon] = header
    return out


def import_csv(db: Session, data: bytes) -> CsvImportResult:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    result = CsvImportResult()
    cols = _map_headers(reader.fieldnames)
    if "first_name" not in cols and "last_name" not in cols:
        result.warnings.append(
            "No name column found — the sheet needs at least a 'First name' or 'Last name' column."
        )
        return result

    def cell(row: dict, canon: str) -> str:
        header = cols.get(canon)
        return _norm(row.get(header)) if header else ""

    # ---- name index across the whole tree (existing rows + everyone we create) ----
    index: dict[str, list[int]] = {}

    def add_index(p: Person) -> None:
        k = _key(f"{p.given_name or ''} {p.surname or ''}")
        if k:
            index.setdefault(k, []).append(p.id)

    for existing in db.scalars(select(Person)):
        add_index(existing)

    # ---- pass 1: one Person (+ birth/death events) per row ----
    rows: list[tuple[Person, dict[str, str]]] = []
    for raw in reader:
        first, last = cell(raw, "first_name"), cell(raw, "last_name")
        if not first and not last:
            continue  # blank row
        person = Person(
            given_name=first or None,
            surname=last or None,
            sex=_SEX.get(cell(raw, "sex").lower(), Sex.UNKNOWN),
            notes=cell(raw, "notes") or None,
        )
        db.add(person)
        db.flush()
        add_index(person)
        result.persons += 1

        dob, dod, place = cell(raw, "dob"), cell(raw, "dod"), cell(raw, "birthplace")
        if dob or place:
            db.add(
                Event(
                    type=EventType.BIRTH,
                    person_id=person.id,
                    date_value=dob or None,
                    place=place or None,
                )
            )
            result.events += 1
        if dod:
            db.add(Event(type=EventType.DEATH, person_id=person.id, date_value=dod))
            result.events += 1

        rows.append(
            (
                person,
                {
                    "father": cell(raw, "father"),
                    "mother": cell(raw, "mother"),
                    "spouse": cell(raw, "spouse"),
                },
            )
        )

    if not rows:
        result.warnings.append("No people found — every row was blank.")
        return result

    stub_cache: dict[str, int] = {}

    def resolve(name: str, subject: Person, role: str) -> int | None:
        """Person id for ``name`` (creating a name-only stub if unknown); None if blank."""
        k = _key(name)
        if not k:
            return None
        ids = index.get(k)
        if ids and len(ids) == 1:
            return ids[0]
        if ids and len(ids) > 1:
            result.warnings.append(
                f"'{name}' ({role} of {_display(subject)}) matches {len(ids)} people — "
                "left unlinked; merge the duplicates, then link by hand."
            )
            return None
        if k in stub_cache:
            return stub_cache[k]
        parts = _norm(name).split()
        stub = Person(given_name=parts[0], surname=" ".join(parts[1:]) or None, sex=Sex.UNKNOWN)
        db.add(stub)
        db.flush()
        add_index(stub)
        stub_cache[k] = stub.id
        result.stubs += 1
        return stub.id

    # ---- pass 2: build families from parent / spouse columns ----
    partner_family: dict[frozenset[int], int] = {}
    added: set[tuple[int, int, RelationshipRole]] = set()

    def add_member(person_id: int, family_id: int, role: RelationshipRole, sex: Sex) -> None:
        rkey = (person_id, family_id, role)
        if rkey in added:
            return
        ptype = None
        if role == RelationshipRole.PARTNER:
            ptype = {Sex.MALE: PartnerType.HUSBAND, Sex.FEMALE: PartnerType.WIFE}.get(
                sex, PartnerType.SPOUSE
            )
        db.add(
            Relationship(
                person_id=person_id,
                family_id=family_id,
                role=role,
                pedigree=Pedigree.BIRTH if role == RelationshipRole.CHILD else None,
                partner_type=ptype,
            )
        )
        added.add(rkey)
        result.relationships += 1

    sex_of = {p.id: p.sex for p, _ in rows}

    def family_of(partner_ids: list[int]) -> int:
        fkey = frozenset(partner_ids)
        if fkey in partner_family:
            return partner_family[fkey]
        fam = Family()
        db.add(fam)
        db.flush()
        result.families += 1
        for pid in partner_ids:
            add_member(pid, fam.id, RelationshipRole.PARTNER, sex_of.get(pid, Sex.UNKNOWN))
        partner_family[fkey] = fam.id
        return fam.id

    for person, names in rows:
        father = resolve(names["father"], person, "father")
        mother = resolve(names["mother"], person, "mother")
        parents = [pid for pid in (father, mother) if pid and pid != person.id]
        if parents:
            add_member(person.id, family_of(parents), RelationshipRole.CHILD, person.sex)

        spouse = resolve(names["spouse"], person, "spouse")
        if spouse and spouse != person.id:
            family_of([person.id, spouse])  # find-or-create the couple's family

    return result
