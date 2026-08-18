"""Person — a GEDCOM INDI record."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, Sex, TimestampMixin, str_enum

if TYPE_CHECKING:
    from backend.app.models.event import Event
    from backend.app.models.relationship import Relationship


class Person(Base, TimestampMixin):
    """An individual in the tree (GEDCOM ``INDI``)."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Original GEDCOM cross-reference id (e.g. "@I1@") for lossless round-tripping.
    xref_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)

    given_name: Mapped[str | None] = mapped_column(String(200))
    surname: Mapped[str | None] = mapped_column(String(200), index=True)
    name_prefix: Mapped[str | None] = mapped_column(String(50))  # NPFX (Dr., Sir)
    name_suffix: Mapped[str | None] = mapped_column(String(50))  # NSFX (Jr., III)
    nickname: Mapped[str | None] = mapped_column(String(100))

    sex: Mapped[Sex] = mapped_column(str_enum(Sex, 1), default=Sex.UNKNOWN, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    memberships: Mapped[list[Relationship]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        primaryjoin="Person.id == Event.person_id",
    )

    @property
    def display_name(self) -> str:
        """Human-friendly full name; GEDCOM stores surname in /slashes/."""
        parts = [self.name_prefix, self.given_name, self.surname, self.name_suffix]
        return " ".join(p for p in parts if p) or "(unknown)"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Person id={self.id} {self.display_name!r}>"
