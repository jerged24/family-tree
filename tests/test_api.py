"""End-to-end API tests via FastAPI's TestClient."""

from __future__ import annotations


def _person_index(client) -> dict[str, int]:
    """Map given_name → id from the current persons list."""
    return {p["given_name"]: p["id"] for p in client.get("/persons").json()}


# --------------------------------------------------------------------------- meta
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_spa_is_served_with_no_cache(client):
    """The SPA shell must revalidate each load so deploys aren't hidden by the cache."""
    r = client.get("/index.html")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"


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


def test_associations_godparent(client):
    a = client.post("/persons", json={"given_name": "Ana"}).json()["id"]
    b = client.post("/persons", json={"given_name": "Ben"}).json()["id"]

    r = client.post(f"/persons/{a}/associations", json={"to_person_id": b, "type": "GODPARENT"})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert r.json()["from_person_id"] == a and r.json()["to_person_id"] == b

    # Both people list the link; and it surfaces on the tree JSON.
    assert len(client.get(f"/persons/{a}/associations").json()) == 1
    assert len(client.get(f"/persons/{b}/associations").json()) == 1
    tree = client.get("/tree").json()
    assert {"source": str(a), "target": str(b), "type": "GODPARENT"} in tree["associations"]

    assert client.post(f"/persons/{a}/associations", json={"to_person_id": a}).status_code == 400
    assert client.delete(f"/associations/{aid}").status_code == 204
    assert client.get(f"/persons/{a}/associations").json() == []


def test_find_and_merge_duplicates(client):
    # Two "John Smith"s: one with a birth year, one without → flagged as a pair.
    keep = client.post("/persons", json={"given_name": "John", "surname": "Smith"}).json()["id"]
    dup = client.post(
        "/persons", json={"given_name": "John", "surname": "Smith", "sex": "M"}
    ).json()["id"]
    client.post("/events", json={"type": "BIRT", "person_id": dup, "date_value": "1900"})
    # An unrelated person must not be flagged.
    client.post("/persons", json={"given_name": "Mary", "surname": "Jones"})

    pairs = client.get("/persons/duplicates").json()
    assert len(pairs) == 1
    ids = {pairs[0]["a"]["id"], pairs[0]["b"]["id"]}
    assert ids == {keep, dup}
    assert "missing a birth year" in pairs[0]["reason"]

    # Give the duplicate a family membership and a photo, then merge it into keep.
    fam = client.post("/families", json={}).json()["id"]
    client.post(
        f"/families/{fam}/members", json={"person_id": dup, "family_id": fam, "role": "CHILD"}
    )
    client.post(f"/persons/{dup}/media", json={"url": "https://x/j.png", "is_primary": True})

    merged = client.post(f"/persons/{keep}/merge/{dup}")
    assert merged.status_code == 200
    assert merged.json()["sex"] == "M"  # blank field on keep filled from the merged twin

    assert client.get(f"/persons/{dup}").status_code == 404  # loser is gone
    assert client.get(f"/persons/{keep}/media").json()[0]["url"] == "https://x/j.png"  # photo moved
    assert (
        client.get(f"/persons/{keep}/memberships").json()[0]["family_id"] == fam
    )  # membership moved
    assert client.get(f"/persons/{keep}/events").json()[0]["date_value"] == "1900"  # event moved
    assert client.get("/persons/duplicates").json() == []  # nothing left to merge

    assert client.post(f"/persons/{keep}/merge/{keep}").status_code == 400  # self-merge rejected


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


def test_tree_exposes_childless_couple_as_a_family(client):
    """A childless couple has no parent-child edges but is exposed as a family (union)."""
    a = client.post("/persons", json={"given_name": "Al"}).json()["id"]
    b = client.post("/persons", json={"given_name": "Bo"}).json()["id"]
    fam = client.post("/families", json={}).json()["id"]
    client.post(
        f"/families/{fam}/members", json={"person_id": a, "family_id": fam, "role": "PARTNER"}
    )
    client.post(
        f"/families/{fam}/members", json={"person_id": b, "family_id": fam, "role": "PARTNER"}
    )

    tree = client.get("/tree").json()
    assert tree["edges"] == []  # no children → no parent-child lines (the reported gap)
    fams = tree["families"]
    assert len(fams) == 1
    assert set(fams[0]["partners"]) == {str(a), str(b)} and fams[0]["children"] == []


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


