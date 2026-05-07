"""TERM_PREMIUM_REPRICING alert wiring (Phase E.2).

The 10-year Treasury term premium decomposes the long-end yield into :

    DGS10 = expected_path_short_rates + term_premium_10y

where term_premium_10y is the additional yield investors demand for
holding duration risk over rolling shorter-term Treasuries. The
Kim-Wright (KW, FRED THREEFYTP10) and Adrian-Crump-Moench (ACM, NY Fed)
models both estimate this latent variable from yield curve dynamics
and surveys.

When the term premium re-prices materially (>2σ vs trailing 90d
distribution), the long end disconnects from front-end policy
expectations. This is the Bond Vigilante regime — fiscal-stress
narrative, debt sustainability questions, supply-demand imbalance at
auctions, foreign reserve diversification, dollar-debasement worries.

2026 macro context (per Forex.com / Hartford / NY Life / SSGA outlooks) :

  - Fed cuts front-end rates while term premium WIDENS due to fiscal
    stress + Trump-administration fiscal expansion + Fed independence
    questions
  - Long-end repricing > short-end → mortgage rates stay elevated
    despite Fed cuts (a key macro housing inflation impact)
  - Gold rally support : term premium expansion = USD-debasement narrative
  - DXY pressure : foreign holders demand higher term premium → bonds
    sell off → USD weakens (paradoxically, despite higher US yields)

This alert flags the moment of repricing, not the level. A +2σ
expansion against a 90d baseline catches narrative shifts (fiscal-
cliff fears, auction tail surprises, debt-ceiling drama) ; a -2σ
contraction catches the reverse (flight-to-Treasuries safe-haven bid).

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:THREEFYTP10" (Kim-Wright model)
  - extra_payload includes current_value (in bps), baseline_mean,
    baseline_std, n_history, plus regime_signaled tag (expansion vs
    contraction).

ROADMAP E.2. ADR-041.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# FRED series id for the 10-year term premium (Kim-Wright model).
# The strict ACM series is hosted on NY Fed's website only ; per
# Federal Reserve note 2017-04-03, KW and ACM agree within bps once
# survey-rate-expectations are matched. We use KW for free + FRED-hosted.
TERM_PREMIUM_SERIES_ID = "THREEFYTP10"

# Window parameters. 90d trailing window catches narrative-shift episodes
# (fiscal-cliff, auction tails, debt-ceiling). A 252d structural variant
# could be added in v2 (similar to GEOPOL_FLASH 30d + GEOPOL_REGIME 252d
# pair).
ZSCORE_WINDOW_DAYS = 90

# Threshold mirrors the catalog default (`TERM_PREMIUM_REPRICING`
# AlertDef default_threshold=2.0). Single source of truth via test
# test_threshold_constant_matches_catalog.
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for a credible z-score. Below this (e.g. fresh data
# warmup), the alert silently no-ops with structured note.
_MIN_ZSCORE_HISTORY = 60


@dataclass(frozen=True)
class TermPremiumResult:
    """One run summary."""

    current_value_pct: float | None
    """Latest term premium reading in %. NB: FRED reports in % (e.g. 0.45
    means 45 bps), not in bps directly. Multiply by 100 for bps display."""

    current_date: date | None

    baseline_mean: float | None
    """Mean of trailing 90d window (excluding current point)."""

    baseline_std: float | None

    z_score: float | None
    """How many σ the latest reading sits from the rolling baseline."""

    n_history: int

    alert_fired: bool

    regime: str = ""
    """'expansion' if z > 0, 'contraction' if z < 0, '' if N/A."""

    note: str = ""

    assets_likely_to_move: list[str] = field(default_factory=list)


def _classify_regime(z: float | None) -> str:
    """expansion = term premium widening (bond sell-off, fiscal stress).
    contraction = term premium narrowing (flight-to-quality, deflation fear)."""
    if z is None:
        return ""
    return "expansion" if z > 0 else "contraction"


def _assets_for_regime(regime: str) -> list[str]:
    """Map regime to assets most affected. Informational — surfaced to
    extra_payload + result for trader drill-down. Direction is regime-
    dependent (expansion = USD weak / gold up / mortgage rates up ;
    contraction = USD strong / gold ambiguous / safe-haven bid)."""
    if regime == "expansion":
        return ["XAU_USD", "DXY", "DGS10", "MORTGAGE", "EUR_USD", "USD_JPY"]
    if regime == "contraction":
        return ["DGS10", "DXY", "USD_JPY", "BAMLH0A0HYM2"]
    return []


async def _fetch_recent_observations(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[date, float]]:
    """Pull last `days` THREEFYTP10 observations from `fred_observations`,
    oldest-first (last element = most recent reading). The collector
    `fred_extended.py` polls THREEFYTP10 daily as part of EXTENDED_SERIES_TO_POLL
    (added in PR #35)."""
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


async def evaluate_term_premium_repricing(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> TermPremiumResult:
    """Compute term premium z-score over trailing 90d, fire
    TERM_PREMIUM_REPRICING when |z| >= ALERT_Z_ABS_FLOOR.

    Returns a structured result so the CLI can print a one-liner.
    """
    rows = await _fetch_recent_observations(
        session, days=ZSCORE_WINDOW_DAYS + 14
    )

    if not rows:
        return TermPremiumResult(
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
            f"term_premium={current_value:+.4f}% on {current_date.isoformat()} "
            f"(insufficient history: {len(history)}d, need >= {_MIN_ZSCORE_HISTORY})"
        )
        return TermPremiumResult(
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
        f"term_premium={current_value:+.4f}% on {current_date.isoformat()} "
        f"baseline_90d={mean:+.4f}±{std:.4f} z={z:+.2f} ({regime})"
    )

    fired = False
    assets = []
    if abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        assets = _assets_for_regime(regime)
        await check_metric(
            session,
            metric_name="term_premium_z",
            current_value=z,
            asset=None,  # macro-broad
            extra_payload={
                "term_premium_pct": current_value,
                "term_premium_bps": current_value * 100,
                "term_premium_date": current_date.isoformat(),
                "baseline_mean": mean,
                "baseline_std": std,
                "n_history": len(history),
                "regime": regime,
                "assets_likely_to_move": assets,
                "source": f"FRED:{TERM_PREMIUM_SERIES_ID}",
            },
        )
        fired = True

    return TermPremiumResult(
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
