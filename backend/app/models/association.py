"""Association — a directional person→person link outside the family DAG (e.g. godparent)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import AssociationType, Base, TimestampMixin, str_enum

if TYPE_CHECKING:
    from backend.app.models.person import Person


class Association(Base, TimestampMixin):
    """A non-lineage link from one person to another (e.g. godparent → godchild)."""

    __tablename__ = "associations"
    __table_args__ = (
        UniqueConstraint("from_person_id", "to_person_id", "type", name="uq_association"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[AssociationType] = mapped_column(str_enum(AssociationType, 12), nullable=False)

    from_person: Mapped[Person] = relationship(foreign_keys=[from_person_id])
    to_person: Mapped[Person] = relationship(foreign_keys=[to_person_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Association {self.type.value} {self.from_person_id}->{self.to_person_id}>"
