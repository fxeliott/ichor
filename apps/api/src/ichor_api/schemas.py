"""Pydantic API schemas — request/response shapes (separate from ORM models)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

_LOG = logging.getLogger(__name__)


class BriefingOut(BaseModel):
    id: UUID
    briefing_type: str
    triggered_at: datetime
    assets: list[str]
    status: str
    briefing_markdown: str | None
    claude_duration_ms: int | None
    audio_mp3_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BriefingListOut(BaseModel):
    total: int
    items: list[BriefingOut]


class AlertOut(BaseModel):
    id: UUID
    alert_code: str
    severity: Literal["info", "warning", "critical"]
    asset: str | None
    triggered_at: datetime
    metric_name: str
    metric_value: float
    threshold: float
    direction: Literal["above", "below", "cross_up", "cross_down"]
    title: str
    description: str | None
    acknowledged_at: datetime | None

    model_config = {"from_attributes": True}


class BiasSignalOut(BaseModel):
    id: UUID
    asset: str
    horizon_hours: int
    direction: Literal["long", "short", "neutral"]
    probability: float = Field(ge=0.0, le=1.0)
    credible_interval_low: float
    credible_interval_high: float
    contributing_predictions: list[UUID]
    weights_snapshot: dict[str, float]
    generated_at: datetime

    model_config = {"from_attributes": True}


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    db_connected: bool
    redis_connected: bool
    claude_runner_reachable: bool | None = None  # tested only when explicitly asked


class CollectorLag(BaseModel):
    source: str
    last_fetched_at: datetime | None
    minutes_stale: float | None


# ─────────────────────────────────────────────────────────────────────
# SessionCard typed sub-schemas — Phase 2 delta.
#
# These shapes extend the dashboard's contract for SessionCardOut with
# fields that today live untyped inside `claude_raw_response` JSONB.
# Population of these fields in `session_card_audit` is the responsibility
# of the brain pipeline runner (apps/claude-runner) ; routers serialize
# them as `None` until the runner upgrade lands. The frontend can already
# code against the typed contract.
# ─────────────────────────────────────────────────────────────────────


class TradePlan(BaseModel):
    """Pre-computed risk geometry for a session card.

    All prices are in the asset's quoted units (FX = pip, indices =
    points, gold = $). Mirrors the trade plan UI on /sessions/[asset].
    """

    entry_low: float
    entry_high: float
    invalidation_level: float
    invalidation_condition: str
    tp_rr3: float
    """Take-profit at RR 3:1 — primary close-90% target (cf SPEC §3.8)."""
    tp_rr15: float | None = None
    """Trail target at RR 15:1 — residual 10% chase. None if scheme=skip."""
    partial_scheme: str
    """Human-readable scheme, e.g. "90 % @ RR3 · trail 10 % vers RR15+"."""


class ConfluenceDriver(BaseModel):
    """One factor contributing to the asset's confluence score."""

    factor: str
    contribution: float
    """Signed in [-1, +1] — positive = supports the bias_direction."""


class IdeaSet(BaseModel):
    """Brain Pass 2 distilled trade narrative."""

    top: str
    """One-line headline trade idea."""
    supporting: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CalibrationStat(BaseModel):
    """Per-asset Brier track record snapshot at card generation time."""

    brier: float
    sample_size: int
    trend: Literal["bull", "bear", "neutral"]


class Pass4MagnitudeRange(BaseModel):
    """Pip range expected if the scenario realizes."""

    low: float = Field(ge=0.0)
    high: float = Field(ge=0.0)


class Pass4Scenario(BaseModel):
    """One of the 7 mutually-exclusive scenarios produced by brain Pass 4.

    Mirrors the JSON contract documented in /learn/scenarios-tree :
        {id, label, probability, bias, magnitude_pips, primary_mechanism,
         invalidation, [counterfactual_anchor]}

    The `probability` field is calibrated by Pass 4 ; the seven scenarios'
    probabilities sum to ≈ 1.0 (a "tail" placeholder is added if Pass 4
    produces fewer than 7 high-conviction branches).
    """

    id: str
    """Stable id (s1..s7) so Pass 5 can reference scenarios for counterfactual probing."""
    label: str
    probability: float = Field(ge=0.0, le=1.0)
    bias: Literal["bull", "bear", "neutral"]
    magnitude_pips: Pass4MagnitudeRange
    primary_mechanism: str
    invalidation: str
    counterfactual_anchor: str | None = None
    """When set, /scenarios/[asset] surfaces a "Pass 5" button to probe this anchor."""


class Pass4ScenarioTree(BaseModel):
    """Output bundle for /v1/sessions/{asset}/scenarios — the 7-arbre.

    The tree always carries a `tail_padded` flag : when Pass 4 produces
    fewer than 7 scenarios, the runner pads with a `tail` placeholder
    (low-probability catch-all) so the sum approaches 1.0. Frontend can
    visually distinguish padded vs canonical scenarios.
    """

    asset: str
    generated_at: datetime
    session_card_id: UUID | None = None
    """Source `session_card_audit.id` if extracted from a persisted card."""
    n_scenarios: int = Field(ge=0, le=7)
    sum_probability: float = Field(ge=0.0, le=1.05)
    """Always close to 1.0 (some rounding allowed up to 5 %)."""
    tail_padded: bool = False
    scenarios: list[Pass4Scenario]


