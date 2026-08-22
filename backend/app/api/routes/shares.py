"""Public sharing of a slideshow via an unguessable link.

Creating a share is owner-only (``router``); viewing one is public (``public_router``)
so relatives can just tap the link on a phone — no login, no file download.
"""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from backend.app.storage import shares_dir

router = APIRouter(tags=["shares"])  # guarded (owner creates)
public_router = APIRouter(tags=["shares"])  # unguarded (anyone with the link views)

_MAX_BYTES = 30 * 1024 * 1024  # 30 MB — generous headroom for an embedded song
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@router.post("/shares", status_code=status.HTTP_201_CREATED)
async def create_share(request: Request) -> dict[str, str]:
    """Store a fully-assembled slideshow HTML and return its public path."""
    body = await request.body()
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty slideshow")
    if len(body) > _MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Slideshow too large to share"
        )
    token = secrets.token_urlsafe(12)
    (shares_dir() / f"{token}.html").write_bytes(body)
    return {"token": token, "path": f"/s/{token}"}


@public_router.get("/s/{token}", response_class=HTMLResponse)
def view_share(token: str) -> HTMLResponse:
    """Serve a shared slideshow inline (renders in the browser; not a download)."""
    if not _TOKEN_RE.match(token):  # reject anything that isn't a clean token (no path traversal)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    path = shares_dir() / f"{token}.html"
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This shared slideshow is no longer available"
        )
    return HTMLResponse(content=path.read_text(encoding="utf-8", errors="replace"))
