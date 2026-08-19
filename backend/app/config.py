"""Application settings, loaded from environment / .env (Pydantic v2)."""

from __future__ import annotations

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. See .env.example."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./familytree.db"
    # NoDecode stops pydantic-settings from JSON-decoding the env value first, so a
    # plain comma-separated CORS_ORIGINS string reaches the validator below (a raw
    # string like "http://a,http://b" is not valid JSON and would otherwise error).
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]
    sql_echo: bool = False
    admin_password: str = "changeme"
    secret_key: str = "dev-insecure-secret-change-me"
    media_dir: str = "./media"
    public_base_url: str = ""  # e.g. https://app.up.railway.app; "" → derive from request

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Allow CORS_ORIGINS to be a comma-separated string in the environment."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
