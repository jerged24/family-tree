"""FastAPI application factory.

Run with:  ``uvicorn backend.app.main:app --reload``
Interactive docs at ``/docs``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import Scope

from backend.app.api.deps import require_admin
from backend.app.api.routes import (
    admin_auth,
    associations,
    events,
    families,
    gedcom,
    media,
    persons,
    presentation,
    reset,
    tree,
)
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.storage import media_dir


# The SPA shell and its JS/CSS carry ETags; StaticFiles omits Cache-Control, so
# browsers cache heuristically and can show a stale page after a deploy. "no-cache"
# still stores the file but forces a revalidation each load — unchanged files return
# a tiny 304, and a new deploy is picked up immediately with no hard refresh.
class RevalidatingStatic(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ensure the schema exists on startup."""
    init_db()
    yield


def create_app() -> FastAPI:
    # Fail fast rather than boot with insecure defaults in a non-dev environment.
    if settings.env != "dev" and (
        settings.admin_password == "changeme"
        or settings.secret_key == "dev-insecure-secret-change-me"
    ):
        raise RuntimeError(
            "Refusing to start in non-dev env with default ADMIN_PASSWORD/SECRET_KEY — "
            "set them via environment variables."
        )

    app = FastAPI(
        title="Family Tree API",
        version="0.1.0",
        description="GEDCOM-backed family tree: persons, families, relationships, "
        "events, GEDCOM import/export, and a NetworkX graph engine serving DAG JSON.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        # Secure flag on in prod (HTTPS); off in dev/tests so it works over http.
        https_only=(settings.env != "dev"),
    )

    guarded = [
        persons.router,
        families.router,
        events.router,
        media.router,
        associations.router,
        tree.router,
        gedcom.router,
        presentation.router,
        reset.router,
    ]
    for router in guarded:
        app.include_router(router, dependencies=[Depends(require_admin)])
    app.include_router(admin_auth.router)  # unprotected: login lives here

    app.mount("/media/files", StaticFiles(directory=str(media_dir())), name="media")

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # SPA mount MUST be last: it's a catch-all at "/" so specific API routes above
    # still win over it.
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/", RevalidatingStatic(directory=str(frontend_dir), html=True), name="spa")

    return app


app = create_app()
