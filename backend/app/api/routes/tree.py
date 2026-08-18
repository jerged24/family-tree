"""DAG JSON for D3/d3-dag, plus relationship analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas import RelationshipAnalysis, TreeGraph
from backend.app.services.graph_service import GraphService
from backend.app.services.tree_service import build_tree_graph

router = APIRouter(prefix="/tree", tags=["tree"])


@router.get("", response_model=TreeGraph)
def full_tree(db: Session = Depends(get_db)) -> TreeGraph:
    """The entire family DAG as node/edge JSON."""
    return build_tree_graph(db)


@router.get("/person/{person_id}", response_model=TreeGraph)
def subtree(
    person_id: int,
    mode: str = Query("full", pattern="^(full|ancestors|descendants)$"),
    db: Session = Depends(get_db),
) -> TreeGraph:
    """DAG limited to a person's ancestors, descendants, or both."""
    try:
        return build_tree_graph(db, root_id=person_id, mode=mode)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/relationship/{person_a}/{person_b}", response_model=RelationshipAnalysis)
def analyse_relationship(
    person_a: int, person_b: int, db: Session = Depends(get_db)
) -> RelationshipAnalysis:
    """How are two people related — path, common ancestors, kinship, and a label."""
    gs = GraphService(db)
    try:
        path = gs.relationship_path(person_a, person_b)
        mrca = gs.most_recent_common_ancestors(person_a, person_b)
        kinship = gs.kinship_coefficient(person_a, person_b)
        description = gs.describe_relationship(person_a, person_b)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return RelationshipAnalysis(
        person_a=person_a,
        person_b=person_b,
        path=path,
        most_recent_common_ancestors=sorted(mrca),
        kinship_coefficient=kinship,
        coefficient_of_relationship=2.0 * kinship,
        description=description,
    )
