"""Pydantic schemas for Source and Citation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SourceBase(BaseModel):
    title: str | None = None
    author: str | None = None
    publication: str | None = None
    repository: str | None = None
    text: str | None = None


class SourceCreate(SourceBase):
    xref_id: str | None = Field(default=None, max_length=20)


class SourceRead(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    xref_id: str | None = None


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    event_id: int
    page: str | None = None
    note: str | None = None
