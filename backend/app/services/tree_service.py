"""Assemble D3/d3-dag-ready JSON from the family graph plus display data."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Association, Event, EventType, Media, Relationship
from backend.app.models.base import Pedigree, RelationshipRole, Sex
from backend.app.schemas.tree import (
    AssociationEdge,
    DagEdge,
    DagNode,
    FamilyChild,
    FamilyUnion,
    TreeGraph,
)
from backend.app.services.graph_service import GraphService


def _families(db: Session, person_ids: set[int]) -> list[FamilyUnion]:
    """Families with at least one visible member → partners + children (for unions)."""
    by_family: dict[int, dict[str, list]] = {}
    for r in db.scalars(select(Relationship)):
        slot = by_family.setdefault(r.family_id, {"partners": [], "children": []})
        if r.role == RelationshipRole.PARTNER:
            slot["partners"].append(r.person_id)
        elif r.role == RelationshipRole.CHILD:
            slot["children"].append((r.person_id, (r.pedigree or Pedigree.BIRTH)))
    out: list[FamilyUnion] = []
    for fid, slot in by_family.items():
        partners = [str(p) for p in slot["partners"] if p in person_ids]
        children = [
            FamilyChild(id=str(c), pedigree=ped.value)
            for c, ped in slot["children"]
            if c in person_ids
        ]
        if partners or children:
            out.append(FamilyUnion(id=str(fid), partners=partners, children=children))
    return out


def _display_dates(db: Session, person_ids: set[int]) -> dict[int, tuple[str | None, str | None]]:
    """Map person id → (birth date string, death date string) for labelling nodes."""
    out: dict[int, tuple[str | None, str | None]] = {}
    if not person_ids:
        return out
    rows = db.scalars(
        select(Event).where(
            Event.person_id.in_(person_ids),
            Event.type.in_([EventType.BIRTH, EventType.DEATH]),
        )
    ).all()
    for ev in rows:
        birth, death = out.get(ev.person_id, (None, None))
        if ev.type == EventType.BIRTH:
            birth = ev.date_value
        else:
            death = ev.date_value
        out[ev.person_id] = (birth, death)
    return out


def _photos(db: Session, person_ids: set[int]) -> dict[int, tuple[str, float, float]]:
    """Map person id → (primary photo URL, focal_x, focal_y), first attached as fallback."""
    out: dict[int, tuple[str, float, float]] = {}
    if not person_ids:
        return out
    rows = db.scalars(select(Media).where(Media.person_id.in_(person_ids)).order_by(Media.id)).all()
    for m in rows:
        # First row for a person seeds it; a later primary overrides.
        if m.person_id not in out or m.is_primary:
            out[m.person_id] = (m.url, m.focal_x, m.focal_y)
    return out


def build_tree_graph(db: Session, root_id: int | None = None, mode: str = "full") -> TreeGraph:
    """Build the DAG JSON.

    ``mode`` (only when ``root_id`` is given): ``ancestors`` / ``descendants`` /
    ``full`` (both directions around the root).
    """
    gs = GraphService(db)
    graph = gs.graph

    if root_id is not None:
        gs._require(root_id)
        if mode == "ancestors":
            keep = gs.ancestors(root_id) | {root_id}
        elif mode == "descendants":
            keep = gs.descendants(root_id) | {root_id}
        else:
            keep = gs.ancestors(root_id) | gs.descendants(root_id) | {root_id}
        view = graph.subgraph(keep)
    else:
        view = graph

    node_ids = set(view.nodes)
    dates = _display_dates(db, node_ids)
    photos = _photos(db, node_ids)

    nodes: list[DagNode] = []
    for nid, attrs in view.nodes(data=True):
        birth, death = dates.get(nid, (None, None))
        photo = photos.get(nid)
        nodes.append(
            DagNode(
                id=str(nid),
                name=attrs.get("name", str(nid)),
                sex=Sex(attrs.get("sex", Sex.UNKNOWN.value)),
                birth=birth,
                death=death,
                photo_url=photo[0] if photo else None,
                photo_focal_x=photo[1] if photo else 50.0,
                photo_focal_y=photo[2] if photo else 50.0,
                parentIds=[str(p) for p in view.predecessors(nid)],
            )
        )

    edges: list[DagEdge] = []
    for u, v, data in view.edges(data=True):
        pedigree = data.get("pedigree", Pedigree.BIRTH)
        edges.append(DagEdge(source=str(u), target=str(v), pedigree=pedigree.value))

    associations = _associations(db, node_ids)
    families = _families(db, node_ids)

    return TreeGraph(nodes=nodes, edges=edges, associations=associations, families=families)


def _associations(db: Session, person_ids: set[int]) -> list[AssociationEdge]:
    """Associations (e.g. godparent links) where both endpoints are visible."""
    if not person_ids:
        return []
    rows = db.scalars(
        select(Association).where(
            Association.from_person_id.in_(person_ids),
            Association.to_person_id.in_(person_ids),
        )
    ).all()
    return [
        AssociationEdge(source=str(a.from_person_id), target=str(a.to_person_id), type=a.type.value)
        for a in rows
    ]
