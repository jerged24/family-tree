"""Tests for the NetworkX genealogy graph service."""

from __future__ import annotations

import pytest

from backend.app.models import (
    Family,
    PartnerType,
    Pedigree,
    Person,
    Relationship,
    RelationshipRole,
    Sex,
)
from backend.app.services import GraphService


# --------------------------------------------------------------------------- #
# Pedigree fixture
#
#   G1(M) ─┬─ G2(F)      [family FA]        G1 ─┬─ G3(F)   [family FB]
#          │                                     │
#      ┌───┴────┐                                H1        (half-sib of P1,P2)
#     P1(M)   P2(F)      full siblings
#      │        │
#   P1─┴─S1  P2─┴─S2
#      │        │
#     C1       C2        first cousins
#      │
#   (A1 adopted into P1+S1's family FC)
# --------------------------------------------------------------------------- #
@pytest.fixture
def pedigree(db):
    def person(name, sex):
        p = Person(given_name=name, surname="Fam", sex=sex)
        db.add(p)
        return p

    people = {
        "G1": person("G1", Sex.MALE),
        "G2": person("G2", Sex.FEMALE),
        "G3": person("G3", Sex.FEMALE),
        "P1": person("P1", Sex.MALE),
        "P2": person("P2", Sex.FEMALE),
        "H1": person("H1", Sex.MALE),
        "S1": person("S1", Sex.FEMALE),
        "S2": person("S2", Sex.MALE),
        "C1": person("C1", Sex.FEMALE),
        "C2": person("C2", Sex.MALE),
        "A1": person("A1", Sex.FEMALE),
    }
    db.flush()

    def family(partners, children):
        fam = Family()
        db.add(fam)
        db.flush()
        for who, ptype in partners:
            db.add(
                Relationship(
                    person_id=people[who].id,
                    family_id=fam.id,
                    role=RelationshipRole.PARTNER,
                    partner_type=ptype,
                )
            )
        for who, ped in children:
            db.add(
                Relationship(
                    person_id=people[who].id,
                    family_id=fam.id,
                    role=RelationshipRole.CHILD,
                    pedigree=ped,
                )
            )
        return fam

    family(
        [("G1", PartnerType.HUSBAND), ("G2", PartnerType.WIFE)],
        [("P1", Pedigree.BIRTH), ("P2", Pedigree.BIRTH)],
    )  # FA
    family([("G1", PartnerType.HUSBAND), ("G3", PartnerType.WIFE)], [("H1", Pedigree.BIRTH)])  # FB
    family(
        [("P1", PartnerType.HUSBAND), ("S1", PartnerType.WIFE)],
        [("C1", Pedigree.BIRTH), ("A1", Pedigree.ADOPTED)],
    )  # FC
    family([("P2", PartnerType.WIFE), ("S2", PartnerType.HUSBAND)], [("C2", Pedigree.BIRTH)])  # FD
    db.commit()
    return people


@pytest.fixture
def gs(db, pedigree):
    return GraphService(db), pedigree


# --------------------------------------------------------------- lineage
def test_graph_is_dag(gs):
    service, _ = gs
    assert service.is_dag


def test_parents_and_children(gs):
    service, ppl = gs
    assert set(service.parents(ppl["P1"].id)) == {ppl["G1"].id, ppl["G2"].id}
    assert ppl["P1"].id in service.children(ppl["G1"].id)
    assert ppl["H1"].id in service.children(ppl["G1"].id)


def test_ancestors_and_descendants(gs):
    service, ppl = gs
    assert service.ancestors(ppl["C1"].id) >= {
        ppl["P1"].id,
        ppl["S1"].id,
        ppl["G1"].id,
        ppl["G2"].id,
    }
    # A1 is adopted but still a social descendant.
    assert service.descendants(ppl["G1"].id) >= {
        ppl["P1"].id,
        ppl["P2"].id,
        ppl["C1"].id,
        ppl["C2"].id,
        ppl["H1"].id,
    }


def test_siblings_full_vs_half(gs):
    service, ppl = gs
    assert service.siblings(ppl["P1"].id, full=True) == {ppl["P2"].id}
    assert service.siblings(ppl["P1"].id) == {ppl["P2"].id, ppl["H1"].id}


