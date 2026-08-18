"""GEDCOM exporter: ORM objects → valid GEDCOM 5.5.1 text.

Emits a HEAD (declaring GEDCOM 5.5.1 by default, or a 7.0 header form), one record
per Person / Family / Source, and a TRLR. Family membership stored as
``Relationship`` rows is rendered back into the standard HUSB / WIFE / CHIL layout,
with pedigree written under each individual's ``FAMC`` pointer (5.5.1 placement).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    Event,
    Family,
    PartnerType,
    Pedigree,
    Person,
    RelationshipRole,
    Sex,
    Source,
)


class GedcomWriter:
    """Serialises the whole database (or given records) to a GEDCOM string."""

    def __init__(self, db: Session, gedcom_version: str = "5.5.1") -> None:
        self.db = db
        self.version = gedcom_version
        self._lines: list[str] = []

    # -- public API ---------------------------------------------------------
    def write_text(self) -> str:
        self._lines = []
        self._write_header()

        persons = self.db.scalars(select(Person).order_by(Person.id)).all()
        families = self.db.scalars(select(Family).order_by(Family.id)).all()
        sources = self.db.scalars(select(Source).order_by(Source.id)).all()

        for person in persons:
            self._write_person(person)
        for family in families:
            self._write_family(family)
        for source in sources:
            self._write_source(source)

        self._line(0, "TRLR")
        return "\n".join(self._lines) + "\n"

    # -- low-level ----------------------------------------------------------
    def _line(
        self, level: int, tag: str, value: str | None = None, xref: str | None = None
    ) -> None:
        parts = [str(level)]
        if xref:
            parts.append(xref)
        parts.append(tag)
        if value is not None and value != "":
            parts.append(value)
        self._lines.append(" ".join(parts))

    def _text_block(self, level: int, tag: str, text: str | None) -> None:
        """Emit a possibly multi-line value using CONT for embedded newlines."""
        if not text:
            return
        first, *rest = text.split("\n")
        self._line(level, tag, first)
        for line in rest:
            self._line(level + 1, "CONT", line)

    # -- ids ----------------------------------------------------------------
    @staticmethod
    def _person_xref(p: Person) -> str:
        return p.xref_id or f"@I{p.id}@"

    @staticmethod
    def _family_xref(f: Family) -> str:
        return f.xref_id or f"@F{f.id}@"

    @staticmethod
    def _source_xref(s: Source) -> str:
        return s.xref_id or f"@S{s.id}@"

    # -- records ------------------------------------------------------------
    def _write_header(self) -> None:
        self._line(0, "HEAD")
        self._line(1, "SOUR", "FamilyTreeApp")
        self._line(2, "NAME", "Family Tree Application")
        self._line(1, "GEDC")
        self._line(2, "VERS", self.version)
        self._line(2, "FORM", "LINEAGE-LINKED")
        self._line(1, "CHAR", "UTF-8")

    def _write_person(self, person: Person) -> None:
        self._line(0, "INDI", xref=self._person_xref(person))

        name = self._format_name(person)
        self._line(1, "NAME", name)
        if person.given_name:
            self._line(2, "GIVN", person.given_name)
        if person.surname:
            self._line(2, "SURN", person.surname)
        if person.name_prefix:
            self._line(2, "NPFX", person.name_prefix)
        if person.name_suffix:
            self._line(2, "NSFX", person.name_suffix)
        if person.nickname:
            self._line(2, "NICK", person.nickname)

        if person.sex != Sex.UNKNOWN:
            self._line(1, "SEX", person.sex.value)

        for event in person.events:
            self._write_event(event)

        for rel in person.memberships:
            if rel.role == RelationshipRole.PARTNER:
                self._line(1, "FAMS", self._family_xref(rel.family))
            elif rel.role == RelationshipRole.CHILD:
                self._line(1, "FAMC", self._family_xref(rel.family))
                if rel.pedigree and rel.pedigree != Pedigree.BIRTH:
                    self._line(2, "PEDI", rel.pedigree.value.lower())

        self._text_block(1, "NOTE", person.notes)

    def _write_family(self, family: Family) -> None:
        self._line(0, "FAM", xref=self._family_xref(family))

        husband, wife, others = self._assign_partner_slots(family)
        if husband is not None:
            self._line(1, "HUSB", self._person_xref(husband))
        if wife is not None:
            self._line(1, "WIFE", self._person_xref(wife))
        for extra in others:
            # 5.5.1 has no third-partner tag; record as a custom association.
            self._line(1, "ASSO", self._person_xref(extra))
            self._line(2, "RELA", "partner")

        for rel in family.children:
            self._line(1, "CHIL", self._person_xref(rel.person))

        for event in family.events:
            self._write_event(event)

        self._text_block(1, "NOTE", family.notes)

    def _write_source(self, source: Source) -> None:
        self._line(0, "SOUR", xref=self._source_xref(source))
        if source.title:
            self._line(1, "TITL", source.title)
        if source.author:
            self._line(1, "AUTH", source.author)
        if source.publication:
            self._line(1, "PUBL", source.publication)
        if source.repository:
            self._line(1, "REPO", source.repository)
        self._text_block(1, "TEXT", source.text)

    def _write_event(self, event: Event) -> None:
        # Value-bearing events (OCCU) put their description on the tag line.
        inline = event.description if event.type.value in ("OCCU", "RESI") else None
        self._line(1, event.type.value, inline)
        if event.date_value:
            self._line(2, "DATE", event.date_value)
        if event.place:
            self._line(2, "PLAC", event.place)
        if event.description and inline is None:
            self._text_block(2, "NOTE", event.description)
        for cit in event.citations:
            self._line(2, "SOUR", self._source_xref(cit.source))
            if cit.page:
                self._line(3, "PAGE", cit.page)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _format_name(person: Person) -> str:
        given = person.given_name or ""
        value = f"{given} /{person.surname}/".strip() if person.surname else given
        if person.name_suffix:
            value = f"{value} {person.name_suffix}".strip()
        return value

    def _assign_partner_slots(
        self, family: Family
    ) -> tuple[Person | None, Person | None, list[Person]]:
        """Map PARTNER rows onto GEDCOM's single HUSB / WIFE slots.

        Explicit HUSBAND/WIFE win; otherwise infer from sex; leftover partners
        (e.g. same-sex couples where both are 'SPOUSE') fill the empty slot then
        overflow to ASSO.
        """
        husband: Person | None = None
        wife: Person | None = None
        leftovers: list[Person] = []

        for rel in family.partners:
            p = rel.person
            if rel.partner_type == PartnerType.HUSBAND and husband is None:
                husband = p
            elif rel.partner_type == PartnerType.WIFE and wife is None:
                wife = p
            elif p.sex == Sex.MALE and husband is None:
                husband = p
            elif p.sex == Sex.FEMALE and wife is None:
                wife = p
            else:
                leftovers.append(p)

        overflow: list[Person] = []
        for p in leftovers:
            if husband is None:
                husband = p
            elif wife is None:
                wife = p
            else:
                overflow.append(p)
        return husband, wife, overflow


def export_gedcom(db: Session, gedcom_version: str = "5.5.1") -> str:
    """Serialise the entire database to a GEDCOM string."""
    return GedcomWriter(db, gedcom_version).write_text()
