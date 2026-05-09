"""Pydantic settings, env-driven (`ICHOR_MCP_*`).

Loaded from `.env` next to the launch CWD or from process env. Used
by the lifespan to instantiate the httpx client; nothing else reaches
into Settings.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ICHOR_MCP_",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Backend wire ─────────────────────────────────────────────
    api_base_url: str = "https://api.fxmilyapp.com"
    """Hetzner apps/api root. The MCP server posts to {base}/v1/tools/*."""

    api_service_token: str = ""
    """Shared secret sent as `X-Ichor-Tool-Token`. Must equal
    apps/api's `ICHOR_API_TOOL_SERVICE_TOKEN`. Empty disables the
    header (only valid when apps/api also has it empty, dev only)."""

    # ── Cloudflare Access service token (PRE-1, optional today) ─
    cf_access_client_id: str = ""
    """`CF-Access-Client-Id` header. Empty when CF Access not yet
    enforced on the apps/api edge (today). Set this when PRE-1 lands."""

    cf_access_client_secret: str = ""
    """`CF-Access-Client-Secret` header. Pair with the id above."""

    # ── HTTP timeouts ────────────────────────────────────────────
    request_timeout_sec: float = 30.0
    """Hard timeout per `/v1/tools/*` round-trip. Generous for the
    Hetzner→Win11 RTT plus a 1000-row payload serialisation."""

    connect_timeout_sec: float = 5.0
    """Separate connect-phase budget so a degraded edge surfaces fast."""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
