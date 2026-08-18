"""NetworkX-backed genealogy engine.

The family DAG is a :class:`networkx.DiGraph` whose nodes are ``Person`` ids and whose
directed edges run **parent → child**, derived from ``Relationship`` membership (every
PARTNER of a family points at every CHILD of that family). Each edge carries its
``pedigree`` so genetic queries can restrict themselves to *biological* (BIRTH) edges
while social queries (relationship paths) use every edge, adoption included.

Provided operations:

* lineage — ancestors / descendants / parents / children / siblings
* common ancestors and most-recent common ancestor(s)
* relationship path between two people (shortest connecting chain)
* kinship coefficient (φ) and coefficient of relationship (r), genetic — biological edges only
* a human-readable relationship description for common cases
"""

from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Person, Relationship, RelationshipRole
from backend.app.models.base import Pedigree


class GraphService:
    """Builds and queries the family DAG for one database session."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.graph: nx.DiGraph = self._build_graph()

    # ------------------------------------------------------------------ build
    def _build_graph(self) -> nx.DiGraph:
        g = nx.DiGraph()

        for person in self.db.scalars(select(Person)):
            g.add_node(
                person.id,
                name=person.display_name,
                sex=person.sex.value,
                surname=person.surname,
            )

        # Group memberships by family so we can connect each partner to each child.
        rels = self.db.scalars(select(Relationship)).all()
        by_family: dict[int, dict[str, list[Relationship]]] = {}
        for rel in rels:
            slot = by_family.setdefault(rel.family_id, {"partners": [], "children": []})
            if rel.role == RelationshipRole.PARTNER:
                slot["partners"].append(rel)
            elif rel.role == RelationshipRole.CHILD:
                slot["children"].append(rel)

        for family_id, slot in by_family.items():
            for parent in slot["partners"]:
                for child in slot["children"]:
                    g.add_edge(
                        parent.person_id,
                        child.person_id,
                        pedigree=(child.pedigree or Pedigree.BIRTH),
                        family_id=family_id,
                    )
        return g

    @property
    def is_dag(self) -> bool:
        return nx.is_directed_acyclic_graph(self.graph)

    def _require(self, person_id: int) -> None:
        if person_id not in self.graph:
            raise KeyError(f"Unknown person id: {person_id}")

    # --------------------------------------------------------------- lineage
    def parents(self, person_id: int, *, biological: bool = False) -> list[int]:
        self._require(person_id)
        preds = self.graph.predecessors(person_id)
        if biological:
            return [p for p in preds if self.graph[p][person_id]["pedigree"] == Pedigree.BIRTH]
        return list(preds)

    def children(self, person_id: int) -> list[int]:
        self._require(person_id)
        return list(self.graph.successors(person_id))

    def ancestors(self, person_id: int) -> set[int]:
        self._require(person_id)
        return nx.ancestors(self.graph, person_id)

    def descendants(self, person_id: int) -> set[int]:
        self._require(person_id)
        return nx.descendants(self.graph, person_id)

    def siblings(self, person_id: int, *, full: bool = False) -> set[int]:
        """People sharing at least one parent (``full=True`` requires both parents)."""
        self._require(person_id)
        my_parents = set(self.graph.predecessors(person_id))
        if not my_parents:
            return set()
        result: set[int] = set()
        for parent in my_parents:
            result.update(self.graph.successors(parent))
        result.discard(person_id)
        if full:
            result = {
                s for s in result if set(self.graph.predecessors(s)) & my_parents == my_parents
            }
        return result

    # ------------------------------------------------------ common ancestors
    def common_ancestors(self, a: int, b: int) -> set[int]:
        """Ancestors shared by both (strict — excludes ``a`` and ``b`` themselves)."""
        return self.ancestors(a) & self.ancestors(b)

    def most_recent_common_ancestors(self, a: int, b: int) -> set[int]:
        """The closest shared ancestor(s): common ancestors with no descendant that
        is itself a common ancestor. Includes ``a``/``b`` when one is an ancestor of
        the other (lineal relationship).
        """
        self._require(a)
        self._require(b)
        anc_a = self.ancestors(a) | {a}
        anc_b = self.ancestors(b) | {b}
        common = anc_a & anc_b
        if not common:
            return set()
        # An MRCA has none of its descendants also in the common set.
        mrca = {c for c in common if not (self.descendants(c) & common)}
        return mrca

    # ------------------------------------------------------- relationship path
    def relationship_path(self, a: int, b: int) -> list[int] | None:
        """Shortest chain of people connecting ``a`` and ``b`` (undirected), or None."""
        self._require(a)
        self._require(b)
        undirected = self.graph.to_undirected(as_view=True)
        try:
            return nx.shortest_path(undirected, a, b)
        except nx.NetworkXNoPath:
            return None

    # -------------------------------------------------------------- kinship
    def kinship_coefficient(self, a: int, b: int) -> float:
        """Genetic kinship coefficient φ (biological edges only).

        Recursive definition (Malécot), handling multiple ancestral paths and
        inbreeding correctly:

            φ(x,x) = ½ (1 + φ(father, mother))
            φ(x,y) = ½ (φ(father_x, y) + φ(mother_x, y))   [x the younger]
            φ(x,y) = 0                                      [distinct founders]
        """
        self._require(a)
        self._require(b)
        if not self.is_dag:
            raise ValueError("Kinship requires an acyclic pedigree (cycle detected).")

        order = {n: i for i, n in enumerate(nx.topological_sort(self.graph))}
        cache: dict[tuple[int, int], float] = {}

        def bio_parents(x: int) -> list[int]:
            return [
                p
                for p in self.graph.predecessors(x)
                if self.graph[p][x]["pedigree"] == Pedigree.BIRTH
            ]

        def phi(x: int, y: int) -> float:
            if x == y:
                ps = bio_parents(x)
                inbreeding = phi(ps[0], ps[1]) if len(ps) == 2 else 0.0
                return 0.5 * (1.0 + inbreeding)
            # Always expand the "younger" individual (later in topological order).
            if order[x] < order[y]:
                x, y = y, x
            key = (x, y)
            if key in cache:
                return cache[key]
            ps = bio_parents(x)
            value = 0.5 * sum(phi(p, y) for p in ps) if ps else 0.0
            cache[key] = value
            return value

        return phi(a, b)

    def coefficient_of_relationship(self, a: int, b: int) -> float:
        """Wright's coefficient of relationship r = 2φ (for non-inbred individuals)."""
        return 2.0 * self.kinship_coefficient(a, b)

    # ---------------------------------------------------------- description
    def describe_relationship(self, a: int, b: int) -> str:
        """Best-effort label for how ``b`` relates to ``a`` (common cases)."""
        self._require(a)
        self._require(b)
        if a == b:
            return "self"

        # Direct line first.
        if b in self.ancestors(a):
            gens = nx.shortest_path_length(self.graph, b, a)
            return self._lineal_label(gens, ascending=True)
        if b in self.descendants(a):
            gens = nx.shortest_path_length(self.graph, a, b)
            return self._lineal_label(gens, ascending=False)

        mrcas = self.most_recent_common_ancestors(a, b)
        if not mrcas:
            path = self.relationship_path(a, b)
            return "related (by marriage)" if path else "unrelated"

        # Collateral: use distances from each to the nearest shared ancestor.
        mrca = min(
            mrcas,
            key=lambda c: nx.shortest_path_length(self.graph, c, a)
            + nx.shortest_path_length(self.graph, c, b),
        )
        d_a = nx.shortest_path_length(self.graph, mrca, a)
        d_b = nx.shortest_path_length(self.graph, mrca, b)
        return self._collateral_label(d_a, d_b)

    @staticmethod
    def _lineal_label(gens: int, *, ascending: bool) -> str:
        base = "parent" if ascending else "child"
        if gens == 1:
            return base
        if gens == 2:
            return "grand" + base
        return "great-" * (gens - 2) + "grand" + base

    @staticmethod
    def _ordinal(n: int) -> str:
        return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")

    @classmethod
    def _collateral_label(cls, d_a: int, d_b: int) -> str:
        # d_a / d_b are generations from the common ancestor down to a / b.
        if d_a == 1 and d_b == 1:
            return "sibling"
        # aunt/uncle ↔ niece/nephew: one is a sibling of the other's ancestor.
        if min(d_a, d_b) == 1:
            steps = max(d_a, d_b) - 1
            greats = "great-" * (steps - 1)
            return f"{greats}aunt/uncle" if d_b < d_a else f"{greats}niece/nephew"
        cousin_degree = min(d_a, d_b) - 1
        removal = abs(d_a - d_b)
        label = f"{cls._ordinal(cousin_degree)} cousin"
        if removal:
            times = {1: "once", 2: "twice"}.get(removal, f"{removal} times")
            label += f" {times} removed"
        return label
