"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request, status


def require_admin(request: Request) -> None:
    """Guard: allow only requests carrying an authenticated admin session."""
    if not request.session.get("admin"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin login required")
