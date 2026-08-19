# Collaborative Family Intake — Design

- **Date:** 2026-08-18
- **Status:** Approved (design); pending implementation plan
- **Repo:** family-tree (FastAPI + SQLAlchemy + NetworkX + D3/d3-dag)

## 1. Overview

Let the tree owner send each "head of family" a private link (pasted into Facebook
Messenger by hand). Opening the link shows that relative their own branch and lets them
add/edit relatives and upload photos from their phone. Submissions flow into the central
tree with a **hybrid** policy: brand-new people and photos apply automatically; edits that
collide with people already in the tree are held for the owner's review. The app is
deployed publicly on Railway behind an owner login.

### Goals

- Per-person invite links, anchored to a known person, revocable.
- Mobile-friendly guided branch entry ("+ Parent / Spouse / Child / Sibling") plus photo
  uploads; an "Advanced: upload a GEDCOM" path reusing the existing importer.
- Hybrid merge: new data auto-applies; conflicts queue for review; any submission is
  fully revertable.
- Owner login gating the full tree + review dashboard + invite management.
- Deploy on Railway Hobby ($5/mo) with a persistent volume for the SQLite DB and photos.

### Non-goals (v1 — YAGNI)

Email notifications; relative accounts; multi-admin; photo cropping/editing; real-time
updates; automatic cross-submission person de-duplication/merge tooling; i18n.

## 2. Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| What relatives contribute | Their **whole branch** (parents, siblings, extended) + photos |
| How submissions enter the tree | **Hybrid** — new auto-applies, conflicts queue for review |
| Access model | **Per-person invite tokens**, anchored to a person; sent manually via Messenger |
| Hosting | **Railway Hobby ($5/mo)**, managed, persistent volume |
| Notifications | **In-app review dashboard only** (no email) |
| Intake UX | **Guided form primary** + **GEDCOM upload** bonus |

## 3. Architecture

The existing FastAPI app gains three subsystems; existing modules are reused.

```
Owner (authenticated)                Relative (token only)
        │                                    │
        ▼                                    ▼
  Admin routes  ──────────┐        Intake routes (/invite/{token})
  (login, invites,        │                │
   review, existing CRUD) │                ▼
        │                 │           Submission payload
        ▼                 │                │
   Live tree  ◀───────────┴──── Reconciler ┘   (classifies each change:
   (Person/Family/...)              │            auto-apply vs. pending)
        ▲                           ▼
        └──── revert ────── Submission + PendingChange (staging/audit)
```

- **Invites** — token generation/validation, anchored to a `Person`.
- **Intake** — token-scoped read of a relative's branch + a submit endpoint; a
  mobile-first page served at `/invite/{token}`.
- **Staging + review** — `Submission` (audit + revert) and `PendingChange` (conflicts);
  a **reconciler** applies the auto-safe parts and queues the rest.

## 4. Data model

### New tables

**Invite**
- `id` PK
- `token` str, unique, indexed — `secrets.token_urlsafe(32)`
- `anchor_person_id` FK `persons.id` (the relative this link represents)
- `label` str? (e.g. "Uncle Ben")
- `created_at`, `expires_at` datetime? (null = no expiry), `revoked` bool = false

**Submission**
- `id` PK
- `invite_id` FK `invites.id`
- `submitter_name` str? (relative may type their name)
- `payload` JSON/Text — the raw structured branch the relative entered (for audit)
- `status` StrEnum(`APPLIED`, `REVERTED`) = `APPLIED`
- `created_at`

**PendingChange**
- `id` PK
- `submission_id` FK `submissions.id`
- `person_id` FK `persons.id`? (existing person being changed)
- `change_type` StrEnum(`FIELD_EDIT`, `RELATIONSHIP_ADD`) — v1 is mostly `FIELD_EDIT`
- `field` str? (e.g. `surname`, `birth`)
- `current_value` str?, `submitted_value` str?
- `status` StrEnum(`PENDING`, `APPROVED`, `REJECTED`) = `PENDING`
- `created_at`

### Column additions (provenance, for revert)

Add nullable `submission_id` FK (`submissions.id`, `ON DELETE SET NULL`) to **Person**,
**Relationship**, **Event**, and **Media**. Every row a submission creates is stamped, so
"revert submission" deletes exactly those rows. Records the owner created directly have
`submission_id = NULL`.