def _candidate_payload(raw: Any | None) -> dict[str, Any] | None:
    """Return the dict that holds the typed sub-objects, defending against
    different shapes that the brain runner has produced over time :

      - direct dict at root
      - nested under {"session_card": {...}}
      - nested under {"output": {...}}
      - nested under {"session": {...}}

    Returns None if no candidate dict can be located.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        if any(k in raw for k in ("trade_plan", "ideas", "confluence_drivers", "thesis")):
            return raw
        for key in ("session_card", "output", "session"):
            inner = raw.get(key)
            if isinstance(inner, dict):
                return inner
    return None


def extract_thesis(claude_raw_response: Any | None) -> str | None:
    """Pull the one-line thesis from the brain Pass 2 narrative."""
    payload = _candidate_payload(claude_raw_response)
    if payload is None:
        return None
    val = payload.get("thesis")
    if isinstance(val, str) and val.strip():
        return val.strip()[:512]  # cap defensively
    return None


def extract_trade_plan(claude_raw_response: Any | None) -> TradePlan | None:
    """Best-effort projection of Pass 2 trade-plan onto the typed schema."""
    payload = _candidate_payload(claude_raw_response)
    if payload is None:
        return None
    raw_plan = payload.get("trade_plan")
    if not isinstance(raw_plan, dict):
        return None
    try:
        return TradePlan.model_validate(raw_plan)
    except Exception as exc:
        _LOG.debug("extract_trade_plan: skipping malformed entry: %s", exc)
        return None


def extract_ideas(claude_raw_response: Any | None) -> IdeaSet | None:
    """Pull the brain Pass 2 ideas (top + supporting + risks)."""
    payload = _candidate_payload(claude_raw_response)
    if payload is None:
        return None
    raw_ideas = payload.get("ideas")
    if not isinstance(raw_ideas, dict):
        return None
    try:
        return IdeaSet.model_validate(raw_ideas)
    except Exception as exc:
        _LOG.debug("extract_ideas: skipping malformed entry: %s", exc)
        return None


def extract_confluence_drivers(
    claude_raw_response: Any | None,
) -> list[ConfluenceDriver] | None:
    """Project the per-driver confluence breakdown."""
    payload = _candidate_payload(claude_raw_response)
    if payload is None:
        return None
    raw = payload.get("confluence_drivers")
    if not isinstance(raw, list):
        return None
    out: list[ConfluenceDriver] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(ConfluenceDriver.model_validate(item))
        except Exception as exc:
            _LOG.debug("extract_confluence_drivers: skipping malformed entry: %s", exc)
            continue
    return out if out else None


def extract_calibration_stat(
    claude_raw_response: Any | None,
) -> CalibrationStat | None:
    """Project the per-asset Brier snapshot stamped by the runner."""
    payload = _candidate_payload(claude_raw_response)
    if payload is None:
        return None
    raw = payload.get("calibration")
    if not isinstance(raw, dict):
        return None
    try:
        return CalibrationStat.model_validate(raw)
    except Exception as exc:
        _LOG.debug("extract_calibration_stat: skipping malformed entry: %s", exc)
        return None


def extract_pass4_scenarios(mechanisms: Any | None) -> list[Pass4Scenario]:
    """Best-effort extraction of Pass 4 scenarios from `session_card_audit.mechanisms`.

    The `mechanisms` JSONB column is loosely typed today — runners persist
    a list of dicts that MAY include a top-level "scenarios" key, OR a
    list-of-scenarios at the root, OR neither (older cards). This helper
    is permissive : it returns `[]` when the shape doesn't match, rather
    than raising. Routers that surface scenarios use the empty-list as
    the "Pass 4 schema not populated yet" signal.
    """
    if mechanisms is None:
        return []
    payload: list[dict[str, Any]] = []
    if isinstance(mechanisms, dict) and isinstance(mechanisms.get("scenarios"), list):
        payload = mechanisms["scenarios"]
    elif isinstance(mechanisms, list):
        payload = [m for m in mechanisms if isinstance(m, dict)]
    out: list[Pass4Scenario] = []
    for item in payload:
        try:
            out.append(Pass4Scenario.model_validate(item))
        except Exception as exc:
            _LOG.debug("extract_pass4_scenarios: skipping malformed entry: %s", exc)
            continue
    return out


class SessionCardOut(BaseModel):
    """One row of `session_card_audit` projected for the dashboard.

    Phase 2 delta : adds optional typed fields (`thesis`, `trade_plan`,
    `ideas`, `confluence_drivers`, `calibration`) that surface the
    structured sub-objects currently buried in `claude_raw_response`.
    These default to `None` until the brain runner populates them ; the
    frontend SessionCard component already consumes this shape.
    """

    id: UUID
    generated_at: datetime
    session_type: Literal["pre_londres", "pre_ny", "event_driven"]
    asset: str
    model_id: str
    regime_quadrant: str | None
    bias_direction: Literal["long", "short", "neutral"]
    conviction_pct: float
    magnitude_pips_low: float | None
    magnitude_pips_high: float | None
    timing_window_start: datetime | None
    timing_window_end: datetime | None
    mechanisms: Any | None = None
    invalidations: Any | None = None
    catalysts: Any | None = None
    correlations_snapshot: Any | None = None
    polymarket_overlay: Any | None = None
    # r62 (ADR-083 D3) : KeyLevel snapshot at card generation. Mirror
    # of /v1/key-levels response items shape — list[{asset, level,
    # kind, side, source, note}]. Default `[]` covers legacy rows
    # that predate migration 0049 ; never None on rows persisted
    # post-r62 because the column is NOT NULL DEFAULT '[]'::jsonb.
    key_levels: list[dict[str, Any]] = []
    source_pool_hash: str
    critic_verdict: str | None
    critic_findings: Any | None = None
    claude_duration_ms: int | None
    realized_close_session: float | None
    realized_at: datetime | None
    brier_contribution: float | None
    created_at: datetime

    # ── Phase 2 typed enrichment (default None until populated) ──
    thesis: str | None = None
    trade_plan: TradePlan | None = None
    ideas: IdeaSet | None = None
    confluence_drivers: list[ConfluenceDriver] | None = None
    calibration: CalibrationStat | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_row(cls, row: Any) -> SessionCardOut:
        """Build SessionCardOut + extract typed Phase-2 enrichments.

        Reads the ORM row's columns then enriches the output with the
        4 typed sub-objects projected from `claude_raw_response`. All
        extractors are permissive : missing / malformed payloads land
        as None without raising.
        """
        base = cls.model_validate(row)
        raw = getattr(row, "claude_raw_response", None)
        if raw is None:
            return base
        return base.model_copy(
            update={
                "thesis": extract_thesis(raw),
                "trade_plan": extract_trade_plan(raw),
                "ideas": extract_ideas(raw),
                "confluence_drivers": extract_confluence_drivers(raw),
                "calibration": extract_calibration_stat(raw),
            }
        )


class SessionCardListOut(BaseModel):
    """Latest card per asset, ordered by generated_at DESC."""

    total: int
    items: list[SessionCardOut]


class HealthDetailedOut(HealthOut):
    """Extended /healthz/detailed — used by Grafana + RUNBOOK-011."""

    last_briefing_at: datetime | None
    minutes_since_last_briefing: float | None
    unack_alerts_critical: int
    unack_alerts_warning: int
    collectors: list[CollectorLag]


# ─────────────────────────────────────────────────────────────────────
# Capability 5 client-tool wire schemas (W85, ADR-071 STEP-3 / ADR-077)
# ─────────────────────────────────────────────────────────────────────
# Sit in front of `services.tool_query_db` and `services.tool_calc`.
# Consumed by the Win11 apps/ichor-mcp stdio server (which forwards
# every MCP tool call to /v1/tools/* over HTTPS), so the DB credentials
# stay on Hetzner and the immutable tool_call_audit row gets inserted
# atomically with the same async session that ran the tool body.


class _ToolAuditFields(BaseModel):
    """Shared audit-trail fields. Mirror tool_call_audit columns."""

    agent_kind: str = Field(
        default="manual",
        max_length=64,
        description=(
            "4-pass agent that invoked the tool (e.g. 'pass1_regime', "
            "'pass5_counterfactual'). Default 'manual' for ad-hoc CLI "
            "invocations from `claude -p --mcp-config`."
        ),
    )
    pass_index: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Orchestrator pass index. Pass 5 = counterfactual.",
    )
    session_card_id: UUID | None = Field(
        default=None,
        description="FK to session_card_audit when invoked inside a 4-pass run.",
    )


class ToolQueryDbIn(_ToolAuditFields):
    sql: str = Field(min_length=1, max_length=8192)
    max_rows: int | None = Field(default=None, ge=1, le=1000)


class ToolQueryDbOut(BaseModel):
    rows: list[dict[str, Any]]
    duration_ms: int
    tables_referenced: list[str]
    truncated: bool = Field(
        description="True when the result set was capped to max_rows / HARD_MAX_ROWS."
    )


class ToolCalcIn(_ToolAuditFields):
    operation: str = Field(min_length=1, max_length=64)
    values: list[float] = Field(min_length=1, max_length=10000)
    params: dict[str, Any] = Field(default_factory=dict)


class ToolCalcOut(BaseModel):
    # Shape varies per op (float for percentile / annualize_vol / correlation,
    # list[float] otherwise). Use `Any` to avoid coercion gymnastics.
    result: Any
    duration_ms: int
