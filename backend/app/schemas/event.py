"""Pydantic schemas for Event."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from backend.app.models.base import EventType


class EventBase(BaseModel):
    type: EventType
    date_value: str | None = None
    date_sort: date | None = None
    place: str | None = None
    description: str | None = None


class EventCreate(EventBase):
    person_id: int | None = None
    family_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one_subject(self) -> EventCreate:
        if (self.person_id is None) == (self.family_id is None):
            raise ValueError("Provide exactly one of person_id or family_id")
        return self


class EventUpdate(BaseModel):
    type: EventType | None = None
    date_value: str | None = None
    date_sort: date | None = None
    place: str | None = None
    description: str | None = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int | None = None
    family_id: int | None = None