### Media (uploads)

`Media` keeps its shape (`url`, `caption`, `mime_type`, `is_primary`). Uploaded files are
stored on disk under `MEDIA_DIR` with a UUID filename; `url` becomes the served path
`/media/files/{uuid}.{ext}`. GEDCOM `OBJE` export references that served URL unchanged.

The schema is created via `Base.metadata.create_all` (SQLite). Because the deployment is
brand-new, we recreate the dev/prod DB rather than writing migrations; if data already
exists at implementation time, a one-off `ALTER TABLE … ADD COLUMN submission_id` script
covers the additive columns.

## 5. The reconciler (hybrid merge rules)

Input: a submission payload describing draft people (each either references an existing
`person_id` or is new with a temp id), draft relationships between them, field values, and
uploaded photos — all relative to the invite's anchor person.

Per element:

| Element | Rule | Result |
|---------|------|--------|
| New person (temp id) | always | **auto-create**, stamp `submission_id` |
| Relationship with ≥1 new endpoint, not duplicating an existing row | always | **auto-create**, stamp |
| Relationship between two **existing** people | risky | **PendingChange** (`RELATIONSHIP_ADD`) |
| Field edit on a person who already existed | overwrites live data | **PendingChange** (`FIELD_EDIT`), live value untouched |
| Field value on a **new** person | part of creation | applied at create |
| Photo upload (any person) | additive | **auto-attach** `Media`, stamp |

**Approve** a `PendingChange` → apply `submitted_value` to the field (or create the
relationship); mark `APPROVED`. **Reject** → mark `REJECTED`, no change.

**Revert** a submission → delete all `Person`/`Relationship`/`Event`/`Media` rows stamped
with its `submission_id` (ORM cascades handle dependents), delete its still-`PENDING`
changes, mark the submission `REVERTED`.

**Known limitation:** two relatives independently adding the same *new* person creates a
duplicate. v1 accepts this; the owner reverts or (future work) merges. No automatic
cross-submission de-duplication in v1.

## 6. Security & auth

- **Owner login.** A single `ADMIN_PASSWORD` (env var). `POST /admin/login` verifies it and
  sets a signed session cookie (Starlette `SessionMiddleware` with `SECRET_KEY`). An
  `require_admin` dependency guards all admin routes. **All existing CRUD/tree/gedcom routes
  become admin-only.**
- **Relatives** never authenticate; they present a token in the URL. Intake routes validate
  the token (exists, not revoked, not expired) and scope reads to the anchor's branch.
  Invalid/expired/revoked → `403`/`410`.
- Tokens are long, random, revocable, optionally expiring.
- Intake submit is rate-limited (simple per-token/IP throttle) to deter abuse.
- **Writes from relatives never overwrite existing live data** — field edits only ever
  become `PendingChange`s.
- **Photo files** are served from UUID (capability) URLs. This is acceptable for v1; a
  per-request access check is future work. Documented as a privacy trade-off.

## 7. API surface

### Admin (session-protected)

- `POST /admin/login` `{password}` → set cookie · `POST /admin/logout`
- `POST /admin/invites` `{anchor_person_id, label?, expires_at?}` → `{token, url}`
- `GET /admin/invites` · `POST /admin/invites/{id}/revoke`
- `GET /admin/submissions` (audit log) · `POST /admin/submissions/{id}/revert`
- `GET /admin/pending-changes` · `POST /admin/pending-changes/{id}/approve` ·
  `POST /admin/pending-changes/{id}/reject`
- Existing `persons` / `families` / `events` / `media` / `tree` / `gedcom` routes — now
  behind `require_admin`.

### Intake (token-scoped, no session)

- `GET /invite/{token}` → serves the intake page (static).
- `GET /api/invite/{token}/branch` → JSON for display/editing: the anchor plus their
  directly-connected relatives (parents, spouses, children, siblings). The relative adds
  outward from there; the exact payload schema (draft-person temp ids, relationships) is
  defined in the implementation plan.
