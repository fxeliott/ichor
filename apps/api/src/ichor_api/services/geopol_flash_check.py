"""GEOPOL_FLASH alert wiring (Phase D.5.b).

The AI-GPR Index (Caldara & Iacoviello 2022 ; AI version SF Fed 2026)
is a daily measure of geopolitical risk built by scoring ~5M articles
from NYT/WaPo/Chicago Tribune (1960-present) with GPT-4o-mini.
Higher = more geopolitical tension. Spikes correlate with FX havens
(USD, CHF, JPY) bid + gold premium + carry-trade unwinds.

This bridge converts the daily AI-GPR into a tradable alert :

  - z-score of the latest AI-GPR reading against its trailing 30d
    distribution
  - |z| >= 2.0 ⇒ GEOPOL_FLASH alert fires

The 30d window is short on purpose : geopolitical regimes shift
quickly (week-scale, not year-scale), and the AI-GPR is itself a
high-frequency reading. A longer window would dampen the signal we
care about — *new* geopolitical pressure, not slow regime drift.

Why a separate 30d window from `delta_30d` in the collector :
  - The collector helper is a self-contained method on the
    AiGprObservation list (in-memory after fetch). This service
    reads from Postgres so the alert can run independently of
    collector freshness. Both paths converge on the same maths.

Source-stamping (ADR-017) :
  - extra_payload.source = "ai_gpr:caldara_iacoviello"
  - extra_payload includes current value, baseline mean/std,
    n_history, and a `havens_likely_to_move` list so the trader
    knows where the alert is most actionable (XAU, JPY, CHF, USD).

ROADMAP D.5.b. ADR-036.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GprObservation
from .alerts_runner import check_metric

# Window parameter. 30d trailing is the standard reference for AI-GPR
# (cf collector helper `delta_30d` and Caldara-Iacoviello 2022 §3.2).
ZSCORE_WINDOW_DAYS = 30

# Threshold mirrors the catalog default (`GEOPOL_FLASH` AlertDef
# default_threshold=2.0). Kept here for readability ; the real check
# is enforced by `check_metric` against the catalog row. Single
# source of truth via test_threshold_constant_matches_catalog.
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for a credible z-score on the 30d window. Below this
# we treat the signal as not-yet-warm (no alert, structured note).
_MIN_ZSCORE_HISTORY = 20

# Havens likely to react to a geopolitical risk spike (informational —
# included in extra_payload to help the trader pick where the signal
# actionable). Direction is regime-dependent (USD up vs. risk-off, but
# can flip on US-driven instability per ADR-037 dollar-smile switch).
_HAVENS_LIKELY: tuple[str, ...] = ("XAU_USD", "USD_JPY", "USD_CHF", "DXY")


@dataclass(frozen=True)
class GeopolFlashResult:
    """One run summary."""

    current_value: float | None
    """Latest AI-GPR reading (today or most recent in DB)."""

    current_date: date | None
    """Calendar date of the latest reading."""

    baseline_mean: float | None
    """Mean of the trailing 30d window (excluding the current point)."""

    baseline_std: float | None
    """Std of the trailing 30d window (excluding the current point)."""

    z_score: float | None
    """How many σ the latest reading sits from the rolling baseline."""

    n_history: int
    """How many observations were available for the z-score."""

    alert_fired: bool
    """True iff |z| >= ALERT_Z_ABS_FLOOR AND persist=True."""

    note: str = ""
    """Human-readable one-liner for the CLI."""

    havens_signaled: list[str] = field(default_factory=list)
    """Pass-through list of havens likely to react (informational)."""


async def _fetch_recent_observations(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[date, float]]:
    """Pull the last `days` AI-GPR observations from `gpr_observations`,
    oldest-first (so the *last* element is the most recent reading).

    Returns [] if no rows. The collector
    (`collectors/ai_gpr.py` → table `gpr_observations`) refreshes
    daily at 23h Paris (cf register-cron-collectors-extended.sh).
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
    rows.reverse()  # oldest-first
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


async def evaluate_geopol_flash(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> GeopolFlashResult:
    """Compute the AI-GPR z-score and fire `GEOPOL_FLASH` when |z| >= 2.0.

    Returns a structured result so the CLI can print a one-liner.
    """
    # Pull a small buffer beyond the 30d window so we have at least
    # 30 fully-observed days (weekend/holiday gaps in news indexes are
    # rare but possible).
    rows = await _fetch_recent_observations(
        session, days=ZSCORE_WINDOW_DAYS + 14
    )

    if not rows:
        return GeopolFlashResult(
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
        return GeopolFlashResult(
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
        f"baseline={mean:.2f}±{std:.2f} z={z:+.2f}"
    )

    fired = False
    if abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="ai_gpr_z",
            current_value=z,
            asset=None,  # macro-broad; havens signaled via extra_payload
            extra_payload={
                "ai_gpr_value": current_value,
                "ai_gpr_date": current_date.isoformat(),
                "baseline_mean": mean,
                "baseline_std": std,
                "n_history": len(history),
                "havens_likely_to_move": list(_HAVENS_LIKELY),
                "source": "ai_gpr:caldara_iacoviello",
            },
        )
        fired = True

    return GeopolFlashResult(
        current_value=round(current_value, 3),
        current_date=current_date,
        baseline_mean=round(mean, 3) if mean is not None else None,
        baseline_std=round(std, 3) if std is not None else None,
        z_score=round(z, 3),
        n_history=len(history),
        alert_fired=fired,
        note=note,
        havens_signaled=list(_HAVENS_LIKELY) if fired else [],
    )
