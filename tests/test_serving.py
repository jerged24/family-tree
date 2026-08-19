"""Same-origin static serving of the SPA."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_serves_spa():
    from backend.app.main import app

    body = TestClient(app).get("/").text
    assert "Family Tree" in body  # index.html title/header
