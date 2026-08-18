# CLAUDE.md — Family Tree Application

Guidance for Claude Code (and humans) working in this repository.

## What this is

An interactive Family Tree application. A **FastAPI** backend stores genealogical data
in a GEDCOM-aligned relational schema, exposes a **NetworkX**-backed graph engine for
lineage/kinship queries, imports & exports **GEDCOM** (`.ged`) files, and serves tree
data as DAG JSON to a **D3.js** frontend that renders a zoomable, collapsible graph
using the `d3-dag` layout.

## Tech stack

| Layer            | Choice                                                        |
|------------------|---------------------------------------------------------------|
| Language         | Python 3.11+ (dev machine runs 3.14)                          |
| Web framework    | FastAPI + Uvicorn                                            |
| ORM              | SQLAlchemy 2.0 (typed `Mapped` / `mapped_column` style)      |
| Validation       | Pydantic v2                                                  |
| Database         | SQLite (file-based; swappable via `DATABASE_URL`)            |
| Graph engine     | NetworkX (DiGraph — the family DAG)                          |
| GEDCOM parsing   | Hand-rolled 5.5.1 tokenizer/parser (`ged4py` optional for xref checks) |
| Frontend         | Vanilla ES modules + D3.js v7 + `d3-dag` (no build step)     |
| Tests            | pytest                                                        |

## Directory layout

```
family-tree/
├── CLAUDE.md                     # this file
├── README.md                     # human quick-start
├── requirements.txt              # pinned runtime + dev deps
├── pyproject.toml                # tooling config (ruff, pytest, black)
├── .env.example                  # copy to .env
├── .mcp.json                     # recommended local MCP servers (see below)
├── backend/
│   └── app/
│       ├── main.py               # FastAPI app factory + router registration
│       ├── config.py             # Pydantic Settings (env-driven)
│       ├── database.py           # engine, SessionLocal, get_db(), init_db()
│       ├── models/               # SQLAlchemy ORM — the four core entities
│       │   ├── base.py           # DeclarativeBase + TimestampMixin + enums
│       │   ├── person.py         # Person  (GEDCOM INDI)
│       │   ├── family.py         # Family  (GEDCOM FAM)
│       │   ├── relationship.py   # Relationship (INDI↔FAM membership edges)
│       │   ├── event.py          # Event   (BIRT/DEAT/MARR/…)
│       │   └── source.py         # Source + Citation
│       ├── schemas/              # Pydantic request/response models
│       ├── parsers/              # GEDCOM import (reader) + export (writer)
│       ├── services/             # graph_service.py — NetworkX logic
│       └── api/routes/           # persons, families, tree, gedcom endpoints
├── tests/                        # pytest suites + .ged fixtures
└── frontend/                     # index.html + src/ (D3 / d3-dag renderer)
```

## Build / run / test commands

Run everything from the repo root with the venv active.

```bash
# one-time setup
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell:  .venv\Scripts\Activate.ps1)
pip install -r requirements.txt

# initialise the SQLite schema
python -m backend.app.database          # calls init_db()

# run the API (http://127.0.0.1:8000, docs at /docs)
uvicorn backend.app.main:app --reload

# serve the frontend (any static server; from repo root)
python -m http.server 5500 --directory frontend

# tests
pytest                                   # unit + integration (e2e excluded by default)
pytest tests/test_gedcom_parser.py -v    # one suite
pytest -k kinship                         # by keyword

# browser (e2e) tests — opt-in; needs a one-time browser install
playwright install chromium              # once
pytest -m e2e                            # spins up API + static servers per test
```

## Data model (the four core entities)

A **DAG** of people. Edges are *derived* from GEDCOM-style family membership rather
than stored as raw parent→child rows, which keeps multiple marriages, blended
families, and adoption representable without special cases.

- **Person** (`INDI`) — an individual. Names, sex, xref id, notes.
- **Family** (`FAM`) — a partnership/household unit. Marriage & divorce live here as Events.
- **Relationship** — the association table joining Persons to Families:
  - `role = PARTNER` → `partner_type` (HUSBAND / WIFE / SPOUSE / PARTNER) — supports
    same-sex & unmarried partners; a person may partner in *many* families (remarriage).
  - `role = CHILD` → `pedigree` (BIRTH / ADOPTED / FOSTER / STEP / SEALED / GUARDIAN).
  - The parent→child DAG edge = every PARTNER of a family → every CHILD of that family.
