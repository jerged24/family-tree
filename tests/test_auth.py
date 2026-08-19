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
