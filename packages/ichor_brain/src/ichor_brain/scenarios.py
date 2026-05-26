"""Pass-6 scenario_decompose — 7-bucket stratified probability schema.

Canonical home of the Pass-6 contract surface (ADR-085). The schema +
`cap_and_normalize` + `bucket_for_zscore` live here in `ichor_brain`
so that :

  * `packages/ichor_brain/passes/scenarios.py` (Pass-6 LLM caller) can
    import directly without a lazy-import indirection or a
    cross-package dependency on `apps/api`.
  * `apps/api/src/ichor_api/services/scenarios.py` re-exports verbatim
    so existing CI guards (`test_invariants_ichor.py`) + tests
    (`test_scenarios.py`) + the ORM/persistence column shape stay
    byte-equivalent at the public surface.

Pre-W105d this module lived at `apps/api/.../services/scenarios.py` ;
moved here 2026-05-12 (W105 architecture cleanup — closing the
ichor-trader audit JAUNE flag identified during the 2026-05-12
audit) so the `ichor_brain` package can stay installable standalone
while Pass-6 still uses the schema natively.

Exposes :

- `BUCKET_LABELS`           — the 7 canonical labels in order, frozen
- `BUCKET_Z_THRESHOLDS`     — z-score boundaries from realized returns
- `Scenario`                — Pydantic model for one bucket emission
- `ScenarioDecomposition`   — Pydantic model wrapping the 7-list with
                              sum=1 + cap-95 + unique-label validators
- `cap_and_normalize`       — proportional clipping to enforce
                              cap-95 + sum=1 deterministically
- `bucket_for_zscore`       — reverse lookup used by the realized-
                              outcome reconciler (W105g)

The module is import-side-effect-free and has zero DB / network access
so it can be unit-tested in isolation, used by the orchestrator without
pulling SQLAlchemy, and CI-guarded against the ADR-017 boundary.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ADR-017 boundary regression guard — the `mechanism` string emitted by
# Pass-6 (LLM Claude Sonnet 4.6 medium effort) must never reference a
# trade instruction. Word-boundary case-insensitive. Catches: `BUY`,
# `SELL`, `TP`, `SL`, `long entry`, `short entry`. Tested via
# test_invariants_ichor.py + test_scenarios.py at construction time.
_FORBIDDEN_MECHANISM_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

BucketLabel = Literal[
    "crash_flush",
    "strong_bear",
    "mild_bear",
    "base",
    "mild_bull",
    "strong_bull",
    "melt_up",
]

# The 7 canonical labels in stratification order (most-bearish → most-bullish).
# Frozen tuple — never mutate. CI-guarded via `test_invariants_ichor.py`
# Pass-6 extension (W105f).
BUCKET_LABELS: tuple[BucketLabel, ...] = (
    "crash_flush",
    "strong_bear",
    "mild_bear",
    "base",
    "mild_bull",
    "strong_bull",
    "melt_up",
)

# Z-score boundaries (lower-inclusive, upper-exclusive except last) that
# partition the realized-return space into the 7 buckets. Calibrated per
# (asset, session_type) using rolling 252-day historical returns ;
# see ADR-085 §"The 7 buckets" + W105b `services/scenario_calibration.py`.
# These canonical thresholds are the default ; per-asset overrides will
# live in `scenario_calibration_bins` (migration 0039, W105a).
BUCKET_Z_THRESHOLDS: tuple[float, ...] = (-2.5, -1.0, -0.25, 0.25, 1.0, 2.5)

# Conviction cap per ADR-022 — no individual bucket can express certainty.
CAP_95: float = 0.95

# Tolerance used for sum=1 validation. 1e-6 is tight enough to catch real
# bugs but loose enough to absorb float arithmetic drift after normalize.
SUM_TOLERANCE: float = 1e-6


# r161 Strand A — InvalidationCondition canonical metric whitelist. Mirror of
# the Ichor alerts catalog name-space (cf. `services/alerts/evaluator.py` +
# `ALL_ALERTS`). Each entry MUST be polled by an existing collector OR
# computable from already-persisted observations — never inventing a metric
# the system cannot measure. Extension policy : any new metric requires (a)
# a collector or service that persists current values, (b) corresponding
# catalog entry in `alerts/evaluator.py`, (c) test coverage. Doctrine #4 SSOT.
INVALIDATION_METRIC_NAMES: frozenset[str] = frozenset(
    {
        # Cross-asset FX + DXY (polygon_intraday + FRED)
        "DXY",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCAD",
        "AUDUSD",
        # Equity indices (polygon_intraday)
        "SPX500",
        "NAS100",
        # Commodities (polygon_intraday + FRED proxies)
        "XAUUSD",
        "BRENT",
        "WTI",
        # Rates + curve (FRED)
        "FRED_DGS10",
        "FRED_DGS2",
        "FRED_DGS30",
        "FRED_DFII10",
        "FRED_T10Y2Y",
        "FRED_T10YIE",
        # Vol / risk (FRED + CBOE)
        "VIX",
        "VVIX",
        "SKEW",
        "MOVE",
        # Credit / liquidity (FRED)
        "FRED_BAMLH0A0HYM2",
        "FRED_NFCI",
        "FRED_DTWEXBGS",
        # Inflation / growth (FRED)
        "FRED_CPIAUCSL",
        "FRED_PCEPI",
        "FRED_PAYEMS",
        # Geopolitical / event keyword polled via news_nlp + gdelt
        "EVENT_HORMUZ_VOLUME_PCT",
        "EVENT_IRAN_CEASEFIRE_STATUS",
        "EVENT_TRUMP_TARIFF_STATUS",
        # Polymarket probability markets
        "POLY_FED_CUTS_2026",
        "POLY_FED_HIKE_2026",
        "POLY_RECESSION_2026",
    }
)


# r161 Strand A — descriptive-only ADR-017 boundary applied to InvalidationCondition
# `description` field. Same forbidden-token set as `_FORBIDDEN_MECHANISM_TOKENS_RE`
# but reused at the validator site below for clarity (single source of truth on
# regex pattern remains :50-53).


class InvalidationCondition(BaseModel):
    """One measurable threshold that, if breached, makes the parent scenario
    less-likely-to-realize (or fully invalidated, depending on `severity`).

    Doctrine alignment :
      - ADR-017 boundary : descriptive only. ``description`` is what changes
        in the world if the condition fires — never a trade instruction.
      - Doctrine #4 SSOT : ``metric_name`` is enforced against
        ``INVALIDATION_METRIC_NAMES`` so we cannot reference a metric that
        Ichor has no way to poll.
      - Doctrine #11 calibrated honesty : ``severity`` lets the LLM tier
        invalidation strength (hard / soft / note) rather than collapsing
        all to a single boolean fire.

    Wire-up : when the Pass-6 LLM generates scenarios, it lists for each
    bucket the conditions that — if measured against current data —
    contradict the bucket's mechanism. A downstream service
    (``services/scenario_invalidation_monitor.py``, r161 Strand D) polls
    these conditions against current observations + fires through the
    canonical ``alerts_runner.check_metric()`` quadruplet
    (services/alerts/evaluator.py + Alert ORM + cli/run_*_check.py +
    register-cron-*.sh) when a hard breach materialises.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    metric_name: str = Field(min_length=2, max_length=64)
    """Canonical Ichor metric name. MUST be in
    ``INVALIDATION_METRIC_NAMES`` (whitelist enforced by validator below).
    Maps to either a polygon_intraday ticker, a FRED series_id, an
    economic_events column, or a structured news-keyword polled feed."""

    threshold: float
    """Numerical threshold the metric is compared against. Unit varies by
    metric (yield % for FRED_DGS10, index points for VIX, USD spot for
    XAUUSD, etc.). The Pass-6 LLM is responsible for emitting a threshold
    consistent with the metric's natural unit ; downstream monitor is
    metric-aware via the ``alerts/evaluator.py`` catalog."""

    direction: Literal["above", "below", "crosses_above", "crosses_below"]
    """Threshold comparison operator. ``above``/``below`` = current value
    >/< threshold. ``crosses_above``/``crosses_below`` = last-tick was on
    the other side AND current-tick is on this side (state transition
    detection ; needs 2-tick memory in the monitor)."""

    severity: Literal["hard", "soft", "note"]
    """How strongly the breach invalidates the scenario.
      - ``hard`` : scenario fully invalidated, conviction → 0, ``p`` should
        be redistributed across remaining buckets per ``cap_and_normalize``.
      - ``soft`` : scenario partially invalidated, conviction should be
        reduced (no auto-redistribution ; consumer decides).
      - ``note`` : informational only, surface to user as "context
        changed" without modifying probability."""

    description: str = Field(min_length=10, max_length=200)
    """Plain-French (or plain-English) one-sentence explanation of WHY
    this condition invalidates the bucket. Critic-verifiable. ADR-017
    boundary applies : never imperative, never a trade instruction —
    the description explains the macro/structural mechanism that links
    the metric breach to the bucket's contradicted thesis."""

    @field_validator("metric_name")
    @classmethod
    def _validate_metric_name_in_whitelist(cls, v: str) -> str:
        """Doctrine #4 SSOT : the LLM cannot fabricate a metric Ichor
        cannot measure. Enforce against the canonical
        ``INVALIDATION_METRIC_NAMES`` set at construction time."""
        if v not in INVALIDATION_METRIC_NAMES:
            raise ValueError(
                f"metric_name {v!r} is not in INVALIDATION_METRIC_NAMES "
                f"whitelist. Add it to the constant only if a collector "
                f"or service persists current values for it. Current "
                f"whitelist has {len(INVALIDATION_METRIC_NAMES)} entries."
            )
        return v

    @field_validator("description")
    @classmethod
    def _reject_trade_tokens_in_description(cls, v: str) -> str:
        """ADR-017 boundary mirror of ``Scenario._reject_trade_tokens``.
        The description explains the mechanism of invalidation ; never
        prescribes a trade action."""
        if _FORBIDDEN_MECHANISM_TOKENS_RE.search(v):
            raise ValueError(
                "ADR-017 boundary violated : InvalidationCondition.description "
                f"contains a forbidden trade-signal token. Got: {v!r}. The "
                "description explains the macro/structural mechanism that "
                "links the metric breach to the bucket's contradicted thesis ; "
                "it never prescribes BUY/SELL/TP/SL or entry/exit."
            )
        return v


