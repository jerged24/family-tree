"""GEDCOM import (upload) and export (download) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.parsers import export_gedcom, import_gedcom
from backend.app.schemas import ImportSummary

router = APIRouter(prefix="/gedcom", tags=["gedcom"])


@router.post("/import", response_model=ImportSummary, status_code=status.HTTP_201_CREATED)
async def import_ged(
    file: UploadFile = File(..., description="A GEDCOM 5.5.1 .ged file"),
    db: Session = Depends(get_db),
) -> ImportSummary:
    """Import a ``.ged`` upload, merging its records into the database."""
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    result = import_gedcom(db, text)
    db.commit()
    return ImportSummary(
        persons=result.persons,
        families=result.families,
        relationships=result.relationships,
        events=result.events,
        sources=result.sources,
        warnings=result.warnings,
    )


@router.get("/export", response_class=PlainTextResponse)
def export_ged(
    version: str = Query("5.5.1", pattern=r"^(5\.5\.1|7\.0)$"),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Export the whole database as a GEDCOM file."""
    text = export_gedcom(db, gedcom_version=version)
    return PlainTextResponse(
        content=text,
        media_type="text/vnd.familysearch.gedcom",
        headers={"Content-Disposition": 'attachment; filename="family-tree.ged"'},
    )
