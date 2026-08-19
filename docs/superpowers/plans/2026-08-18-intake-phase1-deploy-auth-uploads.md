# Collaborative Intake — Phase 1: Deploy + Login + Uploads — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the existing family-tree app behind an owner login, add photo file-uploads with persistent storage, serve the frontend same-origin, and make it deployable to Railway.

**Architecture:** Add a signed-session admin login (single password) and a `require_admin` dependency that gates every existing router. Add a filesystem storage helper + upload endpoint whose files are served from a static mount. Serve the SPA from the FastAPI app so admin UI + API are same-origin. Ship a Dockerfile targeting Railway with a `/data` volume for the SQLite DB and photos.

**Tech Stack:** Python 3.12, FastAPI, Starlette `SessionMiddleware`, SQLAlchemy 2.0, Pydantic v2, pytest + Playwright, Docker, Railway.

**Spec:** `docs/superpowers/specs/2026-08-18-collaborative-family-intake-design.md` (Phase 1 = §11 phase 1; auth §6; uploads §4; hosting §9).

## Global Constraints

Copied verbatim from the spec / project conventions — every task inherits these:

- Python **3.11+** (dev/prod runs 3.12).
- **SQLAlchemy 2.0 typed** style (`Mapped` / `mapped_column`); no legacy `Column`.
- **Pydantic v2**; response models go through `schemas/`, never raw ORM.
- Enums are `enum.StrEnum` via the `str_enum()` helper.
- Formatting: `black` (line length 100) + `ruff` (select E,F,I,UP,B,SIM). Run before every commit.
- Tests use an in-memory SQLite engine (`tests/conftest.py`); e2e tests are marked `e2e` and excluded by default.
- Relatives' writes must **never overwrite live data** (not exercised in Phase 1, but the auth boundary set here is what later enforces it).
- Commit after every green step. Branch: `feat/collaborative-intake`.

## File Structure

**Create:**
- `backend/app/api/deps.py` — shared FastAPI dependencies (`require_admin`).
- `backend/app/api/routes/admin_auth.py` — `/admin/login`, `/admin/logout`.
- `backend/app/storage.py` — filesystem helper for saving/serving uploaded media.
- `Dockerfile` — production image.
- `railway.json` — Railway service config (volume + start).
- `DEPLOY.md` — deployment runbook (env vars, volume, first-deploy steps).
- `tests/test_auth.py`, `tests/test_uploads.py`, `tests/test_serving.py` — new suites.

**Modify:**
- `backend/app/config.py` — add `admin_password`, `secret_key`, `media_dir`, `public_base_url`.
- `backend/app/main.py` — `SessionMiddleware`, ensure `media_dir`, protect routers, static mounts.
- `backend/app/api/routes/media.py` — add `POST /persons/{id}/media/upload`.
- `frontend/src/api.js` — send credentials, add `login`, `uploadMedia`; surface 401.
- `frontend/src/main.js` + `frontend/index.html` + `frontend/src/styles.css` — login overlay.
- `tests/conftest.py` — the `client` and `live` fixtures authenticate; `live` sets `ADMIN_PASSWORD`.
- `tests/e2e/test_ui.py` — log in through the overlay before asserting.
- `requirements.txt` — add `itsdangerous` (SessionMiddleware dependency).

---

### Task 1: Settings for auth, storage, and deploy

**Files:**
- Modify: `backend/app/config.py`
- Modify: `requirements.txt`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `settings.admin_password: str`, `settings.secret_key: str`, `settings.media_dir: str`, `settings.public_base_url: str`.

- [ ] **Step 1: Add the dependency**

Add to `requirements.txt` under the runtime section:

```
itsdangerous>=2.2          # required by Starlette SessionMiddleware
```

Install: `.venv/Scripts/python.exe -m pip install "itsdangerous>=2.2"`

- [ ] **Step 2: Write the failing test**

Create `tests/test_auth.py`:

```python
"""Auth + settings tests."""
from __future__ import annotations

import os


def test_settings_read_admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("MEDIA_DIR", "/tmp/ft-media")
    from backend.app.config import Settings

    s = Settings()
    assert s.admin_password == "s3cret"
    assert s.media_dir == "/tmp/ft-media"
    assert hasattr(s, "secret_key") and hasattr(s, "public_base_url")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py::test_settings_read_admin_env -v`
Expected: FAIL (`AttributeError: admin_password` / validation error).

- [ ] **Step 4: Add the fields**