class Scenario(BaseModel):
    """One bucket emission. ADR-017 compliant — describes probability +
    magnitude range, never a trade signal.

    r161 Strand A extension : ``invalidations`` field carries 0..5
    measurable conditions that, if breached, contradict this bucket's
    mechanism. Optional + default-empty preserves byte-compatibility
    with pre-r161 Pass-6 outputs (when the Pass-6 LLM prompt has not
    yet been updated to generate invalidations, the field stays
    ``[]`` and downstream consumers no-op cleanly).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    label: BucketLabel
    p: float = Field(ge=0.0, le=CAP_95)
    """Probability of this bucket realizing. Capped at 0.95 (ADR-022)."""

    magnitude_pips: tuple[float, float]
    """[low, high] realized-return range for this bucket in the asset's
    pip/point unit. Sourced from `scenario_calibration_bins` for the
    relevant (asset, session_type, rolling 252d). NOT a price target."""

    mechanism: str = Field(min_length=20, max_length=500)
    """One-paragraph plain-French explanation of what would trigger this
    bucket : event, narrative, technical level (referenced not prescribed).
    Critic-verifiable. ADR-017 forbids BUY/SELL/TP/SL tokens — enforced
    by `_reject_trade_tokens` validator below."""

    invalidations: list[InvalidationCondition] = Field(
        default_factory=list,
        max_length=5,
    )
    """r161 Strand A — list of 0..5 measurable conditions that contradict
    this bucket's mechanism if breached. Default empty preserves
    backward-compat with pre-r161 Pass-6 emissions ; once Strand C ships
    the updated Pass-6 system prompt, the LLM will populate this field
    per bucket. Consumed by ``services/scenario_invalidation_monitor.py``
    (Strand D) which polls each condition against current data and
    fires through ``alerts_runner.check_metric()`` (canonical Ichor
    alert pipeline) when a hard breach materialises.

    Cap at 5 invalidations per bucket prevents prompt-engineering
    saturation (the LLM tends to enumerate every adjacent risk if
    unbounded ; 5 is the trader-mindset reading capacity per the
    transcript framework + Pass-3 stress addendum doctrine)."""

    @field_validator("mechanism")
    @classmethod
    def _reject_trade_tokens(cls, v: str) -> str:
        """ADR-017 boundary : the mechanism explains WHY a bucket might
        realize, never WHAT to do. Reject any trade-signal token at
        construction time so the boundary is enforced regardless of
        whether the LLM cooperated with the prompt instruction."""
        if _FORBIDDEN_MECHANISM_TOKENS_RE.search(v):
            raise ValueError(
                "ADR-017 boundary violated : mechanism contains a forbidden "
                f"trade-signal token. Got: {v!r}. The mechanism explains the "
                "macro/structural reason a bucket might realize ; it never "
                "prescribes BUY/SELL/TP/SL or entry/exit."
            )
        return v

    @model_validator(mode="after")
    def _validate_magnitude_range(self) -> Scenario:
        low, high = self.magnitude_pips
        if low > high:
            raise ValueError(
                f"magnitude_pips low ({low}) must be ≤ high ({high}); bucket {self.label}"
            )
        return self


class ScenarioDecomposition(BaseModel):
    """The 7-bucket frozen list per (asset, session). Sum=1, cap-95
    enforced, unique labels enforced. CI-guarded ADR-081 W105f."""

    model_config = {"frozen": True, "extra": "forbid"}

    asset: str = Field(min_length=3, max_length=16)
    session_type: str = Field(min_length=5, max_length=16)
    scenarios: list[Scenario] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def _validate_buckets_unique_and_canonical(self) -> ScenarioDecomposition:
        labels = [s.label for s in self.scenarios]
        if len(set(labels)) != 7:
            raise ValueError(f"scenarios must have 7 unique labels, got {labels}")
        if set(labels) != set(BUCKET_LABELS):
            extras = set(labels) - set(BUCKET_LABELS)
            missing = set(BUCKET_LABELS) - set(labels)
            raise ValueError(
                f"scenarios labels must be exactly {set(BUCKET_LABELS)}; "
                f"extras={extras}, missing={missing}"
            )
        return self

    @model_validator(mode="after")
    def _validate_sum_to_one(self) -> ScenarioDecomposition:
        total = sum(s.p for s in self.scenarios)
        if abs(total - 1.0) > SUM_TOLERANCE:
            raise ValueError(
                f"scenarios probabilities must sum to 1.0 (±{SUM_TOLERANCE}); got {total:.9f}"
            )
        return self


def cap_and_normalize(probs: list[float], cap: float = CAP_95) -> list[float]:
    """Proportional clipping per [ADR-085 §"Probability cap + normalization"].

    If `max(probs) > cap`, clip the largest to `cap` and redistribute the
    excess proportionally over the remaining buckets (weighted by their
    current mass). Iterate until convergence. Preserves order, transparent,
    deterministic. Pure function — no I/O.

    Pre-conditions :
      - len(probs) >= 2
      - all(p >= 0)
      - sum(probs) > 0
      - 0 < cap < 1

    Post-conditions :
      - len(returned) == len(probs)
      - all(0 <= p <= cap)
      - abs(sum(returned) - sum(probs)) < 1e-9  (mass preserved)

    Rejected alternative : Dirichlet smoothing (Bayesian prior) — less
    transparent, requires hyperparameter α with no canonical institutional
    convention (per researcher 2026-05-11 web review).
    """
    if len(probs) < 2:
        raise ValueError("cap_and_normalize requires at least 2 probabilities")
    if not (0.0 < cap < 1.0):
        raise ValueError(f"cap must be in (0, 1), got {cap}")
    if any(p < 0.0 for p in probs):
        raise ValueError(f"probabilities must be non-negative, got {probs}")
    total = sum(probs)
    if total <= 0.0:
        raise ValueError(f"sum of probabilities must be positive, got {total}")

    out = list(probs)
    # Iterate (rare case where redistribution pushes another bucket over cap).
    # In practice converges in 1-2 iterations for typical Pass-6 emissions.
    max_iter = 32
    for _ in range(max_iter):
        m = max(out)
        if m <= cap + 1e-12:
            break
        i = out.index(m)
        excess = out[i] - cap
        out[i] = cap
        # Redistribute the excess proportionally on the other buckets.
        rest = sum(out) - cap
        if rest <= 0.0:
            # Edge case : all other buckets are 0 → can't redistribute
            # proportionally ; fall back to uniform across the n-1 others.
            n_others = len(out) - 1
            for j in range(len(out)):
                if j != i:
                    out[j] = excess / n_others
        else:
            for j in range(len(out)):
                if j != i:
                    out[j] += excess * out[j] / rest
    else:
        raise RuntimeError(
            f"cap_and_normalize failed to converge after {max_iter} iterations; "
            f"input={probs}, current={out}"
        )

    return out


def bucket_for_zscore(z: float) -> BucketLabel:
    """Map a realized-return z-score to its canonical bucket. Used by the
    realized-outcome reconciler (W105g) to compute `realized_scenario_bucket`
    from `polygon_intraday` returns. Boundaries match BUCKET_Z_THRESHOLDS.

    Boundaries are lower-inclusive, upper-exclusive ; the extremes are
    open-ended (z ≤ -2.5 = crash_flush, z >= +2.5 = melt_up).
    """
    if z <= BUCKET_Z_THRESHOLDS[0]:
        return "crash_flush"
    if z <= BUCKET_Z_THRESHOLDS[1]:
        return "strong_bear"
    if z <= BUCKET_Z_THRESHOLDS[2]:
        return "mild_bear"
    if z < BUCKET_Z_THRESHOLDS[3]:
        return "base"
    if z < BUCKET_Z_THRESHOLDS[4]:
        return "mild_bull"
    if z < BUCKET_Z_THRESHOLDS[5]:
        return "strong_bull"
    return "melt_up"


__all__ = [
    "BUCKET_LABELS",
    "BUCKET_Z_THRESHOLDS",
    "CAP_95",
    "SUM_TOLERANCE",
    "BucketLabel",
    "Scenario",
    "ScenarioDecomposition",
    "bucket_for_zscore",
    "cap_and_normalize",
]
