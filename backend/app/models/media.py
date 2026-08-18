"""Media — a photo or document attached to a person (GEDCOM OBJE)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.person import Person


class Media(Base, TimestampMixin):
    """An image or document linked to a person (GEDCOM ``OBJE`` / ``FILE``)."""

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)  # link or data: URI
    caption: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    person: Mapped[Person] = relationship(back_populates="media")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Media id={self.id} person={self.person_id} url={self.url!r}>"
