"""Pydantic request/response schemas — the wire contract with Hetzner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BriefingTaskRequest(BaseModel):
    """Posted by Hetzner cron jobs every 6h-ish (06h/12h/17h/22h Paris)."""

    task_id: UUID = Field(default_factory=uuid4)
    briefing_type: Literal["pre_londres", "pre_ny", "ny_mid", "ny_close", "weekly", "crisis"]
    """6h Paris=pre_londres, 12h=pre_ny, 17h=ny_mid, 22h=ny_close, Sun18h=weekly, ad-hoc=crisis."""

    assets: list[str] = Field(min_length=1, max_length=8)
    """Subset of {EUR_USD, XAU_USD, NAS100_USD, USD_JPY, SPX500_USD, GBP_USD, AUD_USD, USD_CAD}."""

    context_markdown: str = Field(max_length=200_000)
    """Pre-assembled context (data tables, recent news, ML signals) injected into prompt."""

    model: Literal["opus", "sonnet", "haiku"] = "opus"
    """Claude model selection. Opus = top quality. Sonnet = faster + cheaper quota use."""

    max_tokens_out: int = Field(default=4_000, ge=100, le=32_000)
    """Output tokens budget. Briefing prose typically 2-4k tokens."""

    temperature: float = Field(default=0.5, ge=0.0, le=1.0)
    """0.5 = balance between consistency and natural prose."""


class BriefingTaskResponse(BaseModel):
    task_id: UUID
    status: Literal["success", "throttled", "subprocess_error", "timeout", "auth_failed"]
    briefing_markdown: str | None = None
    """Output of `claude -p` — raw markdown ready for journalist agent / TTS pipeline."""

    raw_claude_json: dict | None = None
    """Full JSON envelope returned by `claude -p --output-format json`. Includes
    usage stats (input/output tokens) for quota monitoring."""

    error_message: str | None = None
    duration_ms: int
    """Wall time of the subprocess run."""

    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    claude_cli_available: bool
    persona_loaded: bool
    in_flight_subprocess: int
    """0 if idle, >0 if a briefing is currently running."""

    requests_last_hour: int
    rate_limit_remaining: int
