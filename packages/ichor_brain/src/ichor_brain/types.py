"""Pydantic schemas for the 4-pass pipeline.

The shapes here mirror the columns in `session_card_audit` (migration
0005). Each pass produces one of these objects; the orchestrator stitches
them into a `SessionCard`.

Conviction is capped at 95 — anything above is treated as a red flag
under the macro-frameworks doctrine ("100% conviction never exists").
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ────────────────────────────── enums ──────────────────────────────

SessionType = Literal["pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"]
"""5 session windows. ny_mid (17:00 Paris) and ny_close (22:00 Paris)
were registered as systemd timers (cf scripts/hetzner/) but missing
from this Literal — every batch since 2026-05-04 14:23 was rejected
with `unknown session_type` before even hitting the runner."""

VALID_SESSION_TYPES: frozenset[str] = frozenset(get_args(SessionType))
"""Single source of truth for runtime validation across CLI runners.

Derived directly from `SessionType` — adding/removing a window in the
Literal automatically updates this set. Replaces the hardcoded
`_VALID_SESSIONS = {...}` duplicates that drifted in
`run_session_card.py` vs `run_session_cards_batch.py` (cf ADR-024 fix 2,
note "future drift is possible" — closed by ADR-031)."""
BiasDirection = Literal["long", "short", "neutral"]
RegimeQuadrant = Literal[
    "haven_bid",
    "funding_stress",
    "goldilocks",
    "usd_complacency",
]
CriticVerdict = Literal["approved", "amendments", "blocked"]


# ─────────────────────── per-pass output models ────────────────────────


class RegimeReading(BaseModel):
    """Output of Pass 1 — Régime global.

    Reads the macro trinity (DXY + 10Y yields + VIX) plus dollar smile
    inputs (real yields, foreign rate diffs) and outputs which of the
    four quadrants the market is currently in, with a 1-2 sentence
    rationale.
    """

    model_config = ConfigDict(extra="forbid")

    quadrant: RegimeQuadrant
    rationale: str = Field(min_length=20, max_length=2000)
    confidence_pct: float = Field(ge=0.0, le=100.0)
    macro_trinity_snapshot: dict[str, float | None] = Field(
        default_factory=dict,
        description="DXY, US10Y, VIX, DFII10, BAMLH0A0HYM2 levels at read time.",
    )


class AssetSpecialization(BaseModel):
    """Output of Pass 2 — Asset specialization for a single asset.

    Applies the asset-specific framework (e.g. EUR/USD = US-DE 10Y diff
    + ECB-Fed expectations) on top of the régime reading.
    """

    model_config = ConfigDict(extra="forbid")

    asset: str
    bias_direction: BiasDirection
    conviction_pct: float = Field(ge=0.0, le=95.0)
    magnitude_pips_low: float | None = None
    magnitude_pips_high: float | None = None
    timing_window_start: datetime | None = None
    timing_window_end: datetime | None = None
    mechanisms: list[dict[str, Any]] = Field(default_factory=list)
    """Each entry: {claim: str, sources: list[str]}."""
    catalysts: list[dict[str, Any]] = Field(default_factory=list)
    """Each entry: {time: iso8601, event: str, expected_impact: str}."""
    correlations_snapshot: dict[str, float | None] = Field(default_factory=dict)
    """Each value is the rolling correlation. None when unavailable."""
    polymarket_overlay: list[dict[str, Any]] = Field(default_factory=list)


class StressTest(BaseModel):
    """Output of Pass 3 — Bull case stress-test (devil's advocate).

    Asked to argue the OPPOSITE of Pass 2's bias and rate the strongest
    counter-claims. Forces honest probability calibration.
    """

    model_config = ConfigDict(extra="forbid")

    counter_claims: list[dict[str, Any]] = Field(default_factory=list)
    """Each entry: {claim: str, strength_pct: float, sources: list[str]}."""
    revised_conviction_pct: float = Field(ge=0.0, le=95.0)
    """Pass 2 conviction adjusted after stress-testing. May be lower."""
    notes: str = Field(default="", max_length=2000)


class InvalidationConditions(BaseModel):
    """Output of Pass 4 — Invalidation conditions.

    The single most important section per Tetlock's superforecaster
    research: explicit pre-commitment to "this thesis is wrong if X".
    """

    model_config = ConfigDict(extra="forbid")

    conditions: list[dict[str, Any]] = Field(min_length=1)
    """Each entry: {condition: str, threshold: str|float, source: str}."""
    review_window_hours: int = Field(default=8, ge=1, le=168)


# ─────────────────────── final assembled card ────────────────────────


class CriticDecision(BaseModel):
    """Outcome of the Critic Agent gate."""

    model_config = ConfigDict(extra="forbid")

    verdict: CriticVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    n_findings: int = 0
    findings: list[dict[str, Any]] = Field(default_factory=list)
    suggested_footer: str = ""


class SessionCard(BaseModel):
    """Final structured output of the 4-pass pipeline for one asset.

    Persisted into `session_card_audit` (one row per asset per session).
    Brier-score outcome columns are filled later, after the session
    closes (CHUNK 7 will add the realized-outcome reconciler).
    """

    model_config = ConfigDict(extra="forbid")

    session_type: SessionType
    asset: str
    model_id: str = "claude-opus-4-7"
    generated_at: datetime
    regime: RegimeReading
    specialization: AssetSpecialization
    stress: StressTest
    invalidation: InvalidationConditions
    critic: CriticDecision
    source_pool_hash: str
    """SHA-256 of the input data pool, used as a cache key + reproducibility anchor."""

    claude_duration_ms: int = 0
    """Sum of wall-times across the 4 runner calls (excludes critic)."""

    drivers: list[dict[str, Any]] | None = None
    """Per-factor contribution snapshot from confluence_engine at
    generation time. Shape : list[{factor: str, contribution: float,
    evidence: str, source: str | None}]. Optional — None for legacy
    pipelines that don't compute confluence. Persisted to
    session_card_audit.drivers (migration 0026) so brier_optimizer V2
    can fit per-factor SGD on a real (signals, outcomes) matrix."""

    scenarios: list[dict[str, Any]] | None = None
    """Pass-6 7-bucket scenario decomposition (ADR-085, W105c). Shape :
    list[{label: str, p: float, magnitude_pips: [low, high],
    mechanism: str}] — 7 entries exactly, sum(p) == 1.0, all p in
    [0, 0.95]. None for pipelines that don't run Pass-6 (pre-W105
    legacy or `tool_config.enabled_for_passes` excludes `scenarios`).
    Persisted as `session_card_audit.scenarios` JSONB column
    (migration 0039) — the W108 reconciler reads it to compute Brier
    multi-class K=7 vs `realized_scenario_bucket`."""

    key_levels: list[dict[str, Any]] | None = None
    """ADR-083 D3 KeyLevel snapshot at orchestrator finalization (r62).
    Shape : list[{asset: str, level: float, kind: str, side: str,
    source: str, note: str}] — mirror of `/v1/key-levels` response
    items. Empty list `[]` is the canonical "all bands NORMAL" state ;
    None for pipelines that don't compose the snapshot (pre-r62
    legacy). Persisted as `session_card_audit.key_levels` JSONB
    column (migration 0049, NOT NULL DEFAULT `'[]'::jsonb`) — D4
    frontend replay + Brier post-mortem read this snapshot rather
    than recomputing."""

    @field_validator("asset")
    @classmethod
    def _normalize_asset(cls, v: str) -> str:
        return v.strip().upper().replace("-", "_")


__all__ = [
    "VALID_SESSION_TYPES",
    "AssetSpecialization",
    "BiasDirection",
    "CriticDecision",
    "CriticVerdict",
    "InvalidationConditions",
    "RegimeQuadrant",
    "RegimeReading",
    "SessionCard",
    "SessionType",
    "StressTest",
]


# `Annotated` is imported for downstream consumers that want stricter
# type narrowing. Suppress the unused-import warning in static analyzers.
_ = Annotated
