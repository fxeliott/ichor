"""TERM_PREMIUM_STRUCTURAL_252D alert wiring (Phase E.2 structural companion).

Sister long-window companion to TERM_PREMIUM_REPRICING (ADR-041, 90d).
Where TERM_PREMIUM_REPRICING catches *acute* term premium repricing
events (auction tail, debt-ceiling dramas, FOMC surprises), this
companion catches *structural* fiscal regime shifts on a 252d
(1 trading year) window.

Pattern aligned with GEOPOL_FLASH (30d) + GEOPOL_REGIME_STRUCTURAL
(252d) sister-pair (ADR-039) :

| Alert | Window | Severity | Cadence | Use |
|---|---|---|---|---|
| TERM_PREMIUM_REPRICING | 90d | warning | daily 22:30 | Acute repricing event |
| TERM_PREMIUM_STRUCTURAL_252D | 252d | info | weekly Sun 22:00 | Structural fiscal regime |

Why both windows are needed :

  - **Slow-build fiscal escalations** (Trump fiscal expansion arc 2025-2027,
    Treasury supply-demand multi-year imbalance, sovereign debt repricing
    cycle) get *dampened* in a 90d window because the rolling baseline
    drifts up with the absolute level. The relative z-score shrinks even
    though the absolute term premium is structurally elevated. Per Hartford
    / SSGA / NY Life 2026 outlooks : term premium expansion is THE 2026
    story but it unfolds over 12-24 months.
  - **Acute repricing events** (single-day auction tail, debt-ceiling
    drama, FOMC press surprise) need 90d-window reactivity (sister alert).

The 252d trailing-year window catches a regime shift "from one fiscal era
to another" — exactly the situation 2026 macro is in (post-COVID fiscal
impulse + Trump 2.0 expansion + Fed independence questions).

Severity is `info` (not `warning`) because structural shifts unfold over
weeks-months — the alert is a *context flag* not an actionable signal. The
warning-level TERM_PREMIUM_REPRICING remains the trader-actionable pathway.

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:THREEFYTP10"
  - extra_payload includes window=252, baseline_mean, baseline_std,
    n_history, regime tag — same shape as TERM_PREMIUM_REPRICING for
    consistency and audit-replay simplicity.

Cron : weekly Sunday 22:15 Paris (slow-build, no need for daily evaluation
of a 252d-window signal — single drift detection per week is plenty).

ROADMAP E.2 structural companion. ADR-045.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# Same FRED series as TERM_PREMIUM_REPRICING — KW 10y term premium.
TERM_PREMIUM_SERIES_ID = "THREEFYTP10"

# Window parameter. 252 = 1 trading year (financial econometrics standard
# for "annual" rolling window). Captures structural shifts spanning
# ~6-12 months that the 90d window misses.
ZSCORE_WINDOW_DAYS = 252

# Threshold mirrors catalog default. Single source of truth via
# test_threshold_constant_matches_catalog.
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for credible z-score on the 252d window. Below this
# (e.g. fresh data warmup), the alert silently no-ops with structured
# note pointing at the collector freshness.
_MIN_ZSCORE_HISTORY = 180


@dataclass(frozen=True)
class TermPremiumStructuralResult:
    """One run summary."""

    current_value_pct: float | None
    """Latest term premium reading in % (FRED units)."""

    current_date: date | None

    baseline_mean: float | None
    """Mean of the trailing 252d window (excluding current point)."""

    baseline_std: float | None

    z_score: float | None

    n_history: int

    alert_fired: bool

    regime: str = ""
    """'expansion_structural' if z > 0, 'contraction_structural' if z < 0,
    '' if N/A."""

    note: str = ""

    assets_likely_to_move: list[str] = field(default_factory=list)


def _classify_regime(z: float | None) -> str:
    """Map z-score to regime tag."""
    if z is None:
        return ""
    return "expansion_structural" if z > 0 else "contraction_structural"


def _assets_for_regime(regime: str) -> list[str]:
    """Same per-regime asset list as TERM_PREMIUM_REPRICING for
    consistency. The structural variant catches longer-cycle moves but
    the trader-actionable assets are the same."""
    if regime == "expansion_structural":
        return ["XAU_USD", "DXY", "DGS10", "MORTGAGE", "EUR_USD", "USD_JPY"]
    if regime == "contraction_structural":
        return ["DGS10", "DXY", "USD_JPY", "BAMLH0A0HYM2"]
    return []


async def _fetch_recent_observations(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[date, float]]:
    """Pull last `days` THREEFYTP10 observations, oldest-first.

    Same helper shape as `term_premium_check._fetch_recent_observations`
    — kept duplicated for evolution independence (the structural alert
    can diverge from the acute alert in v2 without coupling).
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == TERM_PREMIUM_SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [(r[0], float(r[1])) for r in rows if r[1] is not None]


