"""Photo upload + serving tests."""

from __future__ import annotations

_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000155a2b4ee0000000049454e44ae426082"
)


def test_upload_creates_media_and_serves_file(client):
    pid = client.post("/persons", json={"given_name": " Imo", "sex": "F"}).json()["id"]
    resp = client.post(
        f"/persons/{pid}/media/upload",
        files={"file": ("me.png", _PNG_1x1, "image/png")},
        data={"is_primary": "true"},
    )
    assert resp.status_code == 201
    url = resp.json()["url"]
    assert url.startswith("/media/files/") and url.endswith(".png")

    served = client.get(url)
    assert served.status_code == 200
    assert served.content == _PNG_1x1
