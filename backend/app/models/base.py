"""Declarative base, shared mixin, and domain enums.

Enums are stored as plain strings (``native_enum=False``) so the SQLite file stays
human-readable and portable across engines.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Root declarative base for all ORM models."""


def str_enum(enum_cls: type[enum.Enum], length: int) -> SAEnum:
    """A non-native string Enum column that stores each member's ``.value``.

    SQLAlchemy defaults to storing enum *names*; we want the compact GEDCOM tag
    values (e.g. ``BIRT`` rather than ``BIRTH``) so the SQLite file stays close to
    the GEDCOM source and portable.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class TimestampMixin:
    """Adds created/updated audit columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class Sex(enum.StrEnum):
    """GEDCOM SEX tag values (plus X/U for non-binary / unknown)."""

    MALE = "M"
    FEMALE = "F"
    INTERSEX = "X"
    UNKNOWN = "U"


class RelationshipRole(enum.StrEnum):
    """How a Person participates in a Family."""

    PARTNER = "PARTNER"  # spouse / co-parent (GEDCOM HUSB / WIFE)
    CHILD = "CHILD"  # offspring / dependent (GEDCOM CHIL)


class PartnerType(enum.StrEnum):
    """Sub-classification of a PARTNER relationship. Supports non-traditional unions."""

    HUSBAND = "HUSBAND"
    WIFE = "WIFE"
    SPOUSE = "SPOUSE"  # sex-neutral married partner
    PARTNER = "PARTNER"  # unmarried / domestic partner


class Pedigree(enum.StrEnum):
    """Nature of a CHILD relationship (GEDCOM PEDI + common extensions)."""

    BIRTH = "BIRTH"
    ADOPTED = "ADOPTED"
    FOSTER = "FOSTER"
    STEP = "STEP"
    SEALED = "SEALED"
    GUARDIAN = "GUARDIAN"


class EventType(enum.StrEnum):
    """Common GEDCOM 5.5.1 event tags. Individual- or family-scoped."""

    # Individual events
    BIRTH = "BIRT"
    DEATH = "DEAT"
    BURIAL = "BURI"
    CHRISTENING = "CHR"
    BAPTISM = "BAPM"
    ADOPTION = "ADOP"
    GRADUATION = "GRAD"
    IMMIGRATION = "IMMI"
    OCCUPATION = "OCCU"
    RESIDENCE = "RESI"
    # Family events
    MARRIAGE = "MARR"
    DIVORCE = "DIV"
    ENGAGEMENT = "ENGA"
    ANNULMENT = "ANUL"
    # Catch-all custom event
    OTHER = "EVEN"
