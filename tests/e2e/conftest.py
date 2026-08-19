"""Fixtures for browser (e2e) tests: an isolated live API server.

Each test gets its own uvicorn API (fresh temp SQLite DB) on an ephemeral port.
The API server also serves the SPA itself (``backend/app/main.py`` mounts
``frontend/`` at ``/``), so Playwright is pointed at the API's own
``/index.html`` rather than a separate static server. This keeps the login
session cookie same-origin: a cross-port static server would make the cookie
cross-site for ``SameSite=Lax`` purposes in some browser/CORS configurations,
which is fragile to rely on. Tests opt into data with ``live.seed()``, which
authenticates via the admin login endpoint before importing.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_551.ged"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_until_up(url: str, tries: int = 80) -> None:
    for _ in range(tries):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except Exception:  # noqa: BLE001 - server not accepting connections yet
            pass
        time.sleep(0.25)
    raise RuntimeError(f"server did not come up: {url}")


ADMIN_PASSWORD = "test-pass"


class Live:
    """Handle to the running API (which also serves the SPA), plus test helpers."""

    def __init__(self, api: str) -> None:
        self.api = api

    def seed(self) -> dict:
        """Log in as admin, then import the sample GEDCOM into the running API."""
        with httpx.Client(base_url=self.api, timeout=15) as client:
            login_resp = client.post("/admin/login", json={"password": ADMIN_PASSWORD})
            login_resp.raise_for_status()
            with open(FIXTURE, "rb") as fh:
                resp = client.post(
                    "/gedcom/import",
                    files={"file": ("sample.ged", fh, "text/plain")},
                )
            resp.raise_for_status()
            return resp.json()

    def url(self) -> str:
        """Frontend URL (served by the API itself) wired to this API instance."""
        return f"{self.api}/index.html?api={self.api}"


@pytest.fixture
def live(tmp_path):
    api_port = _free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    db_path = (tmp_path / "e2e.db").as_posix()

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "CORS_ORIGINS": api_url,
        "SQL_ECHO": "false",
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "SECRET_KEY": "test-secret",
    }

    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
    )
    try:
        _wait_until_up(f"{api_url}/health")
        yield Live(api_url)
    finally:
        api_proc.terminate()
        try:
            api_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api_proc.kill()
