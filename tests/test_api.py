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


def test_person_memberships(client):
    parent = client.post("/persons", json={"given_name": "Pat"}).json()["id"]
    child = client.post("/persons", json={"given_name": "Kim"}).json()["id"]
    fam = client.post("/families", json={}).json()["id"]
    client.post(
        f"/families/{fam}/members", json={"person_id": parent, "family_id": fam, "role": "PARTNER"}
    )
    client.post(
        f"/families/{fam}/members", json={"person_id": child, "family_id": fam, "role": "CHILD"}
    )

    pm = client.get(f"/persons/{parent}/memberships").json()
    assert len(pm) == 1 and pm[0]["role"] == "PARTNER" and pm[0]["family_id"] == fam
    cm = client.get(f"/persons/{child}/memberships").json()
    assert cm[0]["role"] == "CHILD"
    assert client.get("/persons/999999/memberships").status_code == 404


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
        "media": 0,
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


def test_export_privacy_masks_living(client):
    client.post("/persons", json={"given_name": "Alive", "surname": "Now"})
    dead = client.post("/persons", json={"given_name": "Gone", "surname": "Past"}).json()["id"]
    client.post("/events", json={"type": "DEAT", "person_id": dead, "date_value": "1950"})

    masked = client.get("/gedcom/export", params={"privacy": "living"}).text
    assert "Living /Living/" in masked
    assert "Alive" not in masked  # living person's name hidden
    assert "Gone" in masked  # deceased person still shown

    plain = client.get("/gedcom/export").text
    assert "Alive" in plain  # no masking by default


# --------------------------------------------------------------- sample seed + merge
def test_load_sample_endpoint_is_idempotent(client):
    first = client.post("/gedcom/sample").json()
    assert first["persons"] == 9 and first["families"] == 3
    # Calling again adds nothing (merge by xref).
    second = client.post("/gedcom/sample").json()
    assert (second["persons"], second["families"], second["relationships"]) == (0, 0, 0)
    assert len(client.get("/persons").json()) == 9


def test_import_merge_mode_no_duplicate(client, sample_ged):
    client.post("/gedcom/import", files={"file": ("s.ged", sample_ged, "text/plain")})
    # Default mode is merge → second import of the same file must not error or duplicate.
    r = client.post("/gedcom/import", files={"file": ("s.ged", sample_ged, "text/plain")})
    assert r.status_code == 201
    assert r.json()["persons"] == 0
    assert len(client.get("/persons").json()) == 4


# --------------------------------------------------------------- media
def test_media_crud_and_tree_photo(client):
    pid = client.post("/persons", json={"given_name": "Ivy", "sex": "F"}).json()["id"]

    created = client.post(
        f"/persons/{pid}/media",
        json={"url": "https://img/ivy.png", "caption": "Ivy", "is_primary": True},
    )
    assert created.status_code == 201
    media_id = created.json()["id"]

    assert client.get(f"/persons/{pid}/media").json()[0]["url"] == "https://img/ivy.png"

    # The photo surfaces in the tree DAG JSON.
    node = next(n for n in client.get("/tree").json()["nodes"] if n["id"] == str(pid))
    assert node["photo_url"] == "https://img/ivy.png"

    assert client.delete(f"/media/{media_id}").status_code == 204
    assert client.get(f"/persons/{pid}/media").json() == []


def test_add_media_unknown_person_404(client):
    resp = client.post("/persons/99999/media", json={"url": "https://x/y.png"})
    assert resp.status_code == 404


def test_only_one_primary_photo(client):
    pid = client.post("/persons", json={"given_name": "Jo"}).json()["id"]
    client.post(f"/persons/{pid}/media", json={"url": "https://x/1.png", "is_primary": True})
    client.post(f"/persons/{pid}/media", json={"url": "https://x/2.png", "is_primary": True})
    media = client.get(f"/persons/{pid}/media").json()
    assert sum(1 for m in media if m["is_primary"]) == 1
    assert next(m for m in media if m["is_primary"])["url"] == "https://x/2.png"


def test_set_media_focal_point(client):
    pid = client.post("/persons", json={"given_name": "Fo"}).json()["id"]
    mid = client.post(
        f"/persons/{pid}/media", json={"url": "https://x/f.png", "is_primary": True}
    ).json()["id"]

    r = client.patch(f"/media/{mid}", json={"focal_x": 30, "focal_y": 70})
    assert r.status_code == 200
    assert r.json()["focal_x"] == 30 and r.json()["focal_y"] == 70

    node = next(n for n in client.get("/tree").json()["nodes"] if n["id"] == str(pid))
    assert node["photo_focal_x"] == 30 and node["photo_focal_y"] == 70

    assert client.patch(f"/media/{mid}", json={"focal_x": 150}).status_code == 422  # out of range


def test_set_media_primary_via_patch(client):
    pid = client.post("/persons", json={"given_name": "Mo"}).json()["id"]
    first = client.post(
        f"/persons/{pid}/media", json={"url": "https://x/a.png", "is_primary": True}
    )
    second = client.post(f"/persons/{pid}/media", json={"url": "https://x/b.png"}).json()["id"]

    # Promote the second to primary; the first must drop.
    resp = client.patch(f"/media/{second}", json={"is_primary": True})
    assert resp.status_code == 200 and resp.json()["is_primary"] is True
    media = {m["id"]: m["is_primary"] for m in client.get(f"/persons/{pid}/media").json()}
    assert media[second] is True and media[first.json()["id"]] is False
    assert client.patch("/media/999999", json={"is_primary": True}).status_code == 404