- **Event / Source** — typed events (attachable to a Person *or* a Family) and the
  source citations that back them.

The NetworkX `DiGraph` is built in `services/graph_service.py` by walking Relationships:
nodes = Persons, directed edges = parent→child. Lineage, ancestors/descendants,
common-ancestor, relationship-path, and kinship-coefficient queries run on that graph.

## Code style & conventions

- **SQLAlchemy 2.0 typed style** only: `Mapped[...]` + `mapped_column(...)`. No legacy
  `Column` class attributes.
- **Pydantic v2**: `model_config = ConfigDict(from_attributes=True)`; never reuse an ORM
  object as a response model — always go through a `schemas/` model.
- Keep ORM models free of business logic. Graph/genealogy logic lives in `services/`.
  GEDCOM text handling lives only in `parsers/`.
- **Enums** are `enum.StrEnum` persisted via the `str_enum()` helper in `models/base.py`
  (`SQLAlchemy Enum(..., native_enum=False, values_callable=...)`) so the SQLite file stores
  the compact GEDCOM tag values and stays human-readable and portable.
- Type-hint everything. Public functions get a one-line docstring stating intent.
- Formatting: `black` (line length 100) + `ruff` (see `pyproject.toml`). Run before commit.
- Tests are behavior-focused and use an in-memory SQLite engine (see `tests/conftest.py`).
  Every GEDCOM parser change needs a round-trip test (parse → export → re-parse == equal).
- Browser tests live in `tests/e2e/` behind the `e2e` marker (excluded from the default
  run). Their `live` fixture launches a real API + static server per test on ephemeral
  ports. Because SVG nodes drift during the fit-to-view zoom, e2e node interactions use
  `dispatch_event("click")` rather than physical clicks.

## GEDCOM compliance notes

- Import targets **5.5.1**; export writes valid **5.5.1** and can emit **7.0** header form.
- Preserve original `@Xref@` ids on Person/Family/Source for lossless round-tripping.
- Line format: `level [xref] tag [value]`; `CONC`/`CONT` continuation lines are joined on read.
- Dates are stored twice: the raw GEDCOM date string (`date_value`) **and** a parsed
  sortable date (`date_sort`, nullable) — never discard the original string.

## Recommended local MCP servers

Configured in `.mcp.json` (start them from an interactive `claude` session with `/mcp`;
this environment can't run OAuth/stdio launches for you):

- **SQLite MCP** — point at `familytree.db` for inline schema inspection & ad-hoc queries.
- **Context7 MCP** — fetch current D3.js / d3-dag / NetworkX docs while coding.
- **Playwright MCP** — automated UI + graph visual regression tests against the frontend.

See `.mcp.json` for the exact server entries and swap in your preferred implementations.

## Implementation roadmap (status)

1. ✅ Project boilerplate & directory layout.
2. ✅ SQLAlchemy schema + Pydantic validation models.
3. ✅ GEDCOM 5.5.1 parser module + comprehensive `tests/` (round-trip verified).
4. ✅ NetworkX relationship graph service layer (kinship, lineage, MRCA, paths).
5. ✅ FastAPI endpoints: persons/families/events CRUD, GEDCOM import/export, tree DAG
   JSON + relationship analysis. 50 tests total; live-boot verified.
6. ✅ D3 / d3-dag frontend: zoomable/pannable DAG, DAG-aware collapse, click-to-select,
   two-person relationship analysis with path highlighting. Verified live in-browser.
7. ✅ Playwright e2e suite (`tests/e2e/`, 6 tests). Caught two real bugs: (a) a
   `CORS_ORIGINS` env value crashed startup because pydantic-settings JSON-decoded the
   `list[str]` field before the CSV validator — fixed with `NoDecode`; (b) the
   empty-state overlay was permanently visible (a class `display:flex` overrode the
   `hidden` attribute) — fixed with `.empty-state[hidden]{display:none}`.
8. ✅ CI (`.github/workflows/ci.yml`): ruff + black + unit tests on Python 3.11 & 3.12,
   and a separate Playwright e2e job. The whole codebase is ruff- and black-clean;
   domain enums use `enum.StrEnum`. Note the e2e job needs network access (the frontend
   pulls d3 / d3-dag from a CDN at runtime) — vendoring those would remove that dependency.

**The application is feature-complete against the original spec.** Run both servers via
`.claude/launch.json` (`api` + `frontend`) or the commands above.
