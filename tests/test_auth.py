"""Auth + settings tests."""

from __future__ import annotations


def test_settings_read_admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("MEDIA_DIR", "/tmp/ft-media")
    from backend.app.config import Settings

    s = Settings()
    assert s.admin_password == "s3cret"
    assert s.media_dir == "/tmp/ft-media"
    assert hasattr(s, "secret_key") and hasattr(s, "public_base_url")


def _fresh_client():
    from backend.app.main import app
    from tests.conftest import isolated_client

    # Isolated in-memory DB (same helper the `client` fixture uses) — never touches
    # the real on-disk sqlite file, and never leaves a stray familytree.db behind.
    return isolated_client(app)


def test_login_rejects_bad_password():
    c = _fresh_client()
    assert c.post("/admin/login", json={"password": "wrong"}).status_code == 401


def test_login_then_protected_route_ok():
    from backend.app.config import settings

    c = _fresh_client()
    assert c.post("/admin/login", json={"password": settings.admin_password}).status_code == 200
    # /persons is protected in Task 3; here we assert login itself round-trips.
    assert c.post("/admin/logout").status_code == 200


def test_persons_requires_admin():
    c = _fresh_client()  # not logged in
    assert c.get("/persons").status_code == 401


def test_persons_ok_after_login():
    from backend.app.config import settings

    c = _fresh_client()
    c.post("/admin/login", json={"password": settings.admin_password})
    assert c.get("/persons").status_code == 200


def test_create_app_fails_on_default_secrets_in_production(monkeypatch):
    """In a non-dev env, create_app() must refuse to boot with default secrets."""
    import pytest

    from backend.app import main
    from backend.app.config import settings

    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "admin_password", "changeme")
    monkeypatch.setattr(settings, "secret_key", "dev-insecure-secret-change-me")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        main.create_app()


def test_create_app_ok_in_production_with_real_secrets(monkeypatch):
    """Non-default secrets in production must NOT trip the guard."""
    from backend.app import main
    from backend.app.config import settings

    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "admin_password", "a-real-owner-password")
    monkeypatch.setattr(settings, "secret_key", "a-long-random-production-secret")
    # Should not raise.
    main.create_app()