# --------------------------------------------------------------- public share links
def test_share_create_and_public_view(client):
    html = "<!doctype html><title>Fam</title><body>Hello family</body>"
    r = client.post("/shares", content=html, headers={"Content-Type": "text/html"})
    assert r.status_code == 201
    path = r.json()["path"]
    assert path.startswith("/s/")

    # The share is viewable with NO login (public), rendered inline (not a download).
    view = client.get(path)
    assert view.status_code == 200
    assert view.headers["content-type"].startswith("text/html")
    assert "content-disposition" not in view.headers  # inline, so it renders on a phone
    assert "Hello family" in view.text

    assert client.post("/shares", content=b"").status_code == 400  # empty rejected
    assert client.get("/s/does-not-exist-token").status_code == 404
    assert client.get("/s/..%2f..%2fetc").status_code == 404  # path traversal rejected


# --------------------------------------------------------------- reset / start over
def test_reset_clears_everything(client):
    john = client.post("/persons", json={"given_name": "John", "surname": "Smith"}).json()["id"]
    kid = client.post("/persons", json={"given_name": "Cara", "surname": "Smith"}).json()["id"]
    fam = client.post("/families", json={}).json()["id"]
    client.post(
        f"/families/{fam}/members", json={"person_id": john, "family_id": fam, "role": "PARTNER"}
    )
    client.post(
        f"/families/{fam}/members", json={"person_id": kid, "family_id": fam, "role": "CHILD"}
    )
    client.post("/events", json={"type": "BIRT", "person_id": john, "date_value": "1900"})
    client.post(f"/persons/{john}/media", json={"url": "https://x/j.png"})
    client.post(f"/persons/{john}/associations", json={"to_person_id": kid, "type": "GODPARENT"})

    r = client.post("/admin/reset")
    assert r.status_code == 200
    assert r.json()["deleted_people"] == 2

    assert client.get("/persons").json() == []
    tree = client.get("/tree").json()
    assert tree["nodes"] == [] and tree["edges"] == [] and tree["associations"] == []
    # The schema is intact — you can start fresh right away.
    assert client.post("/persons", json={"given_name": "New"}).status_code == 201


# --------------------------------------------------------------- slideshow export
def test_slideshow_export(client):
    john = client.post("/persons", json={"given_name": "John", "surname": "Smith"}).json()["id"]
    kid = client.post("/persons", json={"given_name": "Cara", "surname": "Smith"}).json()["id"]
    client.post(
        "/events", json={"type": "BIRT", "person_id": john, "date_value": "1900", "place": "Cebu"}
    )
    fam = client.post("/families", json={}).json()["id"]
    client.post(
        f"/families/{fam}/members", json={"person_id": john, "family_id": fam, "role": "PARTNER"}
    )
    client.post(
        f"/families/{fam}/members", json={"person_id": kid, "family_id": fam, "role": "CHILD"}
    )

    r = client.get("/slideshow")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers.get("content-disposition", "").startswith("attachment")
    body = r.text
    assert "<!doctype html>" in body.lower()
    assert "John Smith" in body and "Cara Smith" in body  # a slide per person
    assert "Born in Cebu" in body  # birthplace rendered
    assert "Children" in body  # relationship row derived from the family
    assert 'id="bgm"' in body and 'const BGM = "";' in body  # autoplay + music hooks present


