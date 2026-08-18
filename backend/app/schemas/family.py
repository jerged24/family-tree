"""Pydantic schemas for Family."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FamilyBase(BaseModel):
    notes: str | None = None


class FamilyCreate(FamilyBase):
    xref_id: str | None = Field(default=None, max_length=20)


class FamilyUpdate(BaseModel):
    notes: str | None = None


class FamilyRead(FamilyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    xref_id: str | None = None
