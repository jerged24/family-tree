"""Duplicate detection and person-merge logic.

Two people are flagged as a possible duplicate when their normalized names match
and their birth years don't *contradict* (equal, or at least one unknown). Merging
folds one person ("merge") into another ("keep"): every relationship, event, photo,
and association is re-pointed at ``keep`` — skipping anything that would duplicate an
existing row — blank ``keep`` fields are filled from ``merge``, then ``merge`` is
deleted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Association, Event, Media, Person, Relationship
from backend.app.models.base import EventType, Sex

_YEAR = re.compile(r"\b(\d{4})\b")


def _norm_name(p: Person) -> str:
    parts = [(p.given_name or "").strip().lower(), (p.surname or "").strip().lower()]
    return " ".join(x for x in parts if x)


def _birth_year(db: Session, person_id: int) -> int | None:
    ev = db.scalars(
        select(Event).where(Event.person_id == person_id, Event.type == EventType.BIRTH)
    ).first()
    if ev and ev.date_value and (m := _YEAR.search(ev.date_value)):
        return int(m.group(1))
    return None


@dataclass
class DuplicateCandidate:
    a_id: int
    b_id: int
    reason: str
    birth_year: int | None


def find_duplicates(db: Session) -> list[DuplicateCandidate]:
    """All unordered person pairs that share a name and don't contradict on birth year."""
    people = list(db.scalars(select(Person).order_by(Person.id)))
    years = {p.id: _birth_year(db, p.id) for p in people}

    groups: dict[str, list[Person]] = {}
    for p in people:
        name = _norm_name(p)
        if name:  # skip nameless rows — too weak a signal to pair on
            groups.setdefault(name, []).append(p)

    out: list[DuplicateCandidate] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                ya, yb = years[a.id], years[b.id]
                if ya is not None and yb is not None:
                    if ya != yb:
                        continue  # different birth years → not the same person
                    reason, year = f"Same name and birth year ({ya})", ya
                elif ya is None and yb is None:
                    reason, year = "Same name; no birth years recorded", None
                else:
                    reason, year = "Same name; one is missing a birth year", (ya or yb)
                out.append(DuplicateCandidate(a.id, b.id, reason, year))
    return out


def merge_persons(db: Session, keep: Person, merge: Person) -> Person:
    """Fold ``merge`` into ``keep`` and delete ``merge``. Caller commits."""
    # ---- relationships (unique on person+family+role) ----
    keep_rel = {
        (r.family_id, r.role)
        for r in db.scalars(select(Relationship).where(Relationship.person_id == keep.id))
    }
    for r in db.scalars(select(Relationship).where(Relationship.person_id == merge.id)):
        if (r.family_id, r.role) in keep_rel:
            db.delete(r)  # keep already belongs to this family in this role
        else:
            r.person_id = keep.id
            keep_rel.add((r.family_id, r.role))

    # ---- events (no uniqueness) ----
    for e in db.scalars(select(Event).where(Event.person_id == merge.id)):
        e.person_id = keep.id

    # ---- media (no uniqueness, but only one primary) ----
    keep_has_primary = any(
        m.is_primary for m in db.scalars(select(Media).where(Media.person_id == keep.id))
    )
    for m in db.scalars(select(Media).where(Media.person_id == merge.id)):
        m.person_id = keep.id
        if m.is_primary and keep_has_primary:
            m.is_primary = False
        elif m.is_primary:
            keep_has_primary = True

    # ---- associations (unique on from+to+type; must not become self-links) ----
    keep_assoc = {
        (a.from_person_id, a.to_person_id, a.type)
        for a in db.scalars(
            select(Association).where(
                (Association.from_person_id == keep.id) | (Association.to_person_id == keep.id)
            )
        )
    }
    assoc = db.scalars(
        select(Association).where(
            (Association.from_person_id == merge.id) | (Association.to_person_id == merge.id)
        )
    )
    for a in assoc:
        new_from = keep.id if a.from_person_id == merge.id else a.from_person_id
        new_to = keep.id if a.to_person_id == merge.id else a.to_person_id
        if new_from == new_to or (new_from, new_to, a.type) in keep_assoc:
            db.delete(a)  # would be a self-link or a duplicate
        else:
            a.from_person_id, a.to_person_id = new_from, new_to
            keep_assoc.add((new_from, new_to, a.type))

    # ---- fill blank scalar fields on keep from merge ----
    for field in ("given_name", "surname", "name_prefix", "name_suffix", "nickname", "notes"):
        if not getattr(keep, field) and getattr(merge, field):
            setattr(keep, field, getattr(merge, field))
    if keep.sex == Sex.UNKNOWN and merge.sex != Sex.UNKNOWN:
        keep.sex = merge.sex

    db.flush()  # apply re-points before the delete so nothing cascades off merge
    db.delete(merge)
    return keep