In `backend/app/config.py`, inside `Settings`, after `sql_echo`:

```python
    admin_password: str = "changeme"
    secret_key: str = "dev-insecure-secret-change-me"
    media_dir: str = "./media"
    public_base_url: str = ""  # e.g. https://app.up.railway.app; "" → derive from request
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py::test_settings_read_admin_env -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py requirements.txt tests/test_auth.py
git commit -m "feat(config): add admin_password, secret_key, media_dir, public_base_url"
```

---

### Task 2: Admin login + `require_admin` dependency

**Files:**
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/routes/admin_auth.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `require_admin(request) -> None` (raises 401 unless `request.session["admin"]`); routes `POST /admin/login {password}`, `POST /admin/logout`.
- Consumes: `settings.admin_password`, `settings.secret_key`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_auth.py`:

```python
from fastapi.testclient import TestClient


def _fresh_client():
    from backend.app.main import app
    return TestClient(app)


def test_login_rejects_bad_password():
    c = _fresh_client()
    assert c.post("/admin/login", json={"password": "wrong"}).status_code == 401


def test_login_then_protected_route_ok():
    from backend.app.config import settings

    c = _fresh_client()
    assert c.post("/admin/login", json={"password": settings.admin_password}).status_code == 200
    # /persons is protected in Task 3; here we assert login itself round-trips.
    assert c.post("/admin/logout").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py -k login -v`
Expected: FAIL (404 — routes don't exist yet).

- [ ] **Step 3: Create the dependency**

Create `backend/app/api/deps.py`:

```python
"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import HTTPException, Request, status


