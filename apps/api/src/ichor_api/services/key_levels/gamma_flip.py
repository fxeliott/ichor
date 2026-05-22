"""Gamma flip key levels — ADR-083 D3 phase 3 (r56).

Dealer gamma exposure (GEX) framework per SqueezeMetrics + Spotgamma :

The "gamma flip" is the underlying price at which aggregate dealer
gamma exposure crosses zero. Above the flip, dealers are net-LONG
gamma — they hedge by SELLING strength + BUYING weakness, which
DAMPENS realized volatility (mean-reversion regime). Below the flip,
dealers are net-SHORT gamma — they hedge by BUYING strength +
SELLING weakness, which AMPLIFIES volatility (trend-continuation
regime, "fragile market" condition).

The flip itself is a regime transition trigger : when spot crosses
the flip level (in either direction), the entire intraday volatility
character of the market changes.

Source : `gex_snapshots` table populated by flashalpha collector
(13:00 + 21:00 Paris daily) with pre-computed `gamma_flip` column
(numeric(14,4)). Assets covered : SPY (SPX500 proxy per ADR-089) +
QQQ (NAS100 proxy).

Asset mapping (per ADR-089) :
- gex_snapshots.asset='SPY'  →  KeyLevel.asset='SPX500_USD'
- gex_snapshots.asset='QQQ'  →  KeyLevel.asset='NAS100_USD'

Doctrine :
- spot >> flip (>1% above) : safely dealer-long gamma, vol-dampening
  regime (range-bound, mean-reversion). KeyLevel fires for context
  with "above flip" framing.
- spot ~~ flip (within 0.5%) : transition zone — even small move
  could flip regime. HIGH-attention KeyLevel "flip imminent".
- spot << flip (>1% below) : dealer-short gamma, vol-amplification
  regime (momentum, trend continuation). KeyLevel fires with
  "below flip" framing.

References :
- SqueezeMetrics "Gamma Exposure" white paper (2017, public)
- Spotgamma daily notes (subscription, but framework is open)
- ADR-066 gex_yfinance collector + ADR-089 SPY/QQQ proxies
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .types import KeyLevel

# Threshold for "transition zone" — within ±0.5% of gamma_flip.
GAMMA_FLIP_TRANSITION_DELTA_PCT = 0.005

# r67 defense-in-depth — reject an implausibly-far flip. The collector
# (gex_yfinance._GAMMA_FLIP_MAX_SPOT_DISTANCE_PCT = 0.15) is the primary
# domain constraint, but `gex_snapshots` already contains garbage rows
# persisted before that fix (QQQ 2026-05-15 21:30 spot 710.74 / flip
# 310.43 = -56%, rendering "+128.95%" nonsense on the /briefing
# dashboard). This read-path guard is the backstop : a flip more than
# 25% from spot is definitionally corrupt (a real dealer gamma flip is
# structurally near spot, empirically within ~1%). 25% is deliberately
# more lenient than the collector's 15% — the computer doesn't
# second-guess borderline-but-plausible collector output, it only
# hard-rejects the unambiguous garbage class. Skipping the KeyLevel is
# honest ; a wrong number on a premium UI erodes trust faster than a
# missing one.
_GAMMA_FLIP_SANITY_MAX_DISTANCE_PCT = 0.25

# Asset proxy mapping per ADR-089.
_GEX_ASSET_TO_ICHOR_ASSET = {
    "SPY": "SPX500_USD",
    "QQQ": "NAS100_USD",
}


async def compute_gamma_flip_levels(session: AsyncSession) -> list[KeyLevel]:
    """Compute gamma_flip KeyLevels for all gex_snapshots assets (SPY+QQQ).

    Reads the LATEST snapshot per asset (DISTINCT ON (asset)).
    Returns a list of 0-2 KeyLevels (one per asset with data + non-NULL
    gamma_flip + non-NULL spot_at_capture).

    Side semantics : `above_long_below_short` reflects dealer-gamma
    sign — above flip = dealers long gamma = vol-dampening (mean-
    reversion) ; below flip = dealers short gamma = vol-amplification
    (trend-continuation). Pass 2 should weigh as a regime-modulator,
    not a directional signal.
    """
    # Raw SQL DISTINCT ON for one row per asset (latest snapshot)
    from sqlalchemy import text

    stmt = text(
        """
        SELECT DISTINCT ON (asset)
               asset, spot_at_capture, gamma_flip, captured_at
        FROM gex_snapshots
        WHERE gamma_flip IS NOT NULL AND spot_at_capture IS NOT NULL
        ORDER BY asset, captured_at DESC
        """
    )
    rows = (await session.execute(stmt)).all()

    out: list[KeyLevel] = []
    for asset_gex, spot, flip, captured_at in rows:
        ichor_asset = _GEX_ASSET_TO_ICHOR_ASSET.get(asset_gex)
        if ichor_asset is None:
            # Unknown gex asset (future-proof for if e.g. IWM/DIA added).
            continue
        spot_f = float(spot)
        flip_f = float(flip)
        if flip_f <= 0:
            # Defensive : a NULL/zero flip would yield meaningless distance.
            continue

        distance_pct = (spot_f - flip_f) / flip_f
        abs_distance_pct = abs(distance_pct)

        # r67 defense-in-depth : reject a flip that is implausibly far
        # from spot (corrupt collector data already persisted before the
        # gex_yfinance band fix). A real dealer gamma flip is structurally
        # near spot ; >25% away is numerical garbage, not signal.
        if abs_distance_pct > _GAMMA_FLIP_SANITY_MAX_DISTANCE_PCT:
            continue

        source = f"flashalpha:{asset_gex} {captured_at:%Y-%m-%d %H:%M} (proxy for {ichor_asset})"

        if abs_distance_pct <= GAMMA_FLIP_TRANSITION_DELTA_PCT:
            # Transition zone : within 0.5%
            note = (
                f"Spot {spot_f:.2f} ~= flip {flip_f:.2f} "
                f"(distance {distance_pct * 100:+.2f}% of flip). "
                "TRANSITION ZONE — small move flips dealer-gamma regime "
                "(vol-dampening ↔ vol-amplification). HIGH attention to "
                "intraday vol regime change."
            )
        elif distance_pct > 0:
            # Spot above flip : dealer-long gamma, vol-dampening regime
            note = (
                f"Spot {spot_f:.2f} above flip {flip_f:.2f} "
                f"({distance_pct * 100:+.2f}%). Dealer-long gamma regime — "
                "intraday vol DAMPENED (mean-reversion bias, hedging "
                "absorbs directional momentum). Range-bound preference."
            )
        else:
            # Spot below flip : dealer-short gamma, vol-amplification regime
            note = (
                f"Spot {spot_f:.2f} below flip {flip_f:.2f} "
                f"({distance_pct * 100:+.2f}%). Dealer-short gamma regime — "
                "intraday vol AMPLIFIED (trend-continuation, hedging "
                "FUELS directional moves). Fragile-market condition, "
                "watch for vol cluster + breakout follow-through."
            )

        out.append(
            KeyLevel(
                asset=ichor_asset,
                level=flip_f,
                kind="gamma_flip",
                side="above_long_below_short",
                source=source,
                note=note,
            )
        )

    return out
