"""GEDCOM import (upload/sample) and export (download) endpoints."""

from __future__ import annotations

from importlib import resources

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.parsers import export_gedcom, import_gedcom
from backend.app.parsers.gedcom_reader import ImportResult
from backend.app.schemas import ImportSummary

router = APIRouter(prefix="/gedcom", tags=["gedcom"])


def _summary(result: ImportResult) -> ImportSummary:
    return ImportSummary(
        persons=result.persons,
        families=result.families,
        relationships=result.relationships,
        events=result.events,
        sources=result.sources,
        media=result.media,
        warnings=result.warnings,
    )


@router.post("/import", response_model=ImportSummary, status_code=status.HTTP_201_CREATED)
async def import_ged(
    file: UploadFile = File(..., description="A GEDCOM 5.5.1 .ged file"),
    mode: str = Query(
        "merge",
        pattern="^(merge|append)$",
        description="merge: match existing records by xref and update (idempotent); "
        "append: always insert (may conflict on duplicate xrefs)",
    ),
    db: Session = Depends(get_db),
) -> ImportSummary:
    """Import a ``.ged`` upload into the database."""
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    result = import_gedcom(db, text, merge=(mode == "merge"))
    db.commit()
    return _summary(result)


@router.post("/sample", response_model=ImportSummary, status_code=status.HTTP_201_CREATED)
def load_sample(db: Session = Depends(get_db)) -> ImportSummary:
    """Load the bundled sample family (idempotent — safe to call repeatedly)."""
    text = resources.files("backend.app.data").joinpath("sample.ged").read_text(encoding="utf-8")
    result = import_gedcom(db, text, merge=True)
    db.commit()
    return _summary(result)


@router.get("/export", response_class=PlainTextResponse)
def export_ged(
    version: str = Query("5.5.1", pattern=r"^(5\.5\.1|7\.0)$"),
    privacy: str = Query("none", pattern="^(none|living)$"),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Export the whole database as a GEDCOM file (``privacy=living`` masks living people)."""
    text = export_gedcom(db, gedcom_version=version, mask_living=(privacy == "living"))
    return PlainTextResponse(
        content=text,
        media_type="text/vnd.familysearch.gedcom",
        headers={"Content-Disposition": 'attachment; filename="family-tree.ged"'},
    )
