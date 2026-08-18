"""Event — a dated, placed occurrence attached to a Person or a Family."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, EventType, TimestampMixin, str_enum

if TYPE_CHECKING:
    from backend.app.models.family import Family
    from backend.app.models.person import Person
    from backend.app.models.source import Citation


class Event(Base, TimestampMixin):
    """A genealogical event.

    Exactly one of ``person_id`` / ``family_id`` is set (enforced by a check
    constraint). Individual events (BIRT, DEAT, ...) point at a person; family
    events (MARR, DIV, ...) point at a family.

    The GEDCOM date string is preserved verbatim in ``date_value`` (which may be
    a range or approximation like ``ABT 1850`` / ``BET 1900 AND 1910``); a best-
    effort sortable date is stored separately in ``date_sort``.
    """

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "(person_id IS NOT NULL) <> (family_id IS NOT NULL)",
            name="ck_event_single_subject",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[EventType] = mapped_column(str_enum(EventType, 10), nullable=False)

    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )

    date_value: Mapped[str | None] = mapped_column(String(100))  # raw GEDCOM DATE string
    date_sort: Mapped[date | None] = mapped_column(Date)  # parsed, sortable (nullable)
    place: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    person: Mapped[Person | None] = relationship(back_populates="events", foreign_keys=[person_id])
    family: Mapped[Family | None] = relationship(back_populates="events", foreign_keys=[family_id])
    citations: Mapped[list[Citation]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        subj = f"person={self.person_id}" if self.person_id else f"family={self.family_id}"
        return f"<Event {self.type.value} {subj} date={self.date_value!r}>"
