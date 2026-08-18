"""Pydantic schemas for Relationship (Person↔Family membership)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from backend.app.models.base import PartnerType, Pedigree, RelationshipRole


class RelationshipCreate(BaseModel):
    person_id: int
    family_id: int
    role: RelationshipRole
    partner_type: PartnerType | None = None
    pedigree: Pedigree | None = None

    @model_validator(mode="after")
    def _check_role_fields(self) -> RelationshipCreate:
        """PARTNER rows carry a partner_type; CHILD rows carry a pedigree (default BIRTH)."""
        if self.role == RelationshipRole.PARTNER:
            if self.pedigree is not None:
                raise ValueError("pedigree is not valid on a PARTNER relationship")
            if self.partner_type is None:
                self.partner_type = PartnerType.SPOUSE
        elif self.role == RelationshipRole.CHILD:
            if self.partner_type is not None:
                raise ValueError("partner_type is not valid on a CHILD relationship")
            if self.pedigree is None:
                self.pedigree = Pedigree.BIRTH
        return self


class RelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    family_id: int
    role: RelationshipRole
    partner_type: PartnerType | None = None
    pedigree: Pedigree | None = None
