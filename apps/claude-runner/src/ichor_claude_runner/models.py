"""Pydantic request/response schemas — the wire contract with Hetzner."""

from __future__ import annotations

from datetime import UTC, datetime
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

    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    """Effort level — quality vs latency. high/xhigh for briefings, low for drill-downs."""

    mcp_config: dict | None = Field(default=None, max_length=8)
    """Optional MCP servers spec for Capability 5 (W86 STEP-4, ADR-077).
    Shape : `{"mcpServers": {"<name>": {"type": "stdio", "command": "...",
    "args": [...], "env": {...}}}}`. When set, the runner writes it to
    a tempfile and spawns `claude -p --mcp-config <path> --strict-mcp-config`.
    Keep the dict small — Pydantic enforces top-level key cap to prevent
    accidental large payloads (the actual schema is validated lazily by
    Claude CLI)."""

    allowed_tools: list[str] | None = Field(default=None, max_length=16)
    """Optional tool allowlist for `--allowedTools`. Each entry is a
    fully-qualified MCP tool name (e.g. `mcp__ichor__query_db`). None =
    no allowlist passed (still gated by `--strict-mcp-config`)."""

    max_turns: int = Field(default=0, ge=0, le=20)
    """Max agentic loop iterations (`--max-turns`). 0 = omit flag (CLI
    default). Cap at 20 to bound runaway tool-use cost."""


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

    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    claude_cli_available: bool
    persona_loaded: bool
    in_flight_subprocess: int
    """0 if idle, >0 if a briefing is currently running."""

    requests_last_hour: int
    rate_limit_remaining: int


class AgentTaskRequest(BaseModel):
    """POST /v1/agent-task — generic single-shot Claude call for Couche-2.

    Unlike `/v1/briefing-task` which packages a pre-rendered briefing
    template (assets, briefing_type), this endpoint accepts any
    system+prompt pair so Hetzner-side Couche-2 agents (CB-NLP, News-NLP,
    Sentiment, Positioning, Macro) can route through Claude per ADR-021.

    The system prompt is injected via `--append-system-prompt`, exactly
    like the persona file is for briefings — with one difference: we do
    NOT load the runner's default persona on top, since Couche-2 agents
    bring their own dedicated system prompts.
    """

    task_id: UUID = Field(default_factory=uuid4)
    system: str = Field(min_length=1, max_length=200_000)
    """Agent system prompt (e.g. SYSTEM_PROMPT_MACRO)."""

    prompt: str = Field(min_length=1, max_length=200_000)
    """User-side context (data window from Postgres assembled by Hetzner)."""

    model: Literal["opus", "sonnet", "haiku"] = "sonnet"
    """ADR-021 default mapping: sonnet for CB-NLP/News-NLP/Macro,
    haiku for Sentiment/Positioning. Caller picks per agent kind."""

    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    """Lower than briefing default — Couche-2 runs frequently and the
    output schema is smaller than a full briefing."""

    mcp_config: dict | None = Field(default=None, max_length=8)
    """Optional MCP servers spec — same shape as BriefingTaskRequest.
    Couche-2 agents will rarely use this (their job is to extract
    facts from a fixed window), but the field is symmetric in case
    a future agent type benefits from query_db lookup."""

    allowed_tools: list[str] | None = Field(default=None, max_length=16)
    """Optional `--allowedTools` allowlist. Same semantics as
    BriefingTaskRequest."""

    max_turns: int = Field(default=0, ge=0, le=20)
    """Max agentic loop iterations. Same cap as briefing (20)."""


class AgentTaskResponse(BaseModel):
    task_id: UUID
    status: Literal["success", "throttled", "subprocess_error", "timeout", "auth_failed"]
    output_text: str | None = None
    """Raw model output (typically JSON the caller validates against
    a Pydantic schema)."""

    raw_claude_json: dict | None = None
    """Full envelope from `claude -p --output-format json` — includes
    usage stats for quota monitoring."""

    error_message: str | None = None
    duration_ms: int
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