def _zscore(
    history: list[float],
    current: float,
) -> tuple[float | None, float | None, float | None]:
    """(z, mean, std) of `current` against `history`. None on degenerate input."""
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None, None, None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None, mean, std
    return (current - mean) / std, mean, std


async def evaluate_term_premium_structural(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> TermPremiumStructuralResult:
    """Compute 252d AI-GPR z-score and fire `TERM_PREMIUM_STRUCTURAL_252D`
    when |z| >= ALERT_Z_ABS_FLOOR.

    Returns a structured result so the CLI can print a one-liner.
    """
    rows = await _fetch_recent_observations(session, days=ZSCORE_WINDOW_DAYS + 21)

    if not rows:
        return TermPremiumStructuralResult(
            current_value_pct=None,
            current_date=None,
            baseline_mean=None,
            baseline_std=None,
            z_score=None,
            n_history=0,
            alert_fired=False,
            note=(
                "no THREEFYTP10 observations in DB — verify "
                "ichor-collector-fred_extended.timer is active and "
                "THREEFYTP10 is in EXTENDED_SERIES_TO_POLL"
            ),
        )

    current_date, current_value = rows[-1]
    history = [v for _d, v in rows[:-1]][-ZSCORE_WINDOW_DAYS:]
    z, mean, std = _zscore(history, current_value)

    if z is None:
        note = (
            f"term_premium_structural · {current_value:+.4f}% on "
            f"{current_date.isoformat()} (insufficient history: "
            f"{len(history)}d, need >= {_MIN_ZSCORE_HISTORY})"
        )
        return TermPremiumStructuralResult(
            current_value_pct=current_value,
            current_date=current_date,
            baseline_mean=mean,
            baseline_std=std,
            z_score=None,
            n_history=len(history),
            alert_fired=False,
            note=note,
        )

    regime = _classify_regime(z)
    note = (
        f"term_premium_structural · {current_value:+.4f}% on "
        f"{current_date.isoformat()} baseline_252d={mean:+.4f}±{std:.4f} "
        f"z={z:+.2f} ({regime})"
    )

    fired = False
    assets = []
    if abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        assets = _assets_for_regime(regime)
        await check_metric(
            session,
            metric_name="term_premium_z_252d",
            current_value=z,
            asset=None,  # macro-broad
            extra_payload={
                "term_premium_pct": current_value,
                "term_premium_bps": current_value * 100,
                "term_premium_date": current_date.isoformat(),
                "baseline_mean": mean,
                "baseline_std": std,
                "n_history": len(history),
                "window_days": ZSCORE_WINDOW_DAYS,
                "regime": regime,
                "assets_likely_to_move": assets,
                "source": f"FRED:{TERM_PREMIUM_SERIES_ID}",
            },
        )
        fired = True

    return TermPremiumStructuralResult(
        current_value_pct=round(current_value, 4),
        current_date=current_date,
        baseline_mean=round(mean, 4) if mean is not None else None,
        baseline_std=round(std, 4) if std is not None else None,
        z_score=round(z, 3),
        n_history=len(history),
        alert_fired=fired,
        regime=regime,
        note=note,
        assets_likely_to_move=assets,
    )
