"""Brier score reconciliation for session cards.

Pure functions only — no DB, no I/O — so they're trivially testable.
The CLI in `cli/reconcile_outcomes.py` wires these into Postgres +
`polygon_intraday` to fill `realized_*` columns nightly.

Methodology
-----------
A session card emits a directional bias (long/short/neutral) with a
conviction in [0, 95]. We map this to a forecast probability that the
asset closes UP over the session window :

    P_up = 0.5 + 0.5 * (conviction/100)         if bias == long
           0.5 - 0.5 * (conviction/100)         if bias == short
           0.5                                  if bias == neutral

Outcome y ∈ {0, 1} : 1 if close > open over the timing window, else 0.

Brier score (single forecast) :   B = (P_up - y) ** 2  ∈ [0, 1]

Per Brier (1950) and Murphy (1973), B = 0 is perfect, B = 0.25 is
no-skill (50-50), B = 1 is anti-perfect. Reliability diagrams group
forecasts into probability buckets and plot bucket-mean(P) vs
bucket-mean(y). A perfectly calibrated model lies on the diagonal.

Magnitude is NOT scored here. Magnitude calibration is a separate
metric (continuous-ranked probability score / interval coverage) that
will land in `services/magnitude_calibration.py` once we have ≥ 30 days
of session cards × bars in DB.

References
----------
- Brier, G. W. (1950). *Verification of forecasts expressed in terms of
  probability*. Monthly Weather Review.
- Murphy, A. H. (1973). *A new vector partition of the probability
  score*. Journal of Applied Meteorology.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BiasDirection = Literal["long", "short", "neutral"]


def conviction_to_p_up(bias: BiasDirection, conviction_pct: float) -> float:
    """Map (bias, conviction%) → forecast probability that close > open.

    Conviction is clamped to [0, 95]. The mapping is symmetric around
    0.5 so a long/95 = 0.975 and a short/95 = 0.025. Neutral always
    returns 0.5 regardless of conviction (which the LLM should set
    near 0 anyway).
    """
    c = max(0.0, min(95.0, conviction_pct)) / 100.0
    if bias == "long":
        return 0.5 + 0.5 * c
    if bias == "short":
        return 0.5 - 0.5 * c
    return 0.5


def realized_direction(open_px: float, close_px: float) -> int:
    """Outcome y ∈ {0, 1}. 1 if close > open, else 0.

    Ties (extremely rare on a multi-bar window) resolve to 0 — i.e. a
    flat session is "not up", which is the convention used in most
    Brier-score literature for binary forecasts.
    """
    return 1 if close_px > open_px else 0


def brier_score(p_up: float, y: int) -> float:
    """Single-forecast Brier score. Range [0, 1], 0 is perfect."""
    if y not in (0, 1):
        raise ValueError(f"y must be 0 or 1, got {y!r}")
    if not (0.0 <= p_up <= 1.0):
        raise ValueError(f"p_up must be in [0, 1], got {p_up!r}")
    return (p_up - y) ** 2


def reconcile_card(
    *,
    bias_direction: BiasDirection,
    conviction_pct: float,
    open_px: float,
    close_px: float,
    high_px: float,
    low_px: float,
) -> ReconciliationOutcome:
    """End-to-end reconciliation of a single session card.

    Combines the helpers above into one record ready to be written
    back to `session_card_audit.realized_*` + `brier_contribution`.
    """
    p_up = conviction_to_p_up(bias_direction, conviction_pct)
    y = realized_direction(open_px, close_px)
    bs = brier_score(p_up, y)
    return ReconciliationOutcome(
        p_up=p_up,
        realized_outcome=y,
        brier_contribution=bs,
        realized_close_session=close_px,
        realized_high_session=high_px,
        realized_low_session=low_px,
    )


@dataclass(frozen=True)
class ReconciliationOutcome:
    """Output of `reconcile_card` — DB-shape, no business logic."""

    p_up: float
    realized_outcome: int
    brier_contribution: float
    realized_close_session: float
    realized_high_session: float
    realized_low_session: float


# ────────────────────────── Aggregate metrics ─────────────────────────


@dataclass(frozen=True)
class CalibrationSummary:
    """Aggregate Brier statistics over a window of cards."""

    n_cards: int
    mean_brier: float
    skill_vs_naive: float  # 1 - (mean_brier / 0.25), > 0 = beats coin flip
    hits: int  # cards where direction was correct
    misses: int


def summarize(brier_contributions: list[float], outcomes: list[int]) -> CalibrationSummary:
    """Aggregate Brier + skill score + hit/miss count.

    `outcomes` is the predicted-vs-realized match (1 if forecast went
    in the right direction, 0 otherwise). The Brier "naive" baseline is
    0.25 (always-50/50) — anything below that beats a coin.
    """
    if len(brier_contributions) != len(outcomes):
        raise ValueError("len(brier_contributions) must equal len(outcomes)")
    n = len(brier_contributions)
    if n == 0:
        return CalibrationSummary(0, 0.0, 0.0, 0, 0)
    mean_b = sum(brier_contributions) / n
    skill = 1.0 - (mean_b / 0.25)
    hits = sum(outcomes)
    return CalibrationSummary(
        n_cards=n,
        mean_brier=mean_b,
        skill_vs_naive=skill,
        hits=hits,
        misses=n - hits,
    )


def reliability_buckets(
    p_ups: list[float], ys: list[int], n_bins: int = 10
) -> list[ReliabilityBucket]:
    """Reliability diagram input — bins (P_up) vs mean(y) per bin.

    A well-calibrated model has `mean_p ≈ mean_y` per bucket.
    Returns buckets sorted by p ascending. Empty buckets are dropped.
    """
    if len(p_ups) != len(ys):
        raise ValueError("len(p_ups) must equal len(ys)")
    if n_bins < 2:
        raise ValueError("need at least 2 bins")
    edges = [i / n_bins for i in range(n_bins + 1)]
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, y in zip(p_ups, ys, strict=False):
        # right-inclusive edge so p=1.0 lands in the last bucket
        idx = min(n_bins - 1, max(0, int(p * n_bins)))
        buckets[idx].append((p, y))
    out: list[ReliabilityBucket] = []
    for i, items in enumerate(buckets):
        if not items:
            continue
        ps = [p for p, _ in items]
        ys_in = [y for _, y in items]
        out.append(
            ReliabilityBucket(
                bin_lower=edges[i],
                bin_upper=edges[i + 1],
                count=len(items),
                mean_predicted=sum(ps) / len(ps),
                mean_realized=sum(ys_in) / len(ys_in),
            )
        )
    return out


@dataclass(frozen=True)
class ReliabilityBucket:
    """One bin of a reliability diagram."""

    bin_lower: float
    bin_upper: float
    count: int
    mean_predicted: float
    mean_realized: float
