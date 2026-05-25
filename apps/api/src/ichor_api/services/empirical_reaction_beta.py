"""empirical_reaction_betas read-fn — Engine 8 axis-4 +1 LEVEL DEPTH r160.

Read-only service contract over the `empirical_reaction_betas` table
(migration 0053, ORM `EmpiricalReactionBeta`). Engine 8 calls
`get_latest_empirical_beta(...)` BEFORE falling back to the
literature_prior `EVENT_CLASS_BASELINE_BP` dict — when a row exists for
the queried (event_class, instrument), Engine 8 uses the row's
`p50_drift_bp` instead of the literature prior.

**Contract** :

  - Pure read-fn ; one DB round-trip ; no INSERT/UPDATE ever from this
    module. Backfill writes belong to the r161+ Dukascopy fetcher
    service (separate module, sanctioned write path).
  - Returns `EmpiricalReactionBetaSnapshot | None`. None means "no row
    matches the queried key — caller MUST fall back to literature prior
    cleanly without raising".
  - Latest per (event_class, instrument) selection uses the compound
    index `ix_empirical_reaction_betas_class_instrument_computed_at_desc`
    via `ORDER BY computed_at DESC LIMIT 1` — picks the most recent
    backfill recompute. Methodology stamps (window_minutes_before /
    after) are returned to the caller for caveat-surfacing but do NOT
    participate in row selection — r160 is single-methodology
    (ABDV-2003 5min pre / 0min post canonical default). r170+ multi-
    methodology selection logic will plug in here via an optional
    `prefer_methodology` kwarg without breaking the r160 default.

**Asset ↔ instrument mapping** :

The Engine 8 caller has an OANDA-style asset code (e.g., "EUR_USD",
"XAU_USD", "SPX500_USD") ; the empirical-beta table stores a
Dukascopy URL-slug instrument (e.g., "eurusd", "xauusd",
"usa500idxusd"). `asset_to_instrument()` is the pure mapping. The 5
ADR-083 D1 priority assets are explicit ; r170+ adds USD_CAD when
the 6th `/briefing/[asset]` route ships (ROADMAP §1 carry-forward).

**Doctrine-#2 strict scope post-r160 binding-default** : the table
starts EMPTY. Engine 8 graceful-degradation path means r160 ships
ZERO behavior change vs r159 output (every read returns None ;
caller falls back to literature_prior 100%). The path lights up
naturally as r161+ Dukascopy fetcher populates rows.

ADR refs : ADR-099 §Impl(r160) — Mission centrale Axis-4 +1 LEVEL
DEPTH foundation ; Pattern #17 formal DOCTRINE r159 graduates here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EmpiricalReactionBeta

__all__ = [
    "ASSET_TO_INSTRUMENT",
    "EmpiricalReactionBetaSnapshot",
    "asset_to_instrument",
    "get_latest_empirical_beta",
]


# ── Asset ↔ Dukascopy instrument slug mapping ──
#
# The 5 ADR-083 D1 priority assets that ship with `/briefing/[asset]`
# routes today (ROADMAP §1 universe minus USD_CAD which has no route
# wired yet). Each value is the Dukascopy URL-slug used directly in
# the `datafeed.dukascopy.com/datafeed/{INSTRUMENT}/...` bi5 URL.
#
# Slugs verified r160 against Dukascopy historical-feed URL list :
#   - eurusd       — EUR/USD (forex)
#   - gbpusd       — GBP/USD (forex)
#   - xauusd       — XAU/USD (forex precious-metal)
#   - usa500idxusd — S&P 500 cash index (Dukascopy CFD slug)
#   - usatechidxusd — Nasdaq 100 cash index (Dukascopy CFD slug)
#
# USD_CAD will join when ROADMAP §1 6th route lands (instrument =
# "usdcad"). New assets MUST be added here AND empirically verified
# against the live Dukascopy URL pattern before being shipped (r161+
# fetcher will fail-loud on a 404 if the slug is wrong, but doctrine
# #11 calibrated honesty prefers source-checked over fail-loud).
ASSET_TO_INSTRUMENT: dict[str, str] = {
    "EUR_USD": "eurusd",
    "GBP_USD": "gbpusd",
    "XAU_USD": "xauusd",
    "SPX500_USD": "usa500idxusd",
    "NAS100_USD": "usatechidxusd",
}


def asset_to_instrument(asset: str) -> str | None:
    """Map OANDA-style asset code (e.g., 'EUR_USD') to Dukascopy URL
    slug (e.g., 'eurusd'). Returns None for unknown assets — caller
    falls back to literature_prior path cleanly (parity with the
    `event_class is None` branch in Engine 8 line 1025-1027).

    Pure function ; no side effects. Module-level dict lookup ; the
    7-entry size means a `dict.get` is O(1) and faster than any
    branching alternative."""
    return ASSET_TO_INSTRUMENT.get(asset)


@dataclass(frozen=True)
class EmpiricalReactionBetaSnapshot:
    """Read-only snapshot of one (event_class, instrument) empirical
    reaction-beta calibration row.

    Mirrors the ORM `EmpiricalReactionBeta` columns but as a frozen
    dataclass — keeps the consumer call-site decoupled from SQLAlchemy
    session-lifecycle (the row stays valid after the session closes,
    no expired-attribute fetch surprises).

    `p50_drift_bp` / `p75_drift_bp` / `p90_drift_bp` are absolute-value
    magnitudes — sign stripped at the DB layer per ADR-017 boundary +
    r142 trader RED-1 doctrine. Engine 8 applies `business_cycle_sign`
    downstream — same architecture as the literature_prior fallback
    path.
    """

    event_class: str
    instrument: str
    n_observations: int
    p50_drift_bp: float
    p75_drift_bp: float
    p90_drift_bp: float
    window_minutes_before: int
    window_minutes_after: int
    source: str
    computed_at: datetime


async def get_latest_empirical_beta(
    session: AsyncSession,
    *,
    event_class: str,
    instrument: str,
) -> EmpiricalReactionBetaSnapshot | None:
    """Return the latest empirical reaction-beta calibration for
    `(event_class, instrument)`, or None if no row exists.

    Selection : ORDER BY computed_at DESC LIMIT 1 (uses the compound
    index `ix_empirical_reaction_betas_class_instrument_computed_at_desc`).
    Picks the most recent backfill recompute — historical-trace shape
    means older recomputes are preserved for audit but not consumed
    by the live engine.

    None-return is the graceful-degradation contract : Engine 8 falls
    back to literature_prior cleanly. NEVER raise on missing row —
    that would defeat the cold-start safety net.

    Args :
      session : AsyncSession bound to the live request scope.
      event_class : Must match an EVENT_CLASS_BASELINE_BP dict key (e.g.,
        "FOMC", "NFP", "CPI", "Retail_Sales"). Validation happens
        upstream in the engine ; this fn trusts the input and treats
        an unrecognised event_class as a clean cache-miss (returns
        None).
      instrument : Dukascopy URL slug (e.g., "eurusd"). The caller
        typically passes the result of `asset_to_instrument(asset)`.

    Returns :
      EmpiricalReactionBetaSnapshot if a row exists, else None.
    """
    stmt = (
        select(EmpiricalReactionBeta)
        .where(
            EmpiricalReactionBeta.event_class == event_class,
            EmpiricalReactionBeta.instrument == instrument,
        )
        .order_by(EmpiricalReactionBeta.computed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return EmpiricalReactionBetaSnapshot(
        event_class=row.event_class,
        instrument=row.instrument,
        n_observations=row.n_observations,
        # Decimal → float : the ORM column is `Numeric(8, 3)` (Decimal at
        # the Python boundary). Engine 8 multiplies by float multipliers
        # (impact / time_decay / vix), so a float conversion here is
        # cheaper than promoting Engine 8's whole arithmetic chain to
        # Decimal. Precision loss is sub-bp (3 decimals → float64 covers
        # ~15 sig digits) — well below noise floor 0.01bp.
        p50_drift_bp=float(row.p50_drift_bp),
        p75_drift_bp=float(row.p75_drift_bp),
        p90_drift_bp=float(row.p90_drift_bp),
        window_minutes_before=row.window_minutes_before,
        window_minutes_after=row.window_minutes_after,
        source=row.source,
        computed_at=row.computed_at,
    )