- `POST /api/invite/{token}/photo` → multipart upload → stores file → returns a media ref.
- `POST /api/invite/{token}/submit` → structured branch payload → create `Submission`, run
  reconciler → return `{auto_applied, pending}` summary.
- `POST /api/invite/{token}/gedcom` → `.ged` upload → parsed into a submission payload →
  same reconciler (Phase 3).

### Media serving

- `GET /media/files/{filename}` → serve from `MEDIA_DIR` (FastAPI `StaticFiles` mount).

## 8. Frontend

- **Admin app** = the existing `frontend/`, now behind a **login screen**. Two new panels:
  - **Invites** — pick a person, create link, copy it (to paste into Messenger), list/revoke.
  - **Review** — pending changes (current vs. submitted, Approve/Reject) and a submissions
    log with a **Revert** button.
- **Intake page** = a new mobile-first surface (`frontend/intake/`, served at
  `/invite/{token}`): welcome → read view of the branch → add-relative cards
  (+ Parent/Spouse/Child/Sibling) with inline **photo upload** → optional **Advanced: upload
  a GEDCOM** → Submit → thank-you. The token may be reused to add more later until
  revoked/expired.

## 9. Hosting & deployment (Railway Hobby, $5/mo)

- **Single service:** FastAPI (uvicorn) serves the API *and* both static frontends
  (`StaticFiles` mounts) — so admin app, intake page, and API are **same-origin** in
  production (cross-origin CORS becomes unnecessary; dev keeps the two-server setup).
- **Persistent volume mounted at `/data`.** Env vars:
  - `DATABASE_URL=sqlite:////data/app.db`
  - `MEDIA_DIR=/data/media`
  - `ADMIN_PASSWORD=…`, `SECRET_KEY=…`
- **Build:** a `Dockerfile` (explicit and reproducible) — Python 3.12, install
  `requirements.txt`, run uvicorn on `$PORT`.
- **Deploy:** auto-deploy from GitHub `main`. HTTPS via the Railway-provided domain; custom
  domain optional later. A `railway.json`/dashboard note documents the volume + env setup.

## 10. Testing

- **Unit:** token gen/validate/expire/revoke; reconciler classification (new→auto,
  field-edit→pending, existing↔existing relationship→pending, photo→auto); revert deletes
  exactly the submission-stamped rows; GEDCOM→submission payload; upload storage writes to
  `MEDIA_DIR` and serves back.
- **API:** intake token scoping (bad/expired/revoked → 403/410); submit returns the correct
  `{auto_applied, pending}` split and never overwrites existing fields; approve/reject/revert
  behaviors; admin routes reject unauthenticated requests (401/redirect).
- **e2e (Playwright):** admin logs in → creates an invite → copies link; relative opens the
  link → adds a parent + uploads a photo → submits; admin sees the auto-applied person and
  the pending change → approves it.

## 11. Build order (one spec, three phases)

**Phase 1 — Deploy + login + uploads**
Admin login/session; put existing routes behind `require_admin`; photo file-upload endpoint
+ `MEDIA_DIR` storage + `/media/files` serving; FastAPI serves the frontend same-origin;
`Dockerfile` + Railway volume/env; deploy. *Deliverable: the current app, live and private,
with login and photo uploads.*

**Phase 2 — Invites + intake + review**
`Invite`/`Submission`/`PendingChange` models + `submission_id` provenance columns; admin
invite management + review dashboard; intake page (guided form) + branch API + submit +
reconciler + revert. *Deliverable: relatives submit branches; owner reviews and merges.*

**Phase 3 — GEDCOM-upload bonus**
`.ged` upload on the intake page → parsed into a submission payload through the same
reconciler. *Deliverable: power users can seed a whole branch from an existing GEDCOM.*

## 12. Risks & open items

- **Duplicate people across submissions** — accepted in v1; revert/manual fix; merge tool is
  future work.
- **Photo privacy** — capability (UUID) URLs, not per-viewer access-controlled in v1.
- **SQLite on one instance** — fine for family scale; not for high concurrency.
- **Reconciler heuristics** — ambiguous cases always fall to *pending* (safe default).
- **Existing tests** — the many current tests assume open (unauthenticated) routes; Phase 1
  must update them to authenticate, or exempt the test client. This is expected churn, not a
  regression.
