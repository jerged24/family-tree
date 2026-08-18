"""Generate docs/screenshot.png — boots the app, loads the sample family, and
captures the tree with a cousin relationship analysis showing.

Run:  python docs/capture_screenshot.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshot.png"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait(url: str, tries: int = 80) -> None:
    for _ in range(tries):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    raise RuntimeError(f"server not up: {url}")


def main() -> None:
    api_port, web_port = _free_port(), _free_port()
    api_url, web_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    env = {**os.environ, "DATABASE_URL": "sqlite:///./shot.db", "CORS_ORIGINS": web_url}
    (ROOT / "shot.db").unlink(missing_ok=True)

    api = subprocess.Popen(
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
    web = subprocess.Popen(
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
        _wait(f"{api_url}/health")
        _wait(f"{web_url}/index.html")
        httpx.post(f"{api_url}/gedcom/sample", timeout=15).raise_for_status()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1320, "height": 840}, device_scale_factor=2)
            page.goto(f"{web_url}/index.html?api={api_url}")
            page.wait_for_selector("#tree-svg g.node")

            # Select two first cousins to show the relationship analysis panel.
            def pick(name: str, slot: int) -> None:
                page.locator("#tree-svg g.node", has_text=name).first.locator(
                    "rect.card"
                ).dispatch_event("click")
                page.locator(f'#detail button[data-slot="{slot}"]').click()

            pick("Michael King", 0)
            pick("Sophia Cruz", 1)
            page.wait_for_selector("#analysis .verdict")
            page.wait_for_timeout(800)  # let the fit-to-view settle

            OUT.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(OUT))
            browser.close()
            print(f"wrote {OUT}")
    finally:
        for p in (api, web):
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        (ROOT / "shot.db").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
