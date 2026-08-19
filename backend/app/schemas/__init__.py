"""Pydantic v2 request/response schemas."""

from backend.app.schemas.association import AssociationCreate, AssociationRead
from backend.app.schemas.event import EventCreate, EventRead, EventUpdate
from backend.app.schemas.family import FamilyCreate, FamilyRead, FamilyUpdate
from backend.app.schemas.media import MediaCreate, MediaRead, MediaUpdate
from backend.app.schemas.person import (
    DuplicatePair,
    PersonCreate,
    PersonRead,
    PersonUpdate,
)
from backend.app.schemas.relationship import RelationshipCreate, RelationshipRead
from backend.app.schemas.source import CitationRead, SourceCreate, SourceRead
from backend.app.schemas.tree import (
    DagEdge,
    DagNode,
    ImportSummary,
    RelationshipAnalysis,
    TreeGraph,
)

__all__ = [
    "PersonCreate",
    "PersonRead",
    "PersonUpdate",
    "DuplicatePair",
    "FamilyCreate",
    "FamilyRead",
    "FamilyUpdate",
    "RelationshipCreate",
    "RelationshipRead",
    "EventCreate",
    "EventRead",
    "EventUpdate",
    "SourceCreate",
    "SourceRead",
    "CitationRead",
    "MediaCreate",
    "MediaRead",
    "MediaUpdate",
    "AssociationCreate",
    "AssociationRead",
    "DagNode",
    "DagEdge",
    "TreeGraph",
    "RelationshipAnalysis",
    "ImportSummary",
]
