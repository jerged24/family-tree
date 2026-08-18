"""ORM models. Importing this package registers every mapper on ``Base.metadata``."""

from backend.app.models.base import (
    Base,
    EventType,
    PartnerType,
    Pedigree,
    RelationshipRole,
    Sex,
)
from backend.app.models.event import Event
from backend.app.models.family import Family
from backend.app.models.person import Person
from backend.app.models.relationship import Relationship
from backend.app.models.source import Citation, Source

__all__ = [
    "Base",
    "Sex",
    "RelationshipRole",
    "PartnerType",
    "Pedigree",
    "EventType",
    "Person",
    "Family",
    "Relationship",
    "Event",
    "Source",
    "Citation",
]
