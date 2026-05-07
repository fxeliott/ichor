"""GEOPOL_REGIME_STRUCTURAL alert wiring (Phase D.5.b structural companion).

Sister alert to GEOPOL_FLASH (ADR-036). Where GEOPOL_FLASH catches
*acute* spikes in AI-GPR (30d window), this companion catches
*structural* regime shifts on a 252d (1 trading year) window.

Why both windows are needed :

  - **Slow-build escalations** (Russia-Ukraine cumulative ~3y trajectory,
    Taiwan-strait gradual militarization, US-China decoupling on a
    multi-year arc) get *dampened* in a 30d window because the rolling
    baseline drifts up with the absolute risk level. The relative z-score
    shrinks even though the absolute risk is high. Per WEF Global Risks
    Report 2026 §2 : *"Geopolitical cycles are long — historically, they
    last between 80 and 100 years. Structural changes like those we're
    witnessing now only come around once per century and tend to be
    disruptive."*
  - **Acute shocks** (single-day USTR press release, Trump tweet, Iran
    strike) need 30d-window reactivity (GEOPOL_FLASH).

The 252d trailing-year window catches a regime shift "from one risk era
to another" — exactly the situation 2026 macro is in (post-SCOTUS IEEPA
invalidation, US-Venezuela operations, Section 301 wave, Taiwan drills).

Severity is `info` (not `warning`) because structural shifts unfold over
weeks — the alert is a *context flag* not an actionable signal. The
warning-level GEOPOL_FLASH remains the trader-actionable pathway.

Source-stamping (ADR-017) :
  - extra_payload.source = "ai_gpr:caldara_iacoviello"
  - extra_payload includes window=252, baseline_mean, baseline_std,
    n_history, current_value — same shape as GEOPOL_FLASH for consistency
    and audit-replay simplicity.

Cron : weekly Sunday 22h Paris (slow-build, no need for daily evaluation
of a 252d-window signal — a single drift detection per week is plenty).

ROADMAP D.5.b (structural companion). ADR-039.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GprObservation
from .alerts_runner import check_metric

# Window parameter. 252 = 1 trading year (standard convention in
# financial econometrics for "annual" rolling window). Captures
# structural shifts spanning ~6-12 months that the 30d GEOPOL_FLASH
# misses.
ZSCORE_WINDOW_DAYS = 252

# Threshold mirrors the catalog default (`GEOPOL_REGIME_STRUCTURAL`
# AlertDef default_threshold=2.0). Single source of truth via test
# test_threshold_constant_matches_catalog.
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for a credible z-score on the 252d window. Below this
# (e.g. fresh data warmup), the alert silently no-ops with a structured
# note pointing at the collector freshness.
_MIN_ZSCORE_HISTORY = 180

# Major structural-regime tags — informational, surfaced in extra_payload
# so the trader knows the alert family at a glance. Direction up = "risk
# era heightening", direction down = "de-escalation regime".
_REGIMES_LIKELY: tuple[str, ...] = (
    "Russia-Ukraine cumulative escalation",
    "Taiwan-strait militarization",
    "US-China decoupling arc",
    "MENA conflict cluster",
)


@dataclass(frozen=True)
class GeopolRegimeResult:
    """One run summary."""

    current_value: float | None
    """Latest AI-GPR reading."""

    current_date: date | None

    baseline_mean: float | None
    """Mean of the trailing 252d window (excluding the current point)."""

    baseline_std: float | None

    z_score: float | None
    """How many σ the latest reading sits from the year-trailing baseline."""

    n_history: int

    alert_fired: bool

    note: str = ""

    regimes_signaled: list[str] = field(default_factory=list)


async def _fetch_recent_observations(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[date, float]]:
    """Pull the last `days` AI-GPR observations from `gpr_observations`,
    oldest-first (last element = most recent reading). Same helper shape
    as `geopol_flash_check._fetch_recent_observations` — kept duplicated
    rather than imported so the structural alert can evolve independently
    if window/source semantics diverge in v2.
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(GprObservation.observation_date, GprObservation.ai_gpr)
        .where(
            GprObservation.observation_date >= cutoff,
            GprObservation.ai_gpr.is_not(None),
        )
        .order_by(desc(GprObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [(r[0], float(r[1])) for r in rows if r[1] is not None]


def _zscore(
    history: list[float],
    current: float,
) -> tuple[float | None, float | None, float | None]:
    """(z, mean, std) of `current` against `history`. None on degenerate input.

    Note : history should EXCLUDE the current point so the baseline is
    not biased by it. The caller guarantees this invariant.
    """
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None, None, None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None, mean, std
    return (current - mean) / std, mean, std


async def evaluate_geopol_regime_structural(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> GeopolRegimeResult:
    """Compute the 252d AI-GPR z-score and fire `GEOPOL_REGIME_STRUCTURAL`
    when |z| >= ALERT_Z_ABS_FLOOR.

    Returns a structured result so the CLI can print a one-liner.
    """
    # Pull buffer beyond 252d window for variance-resilient z-score
    rows = await _fetch_recent_observations(
        session, days=ZSCORE_WINDOW_DAYS + 21
    )

    if not rows:
        return GeopolRegimeResult(
            current_value=None,
            current_date=None,
            baseline_mean=None,
            baseline_std=None,
            z_score=None,
            n_history=0,
            alert_fired=False,
            note=(
                "no AI-GPR observations in DB — verify collector "
                "ichor-collector-ai_gpr.timer is active"
            ),
        )

    current_date, current_value = rows[-1]
    history = [v for _d, v in rows[:-1]][-ZSCORE_WINDOW_DAYS:]

    z, mean, std = _zscore(history, current_value)

    if z is None:
        note = (
            f"ai_gpr={current_value:.2f} on {current_date.isoformat()} "
            f"(insufficient history: {len(history)}d, need >= {_MIN_ZSCORE_HISTORY})"
        )
        return GeopolRegimeResult(
            current_value=current_value,
            current_date=current_date,
            baseline_mean=mean,
            baseline_std=std,
            z_score=None,
            n_history=len(history),
            alert_fired=False,
            note=note,
        )

    note = (
        f"ai_gpr={current_value:.2f} on {current_date.isoformat()} "
        f"baseline_252d={mean:.2f}±{std:.2f} z={z:+.2f}"
    )

    fired = False
    if abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="ai_gpr_z_252d",
            current_value=z,
            asset=None,
            extra_payload={
                "ai_gpr_value": current_value,
                "ai_gpr_date": current_date.isoformat(),
                "baseline_mean": mean,
                "baseline_std": std,
                "n_history": len(history),
                "window_days": ZSCORE_WINDOW_DAYS,
                "regimes_signaled": list(_REGIMES_LIKELY),
                "source": "ai_gpr:caldara_iacoviello",
            },
        )
        fired = True

    return GeopolRegimeResult(
        current_value=round(current_value, 3),
        current_date=current_date,
        baseline_mean=round(mean, 3) if mean is not None else None,
        baseline_std=round(std, 3) if std is not None else None,
        z_score=round(z, 3),
        n_history=len(history),
        alert_fired=fired,
        note=note,
        regimes_signaled=list(_REGIMES_LIKELY) if fired else [],
    )
