"""VIX_TERM_INVERSION alert wiring (Phase E innovation).

Detects **backwardation** in the VIX term structure — when the 1-month
implied volatility (VIXCLS) trades ABOVE the 3-month implied volatility
(VXVCLS). The ratio VIXCLS / VXVCLS > 1.0 signals near-term stress :

  - **Contango** (ratio < 1.0) : normal calm regime, longer-dated vol
    prices higher than near-term. Bull-market default.
  - **Neutral** (0.95 - 1.00) : transition zone.
  - **Backwardation** (ratio > 1.00) : near-term fear exceeds longer-
    term expectations. RARE — historically coincides with major stress
    episodes : 2008 GFC, 2011 US debt downgrade, 2015 China devaluation,
    Feb 2018 Volmageddon, late-2018 sell-off, March 2020 COVID, etc.
  - **Volatility shock** (ratio > 1.05) : steeply inverted, near-panic.

The ratio is a **contrarian signal** : empirical 2010-2017 analysis
(Macrosynergy, QuantSeeker) shows that inverted VIX curves have a
significant POSITIVE relation with subsequent S&P 500 returns — the
inversion marks panic/capitulation moments which are often
near-bottoms (April 2020 cleared back below 1.0, marking the durable
bottom).

For Ichor's pre-trade context engine, the alert flags :
  - Reduce dip-buying aggression (bear-market overnight gap risk
    elevated)
  - Increase intraday range expectations (higher volatility velocity)
  - Watch for the all-clear signal when ratio drops back below 1.0

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:VIXCLS+VXVCLS"
  - extra_payload includes vix_1m, vix_3m, ratio, regime tag

ROADMAP E (innovations). ADR-044.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

VIX_1M_SERIES = "VIXCLS"  # 30-day implied vol (VIX)
VIX_3M_SERIES = "VXVCLS"  # 90-day implied vol (VXV / VIX3M)

# Threshold mirrors catalog default (`VIX_TERM_INVERSION` AlertDef
# default_threshold=1.0). When ratio crosses 1.0, term structure is
# inverted = backwardation = near-term stress.
RATIO_INVERSION_FLOOR: float = 1.0

# Volatility-shock secondary threshold (informational only, exposed in
# the regime tag when applicable). Steeply inverted = near-panic.
RATIO_VOL_SHOCK_FLOOR: float = 1.05


@dataclass(frozen=True)
class VixTermResult:
    """One run summary."""

    vix_1m: float | None
    vix_3m: float | None
    ratio: float | None
    """VIXCLS / VXVCLS — > 1.0 means inverted (backwardation)."""

    observation_date: date | None
    regime: str
    """'backwardation_shock' (>= 1.05) | 'backwardation' (>= 1.00) |
    'neutral' (0.95-1.00) | 'contango' (< 0.95) | '' if degenerate."""

    alert_fired: bool
    note: str = ""


async def _fetch_latest(session: AsyncSession, *, series_id: str) -> tuple[date, float] | None:
    """Latest non-null observation for `series_id`. None if no rows."""
    cutoff = datetime.now(UTC).date() - timedelta(days=14)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    d, v = row
    return (d, float(v)) if v is not None else None


def _classify_regime(ratio: float | None) -> str:
    """Map ratio → regime tag per industry convention."""
    if ratio is None:
        return ""
    if ratio >= RATIO_VOL_SHOCK_FLOOR:
        return "backwardation_shock"
    if ratio >= RATIO_INVERSION_FLOOR:
        return "backwardation"
    if ratio >= 0.95:
        return "neutral"
    return "contango"


async def evaluate_vix_term_inversion(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> VixTermResult:
    """Compute VIX 1M / VIX 3M ratio, fire VIX_TERM_INVERSION when
    ratio > RATIO_INVERSION_FLOOR (backwardation).

    Returns a structured result so the CLI can print a one-liner.
    """
    row_1m = await _fetch_latest(session, series_id=VIX_1M_SERIES)
    row_3m = await _fetch_latest(session, series_id=VIX_3M_SERIES)

    if row_1m is None or row_3m is None:
        missing = []
        if row_1m is None:
            missing.append(VIX_1M_SERIES)
        if row_3m is None:
            missing.append(VIX_3M_SERIES)
        return VixTermResult(
            vix_1m=None,
            vix_3m=None,
            ratio=None,
            observation_date=None,
            regime="",
            alert_fired=False,
            note=(
                f"missing latest observations: {','.join(missing)} — "
                f"verify ichor-collector-fred_extended.timer is active"
            ),
        )

    d_1m, vix_1m = row_1m
    d_3m, vix_3m = row_3m
    if vix_3m == 0:
        # Defensive — shouldn't happen but VXVCLS = 0 would explode the ratio
        return VixTermResult(
            vix_1m=vix_1m,
            vix_3m=vix_3m,
            ratio=None,
            observation_date=d_1m,
            regime="",
            alert_fired=False,
            note=f"VXVCLS=0 on {d_3m.isoformat()} — degenerate, no ratio",
        )

    ratio = vix_1m / vix_3m
    regime = _classify_regime(ratio)
    # Use the more recent of the two dates as the alert observation date
    obs_date = max(d_1m, d_3m)

    note = (
        f"vix_term · 1M={vix_1m:.2f} on {d_1m.isoformat()} 3M={vix_3m:.2f} "
        f"on {d_3m.isoformat()} ratio={ratio:.4f} regime={regime}"
    )

    fired = False
    if ratio >= RATIO_INVERSION_FLOOR and persist:
        await check_metric(
            session,
            metric_name="vix_term_ratio",
            current_value=ratio,
            asset=None,  # macro-broad
            extra_payload={
                "vix_1m": vix_1m,
                "vix_3m": vix_3m,
                "ratio": ratio,
                "vix_1m_date": d_1m.isoformat(),
                "vix_3m_date": d_3m.isoformat(),
                "regime": regime,
                "is_vol_shock": ratio >= RATIO_VOL_SHOCK_FLOOR,
                "source": f"FRED:{VIX_1M_SERIES}+{VIX_3M_SERIES}",
            },
        )
        fired = True

    return VixTermResult(
        vix_1m=round(vix_1m, 4),
        vix_3m=round(vix_3m, 4),
        ratio=round(ratio, 4),
        observation_date=obs_date,
        regime=regime,
        alert_fired=fired,
        note=note,
    )
