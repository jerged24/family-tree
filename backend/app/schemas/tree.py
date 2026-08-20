"""DAG JSON contract served to the D3 / d3-dag frontend.

``d3-dag`` consumes a node list plus explicit parent links. Each node carries a
``parentIds`` array so the layout can be built directly, with richer display
fields alongside.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.models.base import Sex


class DagNode(BaseModel):
    id: str  # stringified person id (d3-dag prefers string ids)
    name: str
    sex: Sex
    birth: str | None = None  # display date string, if known
    death: str | None = None
    photo_url: str | None = None  # primary photo, if any
    photo_focal_x: float = 50.0  # focal point (percent) for avatar cropping
    photo_focal_y: float = 50.0
    parentIds: list[str] = []  # ids of parent nodes (the DAG links)


class DagEdge(BaseModel):
    """Explicit parent→child edge, provided for renderers that prefer a link list."""

    source: str
    target: str
    pedigree: str | None = None  # BIRTH / ADOPTED / ...


class AssociationEdge(BaseModel):
    """A non-lineage link (e.g. godparent) between two people, rendered as an overlay."""

    source: str  # from person id (e.g. the godparent)
    target: str  # to person id (e.g. the godchild)
    type: str


class TreeGraph(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]
    associations: list[AssociationEdge] = []


class RelationshipAnalysis(BaseModel):
    """Result of analysing how two people are related."""

    person_a: int
    person_b: int
    path: list[int] | None  # shortest connecting chain of person ids
    most_recent_common_ancestors: list[int]
    kinship_coefficient: float  # φ — genetic (biological edges only)
    coefficient_of_relationship: float  # r = 2φ
    description: str  # e.g. "1st cousin", "grandparent"


class ImportSummary(BaseModel):
    """Counts returned after a GEDCOM import."""

    persons: int
    families: int
    relationships: int
    events: int
    sources: int
    media: int = 0
    warnings: list[str] = []


class CsvImportSummary(BaseModel):
    """Counts returned after a spreadsheet (CSV) import."""

    persons: int
    stubs: int  # name-only people created for referenced-but-unlisted parents/spouses
    families: int
    relationships: int
    events: int
    warnings: list[str] = []
