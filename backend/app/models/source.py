"""Source and Citation — evidence backing events (GEDCOM SOUR / SOURCE_CITATION)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.event import Event


class Source(Base, TimestampMixin):
    """A source record (a book, census, certificate, interview, ...) — GEDCOM ``SOUR``."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    xref_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)

    title: Mapped[str | None] = mapped_column(String(255))  # TITL
    author: Mapped[str | None] = mapped_column(String(255))  # AUTH
    publication: Mapped[str | None] = mapped_column(String(255))  # PUBL
    repository: Mapped[str | None] = mapped_column(String(255))  # REPO
    text: Mapped[str | None] = mapped_column(Text)  # TEXT (verbatim extract)

    citations: Mapped[list[Citation]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source id={self.id} {self.title!r}>"


class Citation(Base, TimestampMixin):
    """Links a :class:`Source` to an :class:`Event` (with an optional page ref)."""

    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page: Mapped[str | None] = mapped_column(String(255))  # PAGE
    note: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="citations")
    event: Mapped[Event] = relationship(back_populates="citations")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Citation source={self.source_id} event={self.event_id}>"
