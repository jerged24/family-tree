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
   - `ENV=production` — enforces the fail-fast guard: the app refuses to boot if
     `ADMIN_PASSWORD`/`SECRET_KEY` are still at their insecure defaults (already
     defaulted in the Dockerfile). Also enables the Secure flag on the session cookie.
5. Deploy. Open the generated URL, log in with `ADMIN_PASSWORD`, and click **Load sample**.
6. Pushes to `main` auto-redeploy. The `/data` volume persists the DB and photos across deploys.

**Cost:** Hobby plan, ~$5/mo including the volume.
