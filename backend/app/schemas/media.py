"""Pydantic schemas for Media."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MediaCreate(BaseModel):
    url: str = Field(max_length=1024)
    caption: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)
    is_primary: bool = False


class MediaUpdate(BaseModel):
    is_primary: bool | None = None
    caption: str | None = Field(default=None, max_length=255)
    focal_x: float | None = Field(default=None, ge=0, le=100)
    focal_y: float | None = Field(default=None, ge=0, le=100)


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    url: str
    caption: str | None = None
    mime_type: str | None = None
    is_primary: bool
    focal_x: float = 50.0
    focal_y: float = 50.0
