"""Filesystem storage for uploaded media."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from backend.app.config import settings

_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Content types accepted by the upload endpoint (images only — prevents stored XSS
# from e.g. an uploaded .html/.svg being served and executed same-origin).
ALLOWED_IMAGE_TYPES = set(_EXT_BY_TYPE)


def media_dir() -> Path:
    path = Path(settings.media_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def shares_dir() -> Path:
    """Where published (public) slideshow snapshots live — sibling of the media dir,
    so it sits on the same persistent volume in production (/data/shares)."""
    path = Path(settings.media_dir).parent / "shares"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(
    data: bytes, content_type: str | None, original_name: str | None = None
) -> tuple[str, str]:
    """Persist bytes under a random filename; return (filename, served_url)."""
    ext = _EXT_BY_TYPE.get(content_type or "", "")
    if not ext and original_name:
        ext = os.path.splitext(original_name)[1].lower()
    filename = f"{uuid.uuid4().hex}{ext or '.bin'}"
    (media_dir() / filename).write_bytes(data)
    return filename, f"/media/files/{filename}"
