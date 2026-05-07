"""DOLLAR_SMILE_BREAK alert wiring (Phase E.3).

Detects the **"broken smile" / "US-driven instability" regime** —
the case Stephen Jen's classic Dollar Smile framework (2001) doesn't
handle, but which dominated 2025-2026.

The classic Dollar Smile (Eurizon SLJ Capital) :

    USD strong on global fear        ← left side
    USD weak on moderate US growth     middle
    USD strong on US outperformance  → right side

The broken smile (Wellington / Stephen Jen 2025-2026 warnings) :

    Term premium expanding + DXY weakening
    + VIX not panicking + HY OAS not blowing out
    = US itself becomes source of instability
    = safe-haven bid evaporates
    = $26T unhedged foreign-held assets create exit loop

This is the regime that emerged in April 2025 when USD fell WITH stocks
during tariff panic. Per Stephen Jen Bloomberg 2025-11-12 : USD could
fall ~13.5% during Trump second term ; left side of smile threatened
by fiscal imprudence + Fed independence questions.

Detection logic (4-condition composite AND gate) :

  1. term_premium_z > +2.0 (TERM_PREMIUM_REPRICING-style expansion)
  2. dxy_z < -1.0 (USD weakening)
  3. vix_z < +1.0 (not panic — distinguishes from classic left-side smile)
  4. hy_oas_z < +1.0 (no systemic credit stress — distinguishes from
     funding-stress regime)

When ALL 4 conditions align, fire DOLLAR_SMILE_BREAK. The gate is
deliberately a logical AND because each condition by itself is
ambiguous — only the simultaneous alignment is informative.

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:THREEFYTP10+DTWEXBGS+VIXCLS+BAMLH0A0HYM2"
  - extra_payload includes all 4 z-scores + per-condition pass/fail

ROADMAP E.3. ADR-043.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# 4 input series for the composite gate.
TERM_PREMIUM_SERIES = "THREEFYTP10"  # KW 10y term premium
DXY_SERIES = "DTWEXBGS"              # Trade-weighted USD broad
VIX_SERIES = "VIXCLS"                # CBOE Volatility Index
HY_OAS_SERIES = "BAMLH0A0HYM2"       # ICE BofA HY Option-Adjusted Spread

# Per-condition thresholds.
TERM_PREMIUM_EXPANSION_FLOOR: float = 2.0   # term_premium_z > this
DXY_WEAKNESS_CEILING: float = -1.0          # dxy_z < this
VIX_NOT_PANIC_CEILING: float = 1.0          # vix_z < this (not panic)
HY_OAS_NOT_STRESS_CEILING: float = 1.0      # hy_oas_z < this (not systemic)

# Composite alert threshold. 4 of 4 conditions must align for the
# regime to be unambiguous. Anything less is interpretable as classic
# smile or noise.
ALERT_CONDITIONS_FLOOR: int = 4

# Window parameter.
ZSCORE_WINDOW_DAYS = 90

# Minimum sample for credible per-dim z-score.
_MIN_ZSCORE_HISTORY = 60


@dataclass(frozen=True)
class ConditionState:
    """One condition of the composite gate."""

    name: str
    z_score: float | None
    threshold: float
    operator: str  # ">" or "<"
    passes: bool


@dataclass(frozen=True)
class DollarSmileResult:
    """One run summary."""

    n_conditions_passing: int
    """Count of the 4 conditions that hold (term-premium-expansion +
    dxy-weakness + vix-not-panic + hy-oas-not-stress)."""

    alert_fired: bool

    conditions: list[ConditionState] = field(default_factory=list)

    note: str = ""

    smile_regime: str = ""
    """'us_driven_instability' if all 4 conditions pass, '' otherwise.
    A future v2 could also detect classic 'left' / 'middle' / 'right'
    smile regimes."""


async def _fetch_history(
    session: AsyncSession,
    *,
    series_id: str,
    days: int,
) -> list[float]:
    """Pull last `days` observations for a FRED series, oldest-first."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [float(r[1]) for r in rows if r[1] is not None]


