"""Pydantic schemas for Person."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.base import Sex


class PersonBase(BaseModel):
    given_name: str | None = Field(default=None, max_length=200)
    surname: str | None = Field(default=None, max_length=200)
    name_prefix: str | None = Field(default=None, max_length=50)
    name_suffix: str | None = Field(default=None, max_length=50)
    nickname: str | None = Field(default=None, max_length=100)
    sex: Sex = Sex.UNKNOWN
    notes: str | None = None


class PersonCreate(PersonBase):
    xref_id: str | None = Field(default=None, max_length=20)


class PersonUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    given_name: str | None = None
    surname: str | None = None
    name_prefix: str | None = None
    name_suffix: str | None = None
    nickname: str | None = None
    sex: Sex | None = None
    notes: str | None = None


class PersonRead(PersonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    xref_id: str | None = None
    display_name: str


class DuplicatePair(BaseModel):
    """A candidate duplicate: two people plus why they were flagged."""

    reason: str
    birth_year: int | None = None
    a: PersonRead
    b: PersonRead
