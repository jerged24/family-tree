"""Fixtures for browser (e2e) tests: isolated live API + static frontend servers.

Each test gets its own uvicorn API (fresh temp SQLite DB) and a static file server
for ``frontend/``, on ephemeral ports. Tests opt into data with ``live.seed()``.
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


class Live:
    """Handles to the running API and frontend, plus test helpers."""

    def __init__(self, api: str, web: str) -> None:
        self.api = api
        self.web = web

    def seed(self) -> dict:
        """Import the sample GEDCOM into the running API."""
        with open(FIXTURE, "rb") as fh:
            resp = httpx.post(
                f"{self.api}/gedcom/import",
                files={"file": ("sample.ged", fh, "text/plain")},
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json()

    def url(self) -> str:
        """Frontend URL wired to this API instance."""
        return f"{self.web}/index.html?api={self.api}"


@pytest.fixture
def live(tmp_path):
    api_port, web_port = _free_port(), _free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    web_url = f"http://127.0.0.1:{web_port}"
    db_path = (tmp_path / "e2e.db").as_posix()

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "CORS_ORIGINS": web_url,
        "SQL_ECHO": "false",
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
    web_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(web_port),
            "--directory",
            str(ROOT / "frontend"),
            "--bind",
            "127.0.0.1",
        ],
        cwd=ROOT,
    )
    try:
        _wait_until_up(f"{api_url}/health")
        _wait_until_up(f"{web_url}/index.html")
        yield Live(api_url, web_url)
    finally:
        for proc in (api_proc, web_proc):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