def require_admin(request: Request) -> None:
    """Guard: allow only requests carrying an authenticated admin session."""
    if not request.session.get("admin"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin login required")
```

- [ ] **Step 4: Create the login routes**

Create `backend/app/api/routes/admin_auth.py`:

```python
"""Owner (admin) authentication: a single shared password → signed session cookie."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict[str, str]:
    if body.password != settings.admin_password:
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
```

- [ ] **Step 5: Wire middleware + router in `main.py`**

In `backend/app/main.py`, add imports:

```python
from starlette.middleware.sessions import SessionMiddleware

from backend.app.api.routes import admin_auth
```

In `create_app()`, add the middleware right after `CORSMiddleware`:

```python
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=False,  # Railway terminates TLS; cookie still flows over its HTTPS domain
    )
```

Include the (unprotected) auth router alongside the others:

```python
    app.include_router(admin_auth.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/routes/admin_auth.py backend/app/main.py tests/test_auth.py
git commit -m "feat(auth): admin login/logout with signed session + require_admin dependency"
```

---

### Task 3: Protect existing routers + make test fixtures authenticate

**Files:**
- Modify: `backend/app/main.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `require_admin` (Task 2).
- Produces: all `persons`/`families`/`events`/`media`/`tree`/`gedcom` routes now require an admin session; the `client` fixture is pre-authenticated.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_auth.py`:

```python
def test_persons_requires_admin():
    c = _fresh_client()  # not logged in
    assert c.get("/persons").status_code == 401


def test_persons_ok_after_login():
    from backend.app.config import settings

    c = _fresh_client()
    c.post("/admin/login", json={"password": settings.admin_password})
    assert c.get("/persons").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py::test_persons_requires_admin -v`
Expected: FAIL (returns 200 — routes not yet protected).

- [ ] **Step 3: Add the guard to each router include**

In `backend/app/main.py`, add `Depends` + `require_admin` imports:

```python
from fastapi import Depends, FastAPI

from backend.app.api.deps import require_admin
```

Replace the router-include loop so every data router carries the guard (the auth router stays open):

```python
    guarded = [
        persons.router,
        families.router,
        events.router,
        media.router,
        tree.router,
        gedcom.router,
    ]
    for router in guarded:
        app.include_router(router, dependencies=[Depends(require_admin)])
    app.include_router(admin_auth.router)  # unprotected: login lives here
```

- [ ] **Step 4: Make the `client` fixture log in**

In `tests/conftest.py`, inside the `client` fixture, after building `TestClient(app)` and before `yield`, authenticate:

```python
        test_client = TestClient(app)
        test_client.post("/admin/login", json={"password": settings.admin_password})
        yield test_client
```

Add the import at the top of `conftest.py`:

```python
from backend.app.config import settings
```

- [ ] **Step 5: Run the whole unit suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (existing 61 + new auth tests; the pre-authenticated `client` keeps them green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py tests/conftest.py tests/test_auth.py
git commit -m "feat(auth): gate all data routes behind require_admin; auth the test client"
```

---

### Task 4: Photo upload storage + endpoint + serving

**Files:**
- Create: `backend/app/storage.py`
- Modify: `backend/app/api/routes/media.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_uploads.py`

**Interfaces:**
- Produces: `storage.save_upload(data: bytes, content_type: str | None, original_name: str | None) -> tuple[str, str]` returning `(filename, url)` where `url == "/media/files/{filename}"`; route `POST /persons/{id}/media/upload` (multipart) → `MediaRead`; static mount serving `/media/files/*`.
- Consumes: `settings.media_dir`, `Media`, `MediaRead`, `require_admin`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_uploads.py`:

```python
"""Photo upload + serving tests."""
from __future__ import annotations

_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000155a2b4ee0000000049454e44ae426082"
)


def test_upload_creates_media_and_serves_file(client):
    pid = client.post("/persons", json={"given_name": " Imo", "sex": "F"}).json()["id"]
    resp = client.post(
        f"/persons/{pid}/media/upload",
        files={"file": ("me.png", _PNG_1x1, "image/png")},
        data={"is_primary": "true"},
    )
    assert resp.status_code == 201
    url = resp.json()["url"]
    assert url.startswith("/media/files/") and url.endswith(".png")

    served = client.get(url)
    assert served.status_code == 200
    assert served.content == _PNG_1x1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uploads.py -v`
Expected: FAIL (404 — endpoint missing).

- [ ] **Step 3: Create the storage helper**

Create `backend/app/storage.py`:

```python
"""Filesystem storage for uploaded media."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from backend.app.config import settings

_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def media_dir() -> Path:
    path = Path(settings.media_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(
    data: bytes, content_type: str | None, original_name: str | None = None
) -> tuple[str, str]:
    """Persist bytes under a random filename; return (filename, served_url)."""
    ext = _EXT_BY_TYPE.get(content_type or "", "")
    if not ext and original_name:
        ext = os.path.splitext(original_name)[1].lower()
    filename = f"{uuid.uuid4().hex}{ext or '.bin'}"
    (media_dir() / filename).write_bytes(data)
    return filename, f"/media/files/{filename}"
```

- [ ] **Step 4: Add the upload endpoint**

In `backend/app/api/routes/media.py`, extend the imports:

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.app.storage import save_upload
```

Add the endpoint (after `add_media`):

```python
@router.post(
    "/persons/{person_id}/media/upload",
    response_model=MediaRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    person_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db),
) -> Media:
    if db.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Person {person_id} not found")
    data = await file.read()
    _, url = save_upload(data, file.content_type, file.filename)
    if is_primary:
        for existing in db.scalars(select(Media).where(Media.person_id == person_id)):
            existing.is_primary = False
    item = Media(
        person_id=person_id,
        url=url,
        caption=caption,
        mime_type=file.content_type,
        is_primary=is_primary,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
```

- [ ] **Step 5: Mount static serving in `main.py`**

In `backend/app/main.py` add:

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from backend.app.storage import media_dir
```

In `create_app()`, after including routers, mount the media directory (ensuring it exists first):

```python
    app.mount("/media/files", StaticFiles(directory=str(media_dir())), name="media")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uploads.py -v`
Expected: PASS

- [ ] **Step 7: Ignore the local media dir**

Append to `.gitignore`:

```
# Uploaded media (dev)
/media/
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/storage.py backend/app/api/routes/media.py backend/app/main.py tests/test_uploads.py .gitignore
git commit -m "feat(media): photo file upload endpoint + filesystem storage + static serving"
```

---

### Task 5: Serve the frontend same-origin + login overlay

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/src/api.js`
- Modify: `frontend/index.html`
- Modify: `frontend/src/main.js`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_serving.py`

**Interfaces:**
- Produces: `GET /` serves `frontend/index.html`; the SPA shows a login overlay and calls `POST /admin/login`; API calls send the session cookie.
- Consumes: `/admin/login`, `/admin/session`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_serving.py`:

```python
"""Same-origin static serving of the SPA."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_serves_spa():
    from backend.app.main import app

    body = TestClient(app).get("/").text
    assert "Family Tree" in body  # index.html title/header
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_serving.py -v`
Expected: FAIL (404 — `/` not served).

- [ ] **Step 3: Mount the SPA last in `main.py`**

At the very end of `create_app()` (after the `/media/files` mount and `/health`), mount the frontend at root so specific API routes still win:

```python
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="spa")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_serving.py -v`
Expected: PASS

- [ ] **Step 5: Make `api.js` send cookies + surface 401**

In `frontend/src/api.js`, add `credentials` to the fetch and expose auth helpers. Change `request`:

```javascript
async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, { credentials: "include", ...options });
  if (res.status === 401) {
    document.dispatchEvent(new CustomEvent("needs-login"));
    throw new Error("Login required");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}
```

Add to the `api` object:

```javascript
  login(password) {
    return request("/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
  },
  uploadMedia(id, file, { is_primary = false } = {}) {
    const body = new FormData();
    body.append("file", file);
    body.append("is_primary", String(is_primary));
    return request(`/persons/${id}/media/upload`, { method: "POST", body });
  },
```

- [ ] **Step 6: Add the login overlay markup**

In `frontend/index.html`, add just inside `<body>` (before `<header>`):

```html
  <div id="login-overlay" class="login-overlay" hidden>
    <form id="login-form" class="login-card">
      <h2>Family Tree</h2>
      <p class="muted">Enter the owner password.</p>
      <input type="password" id="login-password" placeholder="Password" autocomplete="current-password" />
      <button class="btn" type="submit">Sign in</button>
      <div class="login-error" id="login-error"></div>
    </form>
  </div>
```

- [ ] **Step 7: Wire the overlay in `main.js`**

At the top of `frontend/src/main.js` (after imports), add:

```javascript
const loginOverlay = document.getElementById("login-overlay");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");

document.addEventListener("needs-login", () => {
  loginOverlay.hidden = false;
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  try {
    await api.login(document.getElementById("login-password").value);
    loginOverlay.hidden = true;
    loadTree();
  } catch {
    loginError.textContent = "Incorrect password.";
  }
});
```

- [ ] **Step 8: Style the overlay**

Append to `frontend/src/styles.css`:

```css
.login-overlay { position: fixed; inset: 0; background: rgba(31,41,51,0.55);
  display: flex; align-items: center; justify-content: center; z-index: 50; }
.login-card { background: var(--panel); padding: 1.6rem; border-radius: 12px;
  box-shadow: var(--shadow); width: 280px; display: flex; flex-direction: column; gap: 0.6rem; }
.login-card h2 { margin: 0; }
.login-card input { font: inherit; padding: 0.5rem; border: 1px solid var(--border); border-radius: 7px; }
.login-error { color: var(--path); font-size: 0.82rem; min-height: 1em; }
```

- [ ] **Step 9: Run unit suite + commit**

Run: `.venv/Scripts/python.exe -m pytest -q` → Expected: PASS

```bash
git add backend/app/main.py frontend/ tests/test_serving.py
git commit -m "feat(frontend): serve SPA same-origin + owner login overlay"
```

---

### Task 6: Update e2e tests for the login gate

**Files:**
- Modify: `tests/e2e/conftest.py`
- Modify: `tests/e2e/test_ui.py`

**Interfaces:**
- Consumes: the login overlay (Task 5), `settings.admin_password`.
- Produces: e2e tests authenticate through the UI before asserting; the `live` server runs with a known `ADMIN_PASSWORD`.

- [ ] **Step 1: Set a known admin password on the live server**

In `tests/e2e/conftest.py`, in the `live` fixture's `env` dict, add:

```python
        "ADMIN_PASSWORD": "test-pass",
        "SECRET_KEY": "test-secret",
```

- [ ] **Step 2: Add a login helper and use it**

In `tests/e2e/test_ui.py`, add near the top (after `_toggle`):

```python
def _login(page: Page) -> None:
    """Dismiss the login overlay if present."""
    page.wait_for_selector("#login-overlay", state="attached")
    if page.locator("#login-overlay").is_visible():
        page.fill("#login-password", "test-pass")
        page.locator("#login-form button[type=submit]").click()
        page.wait_for_selector("#login-overlay", state="hidden")
```

Then in each test, call `_login(page)` immediately after `page.goto(live.url())` and before the first `wait_for_selector("#tree-svg g.node")` / `#empty-state` assertion. For the tests that assert `#empty-state` visible on an empty DB, log in first, then assert.

- [ ] **Step 3: Run the e2e suite**

Run: `.venv/Scripts/python.exe -m pytest -m e2e -p no:cacheprovider -q`
Expected: PASS (8 tests, now logging in first).

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/
git commit -m "test(e2e): authenticate through the login overlay"
```

---

### Task 7: Dockerfile + Railway config + deploy runbook

**Files:**
- Create: `Dockerfile`
- Create: `railway.json`
- Create: `DEPLOY.md`
- Create: `.dockerignore`
- Test: `tests/test_serving.py`

**Interfaces:**
- Consumes: `settings` env vars (`DATABASE_URL`, `MEDIA_DIR`, `ADMIN_PASSWORD`, `SECRET_KEY`).
- Produces: a container that runs `uvicorn` on `$PORT`; documented Railway setup.

- [ ] **Step 1: Write the failing test (prod-like boot)**

Append to `tests/test_serving.py`:

```python
def test_boots_with_prod_style_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("ADMIN_PASSWORD", "x")
    monkeypatch.setenv("SECRET_KEY", "y")
    # Reload config + app so the env is picked up.
    import importlib

    import backend.app.config as config
    importlib.reload(config)
    import backend.app.database as database
    importlib.reload(database)
    import backend.app.main as main
    importlib.reload(main)

    from fastapi.testclient import TestClient

    assert TestClient(main.app).get("/health").json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_serving.py::test_boots_with_prod_style_env -v`
Expected: PASS *(the app already reads env; if it fails, fix config/database before proceeding).* If it passes immediately, that is acceptable — this task's real deliverable is the deploy files below.

- [ ] **Step 3: Create `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.git/
.pytest_cache/
.ruff_cache/
media/
*.db
docs/
tests/
```

- [ ] **Step 4: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend

ENV MEDIA_DIR=/data/media \
    DATABASE_URL=sqlite:////data/app.db

# Railway sets $PORT; default 8000 for local runs.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

- [ ] **Step 5: Create `railway.json`**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": { "restartPolicyType": "ON_FAILURE", "restartPolicyMaxRetries": 3 }
}
```

- [ ] **Step 6: Create `DEPLOY.md`**

```markdown
# Deploying to Railway

1. Create a new Railway project → **Deploy from GitHub repo** → select `family-tree`.
2. Railway detects the `Dockerfile` and builds it.
3. Add a **Volume** mounted at `/data` (holds the SQLite DB + uploaded photos).
4. Set service **Variables**:
   - `ADMIN_PASSWORD` — the owner password you'll type to log in.
   - `SECRET_KEY` — a long random string (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`).
   - `DATABASE_URL=sqlite:////data/app.db`  (already defaulted in the Dockerfile)
   - `MEDIA_DIR=/data/media`               (already defaulted in the Dockerfile)
   - `PUBLIC_BASE_URL` — your Railway URL, e.g. `https://family-tree-production.up.railway.app`.
5. Deploy. Open the generated URL, log in with `ADMIN_PASSWORD`, and click **Load sample**.
6. Pushes to `main` auto-redeploy. The `/data` volume persists the DB and photos across deploys.

**Cost:** Hobby plan, ~$5/mo including the volume.
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check backend tests && .venv/Scripts/python.exe -m black --check backend tests`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add Dockerfile railway.json DEPLOY.md .dockerignore tests/test_serving.py
git commit -m "feat(deploy): Dockerfile + Railway config + deploy runbook"
```

---

## Self-Review

**Spec coverage (Phase 1 scope):**
- Owner login / session (§6) → Tasks 2, 3, 5 (overlay). ✓
- Existing routes admin-only (§6) → Task 3. ✓
- Photo uploads + `MEDIA_DIR` storage + `/media/files` serving (§4) → Task 4. ✓
- Same-origin SPA (§9) → Task 5. ✓
- Dockerfile + Railway volume/env + auto-deploy (§9) → Task 7. ✓
- Test churn from route protection (§12) → Tasks 3 (unit fixture) + 6 (e2e). ✓
- Phases 2–3 (invites/intake/review/GEDCOM) are **out of scope for this plan** and get their own plans.

**Placeholder scan:** No TBD/TODO; every code step contains real code; the one "may already pass" note in Task 7 Step 2 is an explicit, justified acceptance, not a placeholder.

**Type consistency:** `require_admin(request)` used identically in Tasks 2–3; `save_upload(...) -> (filename, url)` defined in Task 4 Step 3 and consumed in Step 4; `api.login` / `api.uploadMedia` defined in Task 5 and referenced by name; `_login(page)` defined once in Task 6 and reused.

**Known intentional churn:** Task 3 protects routes; the `client` fixture (unit) and e2e `_login` keep suites green — verified by running the full suite in Tasks 5 and 7.
