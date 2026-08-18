"""GEDCOM 5.5.1 importer: ``.ged`` text → ORM objects persisted to a session.

Two passes:

1. Create every ``Person`` (INDI), ``Family`` (FAM) and ``Source`` (SOUR) record so
   their primary keys exist and xrefs resolve.
2. Populate names/sex/events/media on people, HUSB/WIFE/CHIL membership on families
   (as ``Relationship`` rows), pedigree from each INDI's ``FAMC``/``PEDI``, and
   source citations on events.

**Merge mode** (``merge=True``): records are matched to existing rows by ``xref_id``
and updated in place instead of inserted, and relationships / events / media are
de-duplicated. This makes re-importing the same document idempotent rather than
failing on the unique ``xref_id`` constraint. ``ImportResult`` counts reflect rows
*newly created* (so a second identical import reports zeros).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    Citation,
    Event,
    EventType,
    Family,
    Media,
    PartnerType,
    Pedigree,
    Person,
    Relationship,
    RelationshipRole,
    Sex,
    Source,
)
from backend.app.parsers.dates import parse_gedcom_date
from backend.app.parsers.structure import GedNode, parse_records

# GEDCOM tag (== EventType.value) → EventType, split by the record it belongs to.
_TAG_TO_EVENT = {e.value: e for e in EventType}
_INDIVIDUAL_EVENT_TAGS = {
    EventType.BIRTH,
    EventType.DEATH,
    EventType.BURIAL,
    EventType.CHRISTENING,
    EventType.BAPTISM,
    EventType.ADOPTION,
    EventType.GRADUATION,
    EventType.IMMIGRATION,
    EventType.OCCUPATION,
    EventType.RESIDENCE,
    EventType.OTHER,
}
_FAMILY_EVENT_TAGS = {
    EventType.MARRIAGE,
    EventType.DIVORCE,
    EventType.ENGAGEMENT,
    EventType.ANNULMENT,
}
_INDIVIDUAL_EVENT_STR = {e.value for e in _INDIVIDUAL_EVENT_TAGS}
_FAMILY_EVENT_STR = {e.value for e in _FAMILY_EVENT_TAGS}

_PEDI_MAP = {
    "birth": Pedigree.BIRTH,
    "adopted": Pedigree.ADOPTED,
    "foster": Pedigree.FOSTER,
    "step": Pedigree.STEP,
    "sealed": Pedigree.SEALED,
    "guardian": Pedigree.GUARDIAN,
}

_NAME_RE = re.compile(r"^(?P<given>.*?)\s*/(?P<surname>[^/]*)/\s*(?P<suffix>.*)$")


@dataclass
class ImportResult:
    persons: int = 0
    families: int = 0
    relationships: int = 0
    events: int = 0
    sources: int = 0
    media: int = 0
    warnings: list[str] = field(default_factory=list)


class GedcomReader:
    """Imports one GEDCOM document into a SQLAlchemy session."""

    def __init__(self, db: Session, *, merge: bool = False) -> None:
        self.db = db
        self.merge = merge
        self._person: dict[str, Person] = {}
        self._family: dict[str, Family] = {}
        self._source: dict[str, Source] = {}
        self._famc_pedigree: dict[tuple[str | None, str | None], Pedigree] = {}
        self.result = ImportResult()

    # -- public API ---------------------------------------------------------
    def read_text(self, text: str) -> ImportResult:
        records = parse_records(text)
        self._famc_pedigree = _collect_famc_pedigree(records)

        for rec in records:
            if rec.tag == "INDI":
                self._create_person(rec)
            elif rec.tag == "FAM":
                self._create_family(rec)
            elif rec.tag == "SOUR" and rec.xref:
                self._create_source(rec)
        self.db.flush()

        for rec in records:
            if rec.tag == "INDI":
                self._populate_person(rec)
            elif rec.tag == "FAM":
                self._populate_family(rec)
        self.db.flush()
        return self.result

    def read_file(self, path: str, encoding: str = "utf-8-sig") -> ImportResult:
        with open(path, encoding=encoding) as fh:
            return self.read_text(fh.read())

    # -- pass 1: bare records ----------------------------------------------
    def _existing(self, model, xref: str | None):
        if not (self.merge and xref):
            return None
        return self.db.scalar(select(model).where(model.xref_id == xref))

    def _create_person(self, rec: GedNode) -> None:
        person = self._existing(Person, rec.xref)
        if person is None:
            person = Person(xref_id=rec.xref)
            self.db.add(person)
            self.result.persons += 1
        if rec.xref:
            self._person[rec.xref] = person

    def _create_family(self, rec: GedNode) -> None:
        family = self._existing(Family, rec.xref)
        if family is None:
            family = Family(xref_id=rec.xref)
            self.db.add(family)
            self.result.families += 1
        if rec.xref:
            self._family[rec.xref] = family

    def _create_source(self, rec: GedNode) -> None:
        source = self._existing(Source, rec.xref)
        if source is None:
            source = Source(xref_id=rec.xref)
            self.db.add(source)
            self.result.sources += 1
        source.title = rec.value_of("TITL")
        source.author = rec.value_of("AUTH")
        source.publication = rec.value_of("PUBL")
        source.repository = rec.value_of("REPO")
        source.text = rec.value_of("TEXT")
        self._source[rec.xref] = source

    # -- pass 2: contents ---------------------------------------------------
    def _populate_person(self, rec: GedNode) -> None:
        person = self._person.get(rec.xref)
        if person is None:
            return

        name_node = rec.first("NAME")
        if name_node is not None:
            self._apply_name(person, name_node)

        sex_val = (rec.value_of("SEX") or "").upper()
        person.sex = next((s for s in Sex if s.value == sex_val), Sex.UNKNOWN)

        notes = [n.value for n in rec.all("NOTE") if n.value]
        if notes:
            person.notes = "\n".join(notes)

        for child in rec.children:
            if child.tag in _INDIVIDUAL_EVENT_STR:
                self._add_event(child, person=person)
            elif child.tag == "OBJE":
                self._add_media(child, person)

    def _populate_family(self, rec: GedNode) -> None:
        family = self._family.get(rec.xref)
        if family is None:
            return

        for node, ptype in (
            (rec.first("HUSB"), PartnerType.HUSBAND),
            (rec.first("WIFE"), PartnerType.WIFE),
        ):
            if node and node.value in self._person:
                self._add_relationship(
                    family, self._person[node.value], RelationshipRole.PARTNER, partner_type=ptype
                )

        for chil in rec.all("CHIL"):
            person = self._person.get(chil.value)
            if person is None:
                self.result.warnings.append(f"CHIL {chil.value} in {rec.xref} not found")
                continue
            pedigree = self._pedigree_for(person, family)
            self._add_relationship(family, person, RelationshipRole.CHILD, pedigree=pedigree)

        notes = [n.value for n in rec.all("NOTE") if n.value]
        if notes:
            family.notes = "\n".join(notes)

        for child in rec.children:
            if child.tag in _FAMILY_EVENT_STR:
                self._add_event(child, family=family)

    # -- helpers ------------------------------------------------------------
    def _apply_name(self, person: Person, name_node: GedNode) -> None:
        m = _NAME_RE.match(name_node.value)
        if m:
            person.given_name = m.group("given").strip() or None
            person.surname = m.group("surname").strip() or None
            person.name_suffix = m.group("suffix").strip() or None
        elif name_node.value:
            person.given_name = name_node.value.strip() or None
        # Structured sub-tags take precedence when present.
        person.given_name = name_node.value_of("GIVN") or person.given_name
        person.surname = name_node.value_of("SURN") or person.surname
        person.name_prefix = name_node.value_of("NPFX") or person.name_prefix
        person.name_suffix = name_node.value_of("NSFX") or person.name_suffix
        person.nickname = name_node.value_of("NICK") or person.nickname

    def _pedigree_for(self, person: Person, family: Family) -> Pedigree:
        """Read PEDI from the INDI's FAMC pointer back to this family (5.5.1 placement)."""
        return self._famc_pedigree.get((person.xref_id, family.xref_id), Pedigree.BIRTH)

    def _add_relationship(
        self,
        family: Family,
        person: Person,
        role: RelationshipRole,
        *,
        partner_type: PartnerType | None = None,
        pedigree: Pedigree | None = None,
    ) -> None:
        if self.merge:
            existing = self.db.scalar(
                select(Relationship).where(
                    Relationship.person_id == person.id,
                    Relationship.family_id == family.id,
                    Relationship.role == role,
                )
            )
            if existing is not None:
                existing.partner_type = partner_type
                existing.pedigree = pedigree
                return

        rel = Relationship(
            person_id=person.id,
            family_id=family.id,
            role=role,
            partner_type=partner_type,
            pedigree=pedigree,
        )
        self.db.add(rel)
        self.result.relationships += 1

    def _add_event(
        self, node: GedNode, *, person: Person | None = None, family: Family | None = None
    ) -> None:
        etype = _TAG_TO_EVENT.get(node.tag, EventType.OTHER)
        date_value = node.value_of("DATE")
        # Value-bearing events (OCCU "Farmer") and EVEN carry their value/TYPE as description.
        description = node.value_of("TYPE") or (node.value or None)
        place = node.value_of("PLAC")

        if self.merge:
            stmt = select(Event).where(
                Event.type == etype,
                Event.date_value == date_value,
                Event.place == place,
            )
            stmt = stmt.where(
                Event.person_id == (person.id if person else None),
                Event.family_id == (family.id if family else None),
            )
            if self.db.scalar(stmt) is not None:
                return  # identical event already recorded

        event = Event(
            type=etype,
            person_id=person.id if person else None,
            family_id=family.id if family else None,
            date_value=date_value,
            date_sort=parse_gedcom_date(date_value),
            place=place,
            description=description,
        )
        self.db.add(event)
        self.db.flush()  # need event.id for citations
        self.result.events += 1

        for sour in node.all("SOUR"):
            source = self._source.get(sour.value)
            if source is None:
                continue
            self.db.add(
                Citation(
                    source_id=source.id,
                    event_id=event.id,
                    page=sour.value_of("PAGE"),
                    note=sour.value_of("NOTE"),
                )
            )

    def _add_media(self, node: GedNode, person: Person) -> None:
        url = node.value_of("FILE") or (node.value or None)
        if not url:
            return
        if self.merge:
            existing = self.db.scalar(
                select(Media).where(Media.person_id == person.id, Media.url == url)
            )
            if existing is not None:
                return
        self.db.add(
            Media(
                person_id=person.id,
                url=url,
                caption=node.value_of("TITL"),
                mime_type=node.value_of("FORM"),
                is_primary=(node.value_of("_PRIM") or "").upper() == "Y",
            )
        )
        self.result.media += 1


def _collect_famc_pedigree(
    records: list[GedNode],
) -> dict[tuple[str | None, str | None], Pedigree]:
    """Map (person_xref, family_xref) → Pedigree from each INDI's FAMC/PEDI sub-tag."""
    out: dict[tuple[str | None, str | None], Pedigree] = {}
    for rec in records:
        if rec.tag != "INDI":
            continue
        for famc in rec.all("FAMC"):
            pedi = (famc.value_of("PEDI") or "").lower()
            if pedi in _PEDI_MAP:
                out[(rec.xref, famc.value)] = _PEDI_MAP[pedi]
    return out


def import_gedcom(db: Session, text: str, *, merge: bool = False) -> ImportResult:
    """Import GEDCOM ``text`` into ``db`` and return counts. Caller commits."""
    return GedcomReader(db, merge=merge).read_text(text)