def test_common_and_mrca(gs):
    service, ppl = gs
    assert service.common_ancestors(ppl["C1"].id, ppl["C2"].id) == {ppl["G1"].id, ppl["G2"].id}
    assert service.most_recent_common_ancestors(ppl["C1"].id, ppl["C2"].id) == {
        ppl["G1"].id,
        ppl["G2"].id,
    }


def test_relationship_path_cousins(gs):
    service, ppl = gs
    path = service.relationship_path(ppl["C1"].id, ppl["C2"].id)
    # C1 - P1 - (G1 or G2) - P2 - C2  → 5 nodes
    assert path is not None
    assert len(path) == 5
    assert path[0] == ppl["C1"].id and path[-1] == ppl["C2"].id


# --------------------------------------------------------------- kinship
def test_kinship_parent_child(gs):
    service, ppl = gs
    assert service.kinship_coefficient(ppl["P1"].id, ppl["C1"].id) == pytest.approx(0.25)
    assert service.coefficient_of_relationship(ppl["P1"].id, ppl["C1"].id) == pytest.approx(0.5)


def test_kinship_full_siblings(gs):
    service, ppl = gs
    assert service.kinship_coefficient(ppl["P1"].id, ppl["P2"].id) == pytest.approx(0.25)


def test_kinship_half_siblings(gs):
    service, ppl = gs
    assert service.kinship_coefficient(ppl["P1"].id, ppl["H1"].id) == pytest.approx(0.125)


def test_kinship_first_cousins(gs):
    service, ppl = gs
    assert service.kinship_coefficient(ppl["C1"].id, ppl["C2"].id) == pytest.approx(0.0625)
    assert service.coefficient_of_relationship(ppl["C1"].id, ppl["C2"].id) == pytest.approx(0.125)


def test_kinship_grandparent(gs):
    service, ppl = gs
    assert service.kinship_coefficient(ppl["G1"].id, ppl["C1"].id) == pytest.approx(0.125)


def test_adopted_child_has_zero_genetic_kinship(gs):
    service, ppl = gs
    # A1 is adopted into P1's family → no biological path.
    assert service.kinship_coefficient(ppl["P1"].id, ppl["A1"].id) == pytest.approx(0.0)
    # ...but socially still a descendant / relationship path exists.
    assert ppl["A1"].id in service.descendants(ppl["P1"].id)


def test_unrelated_spouses_have_zero_kinship(gs):
    service, ppl = gs
    assert service.kinship_coefficient(ppl["S1"].id, ppl["S2"].id) == pytest.approx(0.0)


def test_biological_parents_exclude_adoption(gs):
    service, ppl = gs
    assert service.parents(ppl["A1"].id) == [ppl["P1"].id, ppl["S1"].id] or set(
        service.parents(ppl["A1"].id)
    ) == {ppl["P1"].id, ppl["S1"].id}
    assert service.parents(ppl["A1"].id, biological=True) == []


# --------------------------------------------------------------- descriptions
def test_describe_lineal(gs):
    service, ppl = gs
    assert service.describe_relationship(ppl["P1"].id, ppl["C1"].id) == "child"
    assert service.describe_relationship(ppl["C1"].id, ppl["P1"].id) == "parent"
    assert service.describe_relationship(ppl["C1"].id, ppl["G1"].id) == "grandparent"
    assert service.describe_relationship(ppl["G1"].id, ppl["C1"].id) == "grandchild"


def test_describe_collateral(gs):
    service, ppl = gs
    assert service.describe_relationship(ppl["P1"].id, ppl["P2"].id) == "sibling"
    assert service.describe_relationship(ppl["C1"].id, ppl["C2"].id) == "1st cousin"
    # P1 is C2's aunt/uncle; C2 is P1's niece/nephew.
    assert service.describe_relationship(ppl["C2"].id, ppl["P1"].id) == "aunt/uncle"
    assert service.describe_relationship(ppl["P1"].id, ppl["C2"].id) == "niece/nephew"


def test_unknown_person_raises(gs):
    service, _ = gs
    with pytest.raises(KeyError):
        service.ancestors(999999)
