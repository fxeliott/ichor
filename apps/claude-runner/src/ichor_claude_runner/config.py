"""Pydantic settings, env-driven."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the claude-runner service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ICHOR_RUNNER_",
        extra="ignore",
    )

    # --- HTTP server ---
    environment: Literal["development", "staging", "production"] = "production"
    """Drives startup safety guards (CF Access required in production etc.)."""

    host: str = "127.0.0.1"
    port: int = 8765
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Claude subprocess ---
    claude_binary: str = "claude"
    """Path to `claude` CLI. On Win11 default install: `claude` is on PATH."""

    claude_default_model: Literal["opus", "sonnet", "haiku"] = "opus"
    """Maps to claude --model flag. Opus 4.7 = top quality for briefings."""

    claude_timeout_sec: int = 360
    """Hard timeout per `claude -p` invocation. 6 min default per briefing."""

    persona_file: Path = Path(__file__).resolve().parent / "personas" / "ichor.md"
    """Persona prompt loaded into --append-system on every call."""

    workdir: Path = Path.home() / ".ichor-runner-work"
    """Scratch dir for intermediate files (created at startup if missing)."""

    # --- Cloudflare Access auth ---
    require_cf_access: bool = True
    """If True, every request must carry valid Cf-Access-Jwt-Assertion header."""

    cf_access_team_domain: str = ""
    """e.g. 'eliot' for eliot.cloudflareaccess.com. Empty if Cloudflare team not set yet."""

    cf_access_aud_tag: str = ""
    """Audience tag of the Cloudflare Access application (32 hex chars)."""

    # --- Quota self-protection ---
    max_concurrent_subprocess: int = 1
    """Don't run multiple `claude -p` at once — Max 20x is single-user."""

    rate_limit_per_hour: int = 60
    """Reject if more than N briefing requests in last hour.
    Pre-Phase-2 default was 30 (4-5/day Phase 0). Bumped to 60 in
    round-10 2026-05-12 after batch test revealed 4/6 cards 429-failed
    when Pass-6 enabled (each card = 5 passes × 6 assets = 30 calls,
    saturated the 30/h ceiling). Claude Max 20x quota allows 60/h
    comfortably. ICHOR_RUNNER_RATE_LIMIT_PER_HOUR env override
    supported (e.g. raise to 120 during catch-up reconciliation)."""


_settings: Settings | None = None


def get_settings() -> Settings:
    """Lazy singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
