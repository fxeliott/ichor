"""Dealer GEX wall key levels — ADR-083 D3 phase 3 extension (r60).

The "call wall" is the strike with maximum negative dealer gamma —
where dealers are most short calls. Their hedging at this level
absorbs upside attempts (rallies are sold), creating EFFECTIVE
RESISTANCE. The "put wall" is the strike with maximum positive
dealer gamma (most long puts) — dealers buy as the underlying falls
toward this level, creating EFFECTIVE SUPPORT.

Empirically these levels act as magnetism / barrier zones :
- Markets often fail to break through call_wall (resistance)
- Markets often find support at put_wall (downside floor)
- BREACH (spot decisively above call_wall OR below put_wall) signals
  regime change : negative gamma squeeze (above call_wall) OR
  acceleration toward next support (below put_wall)

Source : `gex_snapshots.call_wall` + `put_wall` columns
(numeric(14,4)) pre-computed by flashalpha collector. Same SPY/QQQ
asset proxy mapping as gamma_flip (per ADR-089).

Doctrine bands (relative distance to wall) :
- abs(distance_pct) <= 0.5% : APPROACHING wall (likely magnetism)
- distance > 0% (above wall) : depending on which wall :
  - above call_wall : RESISTANCE BREACHED, squeeze potential
  - above put_wall : safely above support, no signal
- distance < 0% (below wall) :
  - below call_wall : safely below resistance, no signal
  - below put_wall : SUPPORT BREACHED, acceleration risk

Returns batch list[KeyLevel] like gamma_flip — 0 to 4 levels (2 per
asset × 2 assets), only fires when in actionable zone.

References : SqueezeMetrics + Spotgamma framework (open).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .types import KeyLevel

# Approach zone : within ±0.5% of wall = magnetism likely.
WALL_APPROACH_DELTA_PCT = 0.005

# Reuse asset mapping from gamma_flip module.
_GEX_ASSET_TO_ICHOR_ASSET = {
    "SPY": "SPX500_USD",
    "QQQ": "NAS100_USD",
}


async def _fetch_latest_gex_walls(session: AsyncSession) -> list[tuple]:
    """Internal : DISTINCT ON (asset) latest snapshot with non-NULL walls."""
    stmt = text(
        """
        SELECT DISTINCT ON (asset)
               asset, spot_at_capture, call_wall, put_wall, captured_at
        FROM gex_snapshots
        WHERE call_wall IS NOT NULL
          AND put_wall IS NOT NULL
          AND spot_at_capture IS NOT NULL
        ORDER BY asset, captured_at DESC
        """
    )
    return list((await session.execute(stmt)).all())


async def compute_call_wall_levels(session: AsyncSession) -> list[KeyLevel]:
    """Compute call_wall KeyLevels for SPY+QQQ. Returns 0-2 KeyLevels."""
    rows = await _fetch_latest_gex_walls(session)
    out: list[KeyLevel] = []
    for asset_gex, spot, call_wall, _put_wall, captured_at in rows:
        ichor_asset = _GEX_ASSET_TO_ICHOR_ASSET.get(asset_gex)
        if ichor_asset is None:
            continue
        spot_f = float(spot)
        wall_f = float(call_wall)
        if wall_f <= 0:
            continue

        distance_pct = (spot_f - wall_f) / wall_f
        abs_distance = abs(distance_pct)
        source = (
            f"flashalpha:{asset_gex} {captured_at:%Y-%m-%d %H:%M} "
            f"(call_wall, proxy for {ichor_asset})"
        )

        if abs_distance <= WALL_APPROACH_DELTA_PCT:
            note = (
                f"Spot {spot_f:.2f} ~= call_wall {wall_f:.2f} "
                f"(distance {distance_pct * 100:+.2f}%). APPROACHING upside "
                "resistance — dealer hedging absorbs rallies, magnetism "
                "likely. Watch for failure-to-break OR squeeze if breached."
            )
        elif distance_pct > 0:
            # Spot above call_wall : RESISTANCE BREACHED
            note = (
                f"Spot {spot_f:.2f} above call_wall {wall_f:.2f} "
                f"({distance_pct * 100:+.2f}%). RESISTANCE BREACHED — "
                "negative-gamma squeeze potential, dealer short-call "
                "hedging fuels upside cascade. Vol-of-vol expansion likely."
            )
        else:
            # Spot well below call_wall : safely below resistance, no signal
            continue

        out.append(
            KeyLevel(
                asset=ichor_asset,
                level=wall_f,
                kind="gex_call_wall",
                side="above_long_below_short",
                source=source,
                note=note,
            )
        )
    return out


async def compute_put_wall_levels(session: AsyncSession) -> list[KeyLevel]:
    """Compute put_wall KeyLevels for SPY+QQQ. Returns 0-2 KeyLevels."""
    rows = await _fetch_latest_gex_walls(session)
    out: list[KeyLevel] = []
    for asset_gex, spot, _call_wall, put_wall, captured_at in rows:
        ichor_asset = _GEX_ASSET_TO_ICHOR_ASSET.get(asset_gex)
        if ichor_asset is None:
            continue
        spot_f = float(spot)
        wall_f = float(put_wall)
        if wall_f <= 0:
            continue

        distance_pct = (spot_f - wall_f) / wall_f
        abs_distance = abs(distance_pct)
        source = (
            f"flashalpha:{asset_gex} {captured_at:%Y-%m-%d %H:%M} "
            f"(put_wall, proxy for {ichor_asset})"
        )

        if abs_distance <= WALL_APPROACH_DELTA_PCT:
            note = (
                f"Spot {spot_f:.2f} ~= put_wall {wall_f:.2f} "
                f"(distance {distance_pct * 100:+.2f}%). APPROACHING downside "
                "support — dealer hedging absorbs declines, magnetism "
                "likely. Watch for bounce OR breach acceleration."
            )
        elif distance_pct < 0:
            # Spot below put_wall : SUPPORT BREACHED
            note = (
                f"Spot {spot_f:.2f} below put_wall {wall_f:.2f} "
                f"({distance_pct * 100:+.2f}%). SUPPORT BREACHED — dealer "
                "long-put hedging unwinds, acceleration risk toward next "
                "support. Funding-stress conditions possible."
            )
        else:
            # Spot well above put_wall : safely above support, no signal
            continue

        out.append(
            KeyLevel(
                asset=ichor_asset,
                level=wall_f,
                kind="gex_put_wall",
                side="above_long_below_short",
                source=source,
                note=note,
            )
        )
    return out