def _zscore(history: list[float], current: float) -> float | None:
    """Compute z-score with min-history + zero-std defenses."""
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None
    return (current - mean) / std


async def _compute_zscore_for_series(
    session: AsyncSession, series_id: str
) -> float | None:
    """Fetch + compute the z-score for one FRED series. None on degenerate."""
    history_full = await _fetch_history(
        session, series_id=series_id, days=ZSCORE_WINDOW_DAYS + 14
    )
    if not history_full:
        return None
    current = history_full[-1]
    history = history_full[:-1][-ZSCORE_WINDOW_DAYS:]
    return _zscore(history, current)


def _evaluate_condition(
    name: str,
    z: float | None,
    threshold: float,
    operator: str,
) -> ConditionState:
    """One condition of the gate. operator must be '>' or '<'."""
    if z is None:
        return ConditionState(
            name=name,
            z_score=None,
            threshold=threshold,
            operator=operator,
            passes=False,
        )
    passes = (z > threshold) if operator == ">" else (z < threshold)
    return ConditionState(
        name=name,
        z_score=round(z, 3),
        threshold=threshold,
        operator=operator,
        passes=passes,
    )


async def evaluate_dollar_smile_break(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> DollarSmileResult:
    """Compute z-scores for the 4 input series, evaluate the 4 conditions,
    fire DOLLAR_SMILE_BREAK when all 4 hold simultaneously.

    Returns a structured result so the CLI can print a one-liner.
    """
    z_term_premium = await _compute_zscore_for_series(session, TERM_PREMIUM_SERIES)
    z_dxy = await _compute_zscore_for_series(session, DXY_SERIES)
    z_vix = await _compute_zscore_for_series(session, VIX_SERIES)
    z_hy_oas = await _compute_zscore_for_series(session, HY_OAS_SERIES)

    conditions = [
        _evaluate_condition(
            "term_premium_expansion",
            z_term_premium,
            TERM_PREMIUM_EXPANSION_FLOOR,
            ">",
        ),
        _evaluate_condition(
            "dxy_weakness",
            z_dxy,
            DXY_WEAKNESS_CEILING,
            "<",
        ),
        _evaluate_condition(
            "vix_not_panic",
            z_vix,
            VIX_NOT_PANIC_CEILING,
            "<",
        ),
        _evaluate_condition(
            "hy_oas_not_stress",
            z_hy_oas,
            HY_OAS_NOT_STRESS_CEILING,
            "<",
        ),
    ]
    n_passing = sum(1 for c in conditions if c.passes)

    smile_regime = "us_driven_instability" if n_passing == ALERT_CONDITIONS_FLOOR else ""

    breakdown = " ".join(
        f"{c.name}={'PASS' if c.passes else 'fail'}({c.z_score})" for c in conditions
    )
    note = (
        f"dollar_smile · {n_passing}/4 conditions met "
        f"(regime={smile_regime or 'classic_or_noise'}) | {breakdown}"
    )

    fired = False
    if n_passing >= ALERT_CONDITIONS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="dollar_smile_conditions_met",
            current_value=float(n_passing),
            asset=None,  # macro-broad
            extra_payload={
                "smile_regime": smile_regime,
                "n_conditions_passing": n_passing,
                "z_term_premium": z_term_premium,
                "z_dxy": z_dxy,
                "z_vix": z_vix,
                "z_hy_oas": z_hy_oas,
                "conditions": [
                    {
                        "name": c.name,
                        "z_score": c.z_score,
                        "threshold": c.threshold,
                        "operator": c.operator,
                        "passes": c.passes,
                    }
                    for c in conditions
                ],
                "source": (
                    f"FRED:{TERM_PREMIUM_SERIES}+{DXY_SERIES}+"
                    f"{VIX_SERIES}+{HY_OAS_SERIES}"
                ),
            },
        )
        fired = True

    return DollarSmileResult(
        n_conditions_passing=n_passing,
        alert_fired=fired,
        conditions=conditions,
        note=note,
        smile_regime=smile_regime,
    )