def test_slideshow_anchor_orders_paternal_then_maternal(client):
    # Anchor (kid) with a paternal grandfather and a maternal grandmother.
    gf = client.post("/persons", json={"given_name": "Grandpa", "sex": "M"}).json()["id"]
    gm = client.post("/persons", json={"given_name": "Grandma", "sex": "F"}).json()["id"]
    dad = client.post("/persons", json={"given_name": "Dad", "sex": "M"}).json()["id"]
    mom = client.post("/persons", json={"given_name": "Mom", "sex": "F"}).json()["id"]
    kid = client.post("/persons", json={"given_name": "Kid", "sex": "F"}).json()["id"]

    fam_dad = client.post("/families", json={}).json()["id"]  # Grandpa → Dad
    client.post(
        f"/families/{fam_dad}/members",
        json={"person_id": gf, "family_id": fam_dad, "role": "PARTNER"},
    )
    client.post(
        f"/families/{fam_dad}/members",
        json={"person_id": dad, "family_id": fam_dad, "role": "CHILD"},
    )
    fam_mom = client.post("/families", json={}).json()["id"]  # Grandma → Mom
    client.post(
        f"/families/{fam_mom}/members",
        json={"person_id": gm, "family_id": fam_mom, "role": "PARTNER"},
    )
    client.post(
        f"/families/{fam_mom}/members",
        json={"person_id": mom, "family_id": fam_mom, "role": "CHILD"},
    )
    fam_kid = client.post("/families", json={}).json()["id"]  # Dad + Mom → Kid
    client.post(
        f"/families/{fam_kid}/members",
        json={"person_id": dad, "family_id": fam_kid, "role": "PARTNER"},
    )
    client.post(
        f"/families/{fam_kid}/members",
        json={"person_id": mom, "family_id": fam_kid, "role": "PARTNER"},
    )
    client.post(
        f"/families/{fam_kid}/members",
        json={"person_id": kid, "family_id": fam_kid, "role": "CHILD"},
    )

    body = client.get("/slideshow", params={"anchor": kid, "seconds": 8}).text
    # Index each person's own slide heading (names also appear in relationship rows).
    order = [body.index(f"<h2>{n}</h2>") for n in ("Grandpa", "Dad", "Grandma", "Mom", "Kid")]
    assert order == sorted(order)  # paternal line, then maternal line, then the anchor
    assert "const INTERVAL = 8000;" in body  # speed honored


# --------------------------------------------------------------- spreadsheet (CSV) import
def _csv_import(client, text: str):
    return client.post(
        "/gedcom/import-csv", files={"file": ("intake.csv", text.encode("utf-8"), "text/csv")}
    )


def test_csv_import_builds_families(client):
    csv_text = (
        "First name,Last name,Sex,Date of birth,Birth place,Date of death,"
        "Father's full name,Mother's full name,Spouse's full name,Notes\n"
        "Juan,Gedorio,M,1940,Cebu,2010,,,Ana Gedorio,\n"
        "Ana,Gedorio,F,1945,,,,,Juan Gedorio,\n"
        "Maria,Gedorio,F,1970,,,Juan Gedorio,Ana Gedorio,Pedro Cruz,the eldest\n"
    )
    r = _csv_import(client, csv_text)
    assert r.status_code == 201
    s = r.json()
    # 3 rows + 1 stub (Pedro Cruz, referenced but no row of his own).
    assert s["persons"] == 3 and s["stubs"] == 1
    # One couple family (Juan+Ana, reused for their child + each spouse column) + Maria&Pedro.
    assert s["families"] == 2
    assert s["relationships"] == 5  # Juan/Ana partners, Maria child, Maria/Pedro partners
    assert s["events"] == 4  # Juan birth+death, Ana birth, Maria birth
    assert s["warnings"] == []

    idx = _person_index(client)
    assert "Pedro" in idx  # stub created and named
    tree = client.get("/tree").json()
    juan, ana, maria = idx["Juan"], idx["Ana"], idx["Maria"]
    assert {"source": str(juan), "target": str(maria), "pedigree": "BIRTH"} in tree["edges"]
    assert {"source": str(ana), "target": str(maria), "pedigree": "BIRTH"} in tree["edges"]
    assert client.get(f"/persons/{maria}").json()["notes"] == "the eldest"  # Notes column stored


def test_csv_import_ambiguous_name_warns(client):
    csv_text = (
        "First name,Last name,Father's full name\n"
        "John,Doe,\n"
        "John,Doe,\n"  # a second identical name → ambiguous target
        "Junior,Doe,John Doe\n"
    )
    s = _csv_import(client, csv_text).json()
    assert s["persons"] == 3 and s["stubs"] == 0
    assert s["relationships"] == 0  # ambiguous father left unlinked
    assert len(s["warnings"]) == 1 and "matches 2 people" in s["warnings"][0]


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
