"""Pydantic schemas for Association (godparent and other non-lineage links)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.app.models.base import AssociationType


class AssociationCreate(BaseModel):
    to_person_id: int
    type: AssociationType = AssociationType.GODPARENT


class AssociationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_person_id: int
    to_person_id: int
    type: AssociationType
