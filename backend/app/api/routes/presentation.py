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
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Return a single self-contained HTML file that plays as a family slideshow."""
    return HTMLResponse(
        content=build_slideshow(db, title=title),
        headers={"Content-Disposition": 'attachment; filename="family-slideshow.html"'},
    )
