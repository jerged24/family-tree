"""Family slideshow — a downloadable, self-contained HTML presentation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services.slideshow_service import build_slideshow

router = APIRouter(tags=["presentation"])


@router.get("/slideshow", response_class=HTMLResponse)
def slideshow(
    title: str = Query("Our Family Tree", max_length=100),
    anchor: int | None = Query(
        None, description="Order from this person's father's then mother's line"
    ),
    seconds: float = Query(6.0, ge=2, le=30, description="Auto-advance interval"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Return a single self-contained HTML file that plays as a family slideshow."""
    return HTMLResponse(
        content=build_slideshow(db, title=title, anchor_id=anchor, seconds=seconds),
        headers={"Content-Disposition": 'attachment; filename="family-slideshow.html"'},
    )
