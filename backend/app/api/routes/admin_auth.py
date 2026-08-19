"""Owner (admin) authentication: a single shared password → signed session cookie."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict[str, str]:
    if not hmac.compare_digest(body.password, settings.admin_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid password")
    request.session["admin"] = True
    return {"status": "ok"}


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "ok"}


@router.get("/session")
def session_status(request: Request) -> dict[str, bool]:
    return {"authenticated": bool(request.session.get("admin"))}
