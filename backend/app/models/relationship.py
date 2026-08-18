"""Relationship — the association edge joining a Person to a Family.

This single table encodes the whole family graph:

* ``role = PARTNER`` rows are the spouses / co-parents of a family
  (``partner_type`` distinguishes husband / wife / sex-neutral spouse / partner).
* ``role = CHILD`` rows are the offspring / dependents of a family
  (``pedigree`` distinguishes birth / adopted / foster / step / ...).

The directed **parent→child DAG** consumed by NetworkX is *derived*: for each
family, every PARTNER is a parent of every CHILD. Storing membership rather than
raw parent-child edges lets multiple marriages, blended families, and adoption
fall out naturally with no special cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import (
    Base,
    PartnerType,
    Pedigree,
    RelationshipRole,
    TimestampMixin,
    str_enum,
)

if TYPE_CHECKING:
    from backend.app.models.family import Family
    from backend.app.models.person import Person


class Relationship(Base, TimestampMixin):
    """Membership of a Person in a Family, as PARTNER or CHILD."""

    __tablename__ = "relationships"
    __table_args__ = (
        # A person holds a given role in a given family at most once.
        UniqueConstraint("person_id", "family_id", "role", name="uq_person_family_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True, nullable=False
    )

    role: Mapped[RelationshipRole] = mapped_column(str_enum(RelationshipRole, 10), nullable=False)
    # Set when role == PARTNER.
    partner_type: Mapped[PartnerType | None] = mapped_column(str_enum(PartnerType, 10))
    # Set when role == CHILD; defaults to BIRTH on child rows.
    pedigree: Mapped[Pedigree | None] = mapped_column(str_enum(Pedigree, 10))

    # --- relationships ---
    person: Mapped[Person] = relationship(back_populates="memberships")
    family: Mapped[Family] = relationship(back_populates="memberships")

    def __repr__(self) -> str:  # pragma: no cover
        detail = self.partner_type or self.pedigree
        return (
            f"<Relationship person={self.person_id} family={self.family_id} "
            f"role={self.role.value} {detail.value if detail else ''}>"
        )
