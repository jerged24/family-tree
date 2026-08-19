"""Same-origin static serving of the SPA."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_serves_spa():
    from backend.app.main import app

    body = TestClient(app).get("/").text
    assert "Family Tree" in body  # index.html title/header


def test_boots_with_prod_style_env(tmp_path):
    """Boot the app in a fresh interpreter with prod-style env and hit /health.

    This runs in a subprocess rather than reloading backend.app.config /
    database / main in-process: importlib.reload(database) mints a new
    get_db function object, but router modules already imported earlier in
    the test session keep their Depends(get_db) bound to the *old* one, so
    conftest.py's dependency-override (keyed on the post-reload get_db) stops
    matching for the rest of the suite and later tests hit a real, tableless
    engine. A subprocess gives a truly clean boot (closer to a real deploy
    anyway) without leaking reloaded modules into the shared test process.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
    env["MEDIA_DIR"] = str(tmp_path / "media")
    env["ADMIN_PASSWORD"] = "x"
    env["SECRET_KEY"] = "y"
    script = (
        "import json\n"
        "from fastapi.testclient import TestClient\n"
        "from backend.app.main import app\n"
        "print(json.dumps(TestClient(app).get('/health').json()))\n"
    )
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout.strip()) == {"status": "ok"}
