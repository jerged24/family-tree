"""FastAPI application factory.

Run with:  ``uvicorn backend.app.main:app --reload``
Interactive docs at ``/docs``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import events, families, gedcom, persons, tree
from backend.app.config import settings
from backend.app.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ensure the schema exists on startup."""
    init_db()
    yield


def create_app() -> FastAPI:
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

    for router in (persons.router, families.router, events.router, tree.router, gedcom.router):
        app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
