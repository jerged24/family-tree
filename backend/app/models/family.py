"""Family — a GEDCOM FAM record (a partnership / household unit)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, RelationshipRole, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.event import Event
    from backend.app.models.relationship import Relationship


class Family(Base, TimestampMixin):
    """A family unit joining partners and their children (GEDCOM ``FAM``).

    Marriage / divorce are modelled as :class:`Event` rows scoped to the family,
    not as columns here — that keeps dates, places, and sources uniform with
    individual events.
    """

    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    xref_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    memberships: Mapped[list[Relationship]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
        primaryjoin="Family.id == Event.family_id",
    )

    # --- convenience accessors (parents / children of this unit) ---
    @property
    def partners(self) -> list[Relationship]:
        return [m for m in self.memberships if m.role == RelationshipRole.PARTNER]

    @property
    def children(self) -> list[Relationship]:
        return [m for m in self.memberships if m.role == RelationshipRole.CHILD]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Family id={self.id} partners={len(self.partners)} children={len(self.children)}>"
