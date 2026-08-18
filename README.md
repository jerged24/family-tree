# Family Tree

An interactive, GEDCOM-backed family tree application.

- **Backend:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 over SQLite
- **Graph engine:** NetworkX (lineage, common ancestors, relationship paths, kinship coefficient)
- **Import/export:** GEDCOM 5.5.1 (reads 5.5.1, exports 5.5.1 / 7.0 header)
- **Frontend:** D3.js v7 + `d3-dag` — a zoomable, collapsible DAG

The data model is a **directed acyclic graph** of people. Membership in `Family` units
(via the `Relationship` table) yields parent→child edges, so multiple marriages,
blended families, and adoption are represented without special cases. See
[`CLAUDE.md`](CLAUDE.md) for the full architecture and conventions.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt

python -m backend.app.database          # create familytree.db
uvicorn backend.app.main:app --reload   # API at http://127.0.0.1:8000/docs
python -m http.server 5500 --directory frontend   # frontend

pytest                                   # run the test suite
```

## Status

**Feature-complete against the original spec** and verified end to end (50 passing tests
plus live in-browser checks):

- SQLAlchemy schema — Person / Family / Relationship / Event / Source (a GEDCOM-aligned DAG)
- Pydantic v2 validation layer
- GEDCOM 5.5.1 reader + writer with round-trip fidelity
- NetworkX graph service — lineage, MRCA, relationship paths, genetic kinship coefficients
- FastAPI — CRUD, GEDCOM import/export, tree DAG JSON, relationship analysis
- D3 / d3-dag frontend — zoomable, collapsible tree with two-person relationship analysis

See the roadmap in `CLAUDE.md` for the per-step detail.
