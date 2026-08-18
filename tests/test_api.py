"""End-to-end API tests via FastAPI's TestClient."""

from __future__ import annotations


def _person_index(client) -> dict[str, int]:
    """Map given_name → id from the current persons list."""
    return {p["given_name"]: p["id"] for p in client.get("/persons").json()}


# --------------------------------------------------------------------------- meta
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# --------------------------------------------------------------------------- persons CRUD
def test_person_crud_lifecycle(client):
    created = client.post("/persons", json={"given_name": "Ada", "surname": "Lovelace", "sex": "F"})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert created.json()["display_name"] == "Ada Lovelace"

    assert client.get(f"/persons/{pid}").json()["surname"] == "Lovelace"

    patched = client.patch(f"/persons/{pid}", json={"nickname": "Countess"})
    assert patched.json()["nickname"] == "Countess"

    assert client.delete(f"/persons/{pid}").status_code == 204
    assert client.get(f"/persons/{pid}").status_code == 404


def test_list_persons_filter_by_surname(client):
    client.post("/persons", json={"given_name": "A", "surname": "Ng"})
    client.post("/persons", json={"given_name": "B", "surname": "Ng"})
    client.post("/persons", json={"given_name": "C", "surname": "Other"})
    assert len(client.get("/persons", params={"surname": "Ng"}).json()) == 2


# --------------------------------------------------------------------------- families & members
def test_family_membership_builds_tree_edge(client):
    parent = client.post("/persons", json={"given_name": "Pat", "sex": "M"}).json()["id"]
    child = client.post("/persons", json={"given_name": "Kim", "sex": "F"}).json()["id"]
    fam = client.post("/families", json={}).json()["id"]

    r1 = client.post(
        f"/families/{fam}/members", json={"person_id": parent, "family_id": fam, "role": "PARTNER"}
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/families/{fam}/members", json={"person_id": child, "family_id": fam, "role": "CHILD"}
    )
    assert r2.status_code == 201
    assert r2.json()["pedigree"] == "BIRTH"  # defaulted by the validator

    tree = client.get("/tree").json()
    assert {"source": str(parent), "target": str(child), "pedigree": "BIRTH"} in tree["edges"]


def test_partner_with_pedigree_is_rejected(client):
    p = client.post("/persons", json={"given_name": "X"}).json()["id"]
    fam = client.post("/families", json={}).json()["id"]
    resp = client.post(
        f"/families/{fam}/members",
        json={"person_id": p, "family_id": fam, "role": "PARTNER", "pedigree": "BIRTH"},
    )
    assert resp.status_code == 422  # validator forbids pedigree on a PARTNER


def test_add_member_unknown_person_404(client):
    fam = client.post("/families", json={}).json()["id"]
    resp = client.post(
        f"/families/{fam}/members", json={"person_id": 99999, "family_id": fam, "role": "CHILD"}
    )
    assert resp.status_code == 404


# ----------------------------------------------------------------- GEDCOM round-trip via API
def test_gedcom_import_export_and_analysis(client, sample_ged):
    resp = client.post("/gedcom/import", files={"file": ("sample.ged", sample_ged, "text/plain")})
    assert resp.status_code == 201
    summary = resp.json()
    assert summary == {
        "persons": 4,
        "families": 1,
        "relationships": 4,
        "events": 6,
        "sources": 1,
        "warnings": [],
    }

    idx = _person_index(client)
    john, carol, david = idx["John"], idx["Carol"], idx["David"]

    # John is Carol's biological parent.
    rel = client.get(f"/tree/relationship/{john}/{carol}").json()
    assert rel["description"] == "child"
    assert rel["kinship_coefficient"] == 0.25
    assert rel["coefficient_of_relationship"] == 0.5

    # David is adopted → zero genetic kinship, but still on a social path.
    adopted = client.get(f"/tree/relationship/{john}/{david}").json()
    assert adopted["kinship_coefficient"] == 0.0
    assert adopted["path"] is not None

    # Export returns valid GEDCOM text.
    exported = client.get("/gedcom/export")
    assert exported.status_code == 200
    body = exported.text
    assert body.startswith("0 HEAD") and body.rstrip().endswith("0 TRLR")
    assert "2 PEDI adopted" in body


def test_tree_subtree_modes(client, sample_ged):
    client.post("/gedcom/import", files={"file": ("s.ged", sample_ged, "text/plain")})
    carol = _person_index(client)["Carol"]

    ancestors = client.get(f"/tree/person/{carol}", params={"mode": "ancestors"}).json()
    names = {n["name"] for n in ancestors["nodes"]}
    assert "Carol Smith" in names
    assert "John Smith" in names and "Mary Jones" in names
    assert "David Smith Jr" not in names  # a sibling, not an ancestor


def test_subtree_unknown_person_404(client):
    assert client.get("/tree/person/424242").status_code == 404


def test_export_version_param(client, sample_ged):
    client.post("/gedcom/import", files={"file": ("s.ged", sample_ged, "text/plain")})
    body = client.get("/gedcom/export", params={"version": "7.0"}).text
    assert "2 VERS 7.0" in body
