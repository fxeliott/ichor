"""Vol/credit regime switch key levels — ADR-083 D3 phase 4 (r57).

Three threshold-based regime switches (similar pattern to TGA) :

1. **VIX regime switch** (per ADR-044 cross-asset matrix v2 doctrine)
   - <12 : extreme complacency (mean-revert short-vol risk)
   - 12-15 : low-vol regime (carry-friendly)
   - 15-25 : NORMAL → no signal
   - 25-35 : elevated/risk-off transition (defensive)
   - >35 : crisis regime (panic, vol-of-vol explosive)

2. **SKEW regime switch** (per ADR-055 + Bevilacqua-Tunaru 2021)
   The CBOE SKEW measures OTM put skew premium — high SKEW means
   the market is pricing left-tail (crash) risk expensively.
   - <120 : low tail-risk pricing (call-side asymmetric pressure)
   - 120-130 : NORMAL → no signal
   - 130-145 : elevated tail concern (hedging demand rising)
   - >145 : extreme tail-risk pricing (left-tail crash hedging)

3. **HY OAS regime switch** (per cross-asset matrix v2)
   BAMLH0A0HYM2 = ICE BofA US High Yield Master II OAS (option-
   adjusted spread, percent). Credit spreads widening = funding
   stress / risk-off ; tightening = complacency / risk-on.
   - <3% : complacency (carry trade favored, late-cycle warning)
   - 3-5% : NORMAL → no signal
   - 5-7% : elevated stress (HY-led risk-off building)
   - >7% : crisis regime (default cycle accelerating)

References :
- ADR-044 VIX_SPIKE / VIX_PANIC alerts
- ADR-055 DOLLAR_SMILE_BREAK SKEW extension
- CLAUDE.md cross-asset matrix v2 (W79)
- Brunnermeier-Pedersen 2009 funding-liquidity (HY-OAS funding-stress)
- Hou-Mo-Xue 2015 q-factor (vol-regime asset pricing)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.cboe_skew_observation import CboeSkewObservation
from ...models.fred_observation import FredObservation
from .types import KeyLevel

# VIX bands (CBOE Volatility Index, percentage points).
VIX_EXTREME_COMPLACENCY = 12.0
VIX_LOW_VOL_FLOOR = 15.0  # below 15 = low-vol regime
VIX_NORMAL_CEILING = 25.0  # above 25 = elevated
VIX_CRISIS_FLOOR = 35.0  # above 35 = crisis

# SKEW bands (CBOE SKEW Index, dimensionless).
SKEW_LOW_TAIL_CEILING = 120.0  # below 120 = low tail-risk pricing
SKEW_NORMAL_CEILING = 130.0  # above 130 = elevated tail concern
SKEW_EXTREME_FLOOR = 145.0  # above 145 = extreme tail-risk pricing

# HY OAS bands (BAMLH0A0HYM2, percentage points).
HY_OAS_COMPLACENCY_CEILING = 3.0  # below 3% = complacency
HY_OAS_NORMAL_CEILING = 5.0  # above 5% = elevated stress
HY_OAS_CRISIS_FLOOR = 7.0  # above 7% = crisis


async def _latest_fred(session: AsyncSession, series_id: str):
    """Helper : latest (value, date) tuple for a FRED series, or None."""
    stmt = (
        select(FredObservation.value, FredObservation.observation_date)
        .where(FredObservation.series_id == series_id)
        .order_by(FredObservation.observation_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).first()


async def compute_vix_regime_switch(session: AsyncSession) -> KeyLevel | None:
    """VIX regime KeyLevel from FRED VIXCLS. Returns None in NORMAL band."""
    row = await _latest_fred(session, "VIXCLS")
    if row is None or row[0] is None:
        return None
    vix = float(row[0])
    when = row[1]
    source = f"FRED:VIXCLS {when:%Y-%m-%d}"

    if vix < VIX_EXTREME_COMPLACENCY:
        return KeyLevel(
            asset="USD",
            level=vix,
            kind="vix_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"VIX {vix:.2f} below {VIX_EXTREME_COMPLACENCY:.0f} — extreme complacency. "
                "Mean-reversion risk on short-vol positioning. "
                "Late-cycle warning : carry-trade unwind asymmetric vulnerability."
            ),
        )
    if vix < VIX_LOW_VOL_FLOOR:
        return KeyLevel(
            asset="USD",
            level=vix,
            kind="vix_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"VIX {vix:.2f} below {VIX_LOW_VOL_FLOOR:.0f} — low-vol regime. "
                "Carry-friendly conditions, range-bound preference."
            ),
        )
    if vix > VIX_CRISIS_FLOOR:
        return KeyLevel(
            asset="USD",
            level=vix,
            kind="vix_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"VIX {vix:.2f} above {VIX_CRISIS_FLOOR:.0f} — CRISIS REGIME. "
                "Vol-of-vol explosive ; haven_bid bias dominant ; correlations collapse to 1."
            ),
        )
    if vix > VIX_NORMAL_CEILING:
        return KeyLevel(
            asset="USD",
            level=vix,
            kind="vix_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"VIX {vix:.2f} above {VIX_NORMAL_CEILING:.0f} — elevated/risk-off "
                "transition. Defensive bias, USD-haven flows possible."
            ),
        )
    # NORMAL band 15-25
    return None


async def compute_skew_regime_switch(session: AsyncSession) -> KeyLevel | None:
    """SKEW regime KeyLevel from cboe_skew_observations. None in NORMAL band."""
    stmt = (
        select(CboeSkewObservation.skew_value, CboeSkewObservation.observation_date)
        .order_by(CboeSkewObservation.observation_date.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None or row[0] is None:
        return None
    skew = float(row[0])
    when = row[1]
    source = f"cboe_skew:{when:%Y-%m-%d}"

    if skew < SKEW_LOW_TAIL_CEILING:
        return KeyLevel(
            asset="USD",
            level=skew,
            kind="skew_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"SKEW {skew:.1f} below {SKEW_LOW_TAIL_CEILING:.0f} — low tail-risk "
                "pricing. Call-side asymmetric pressure (right-tail melt-up risk dominates)."
            ),
        )
    if skew > SKEW_EXTREME_FLOOR:
        return KeyLevel(
            asset="USD",
            level=skew,
            kind="skew_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"SKEW {skew:.1f} above {SKEW_EXTREME_FLOOR:.0f} — EXTREME tail-risk "
                "pricing. Left-tail (crash) hedging demand peaked ; contrarian "
                "mean-revert opportunity in OTM puts but risk-off bias persists."
            ),
        )
    if skew > SKEW_NORMAL_CEILING:
        return KeyLevel(
            asset="USD",
            level=skew,
            kind="skew_regime_switch",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"SKEW {skew:.1f} above {SKEW_NORMAL_CEILING:.0f} — elevated tail "
                "concern. Hedging demand rising ; left-tail premium expanding "
                "vs ATM (smile steepening)."
            ),
        )
    # NORMAL band 120-130
    return None


async def compute_hy_oas_percentile(session: AsyncSession) -> KeyLevel | None:
    """HY OAS regime KeyLevel from FRED BAMLH0A0HYM2. None in NORMAL band.

    Note : ADR-083 D3 spec mentions "historical percentiles (90%, 99%)"
    but with limited DB history (11 rows r57), percentile from rolling
    sample is unreliable. Uses absolute threshold doctrine bands per
    CLAUDE.md cross-asset matrix v2 instead. Once history accumulates
    >100 rows (~6 months), can switch to true percentile-based logic.
    """
    row = await _latest_fred(session, "BAMLH0A0HYM2")
    if row is None or row[0] is None:
        return None
    oas = float(row[0])
    when = row[1]
    source = f"FRED:BAMLH0A0HYM2 {when:%Y-%m-%d}"

    if oas < HY_OAS_COMPLACENCY_CEILING:
        return KeyLevel(
            asset="USD",
            level=oas,
            kind="hy_oas_percentile",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"HY OAS {oas:.2f}% below {HY_OAS_COMPLACENCY_CEILING:.1f}% — credit "
                "complacency. Carry trade favored ; late-cycle warning sign for "
                "asymmetric risk to widening (mean-reversion of spreads)."
            ),
        )
    if oas > HY_OAS_CRISIS_FLOOR:
        return KeyLevel(
            asset="USD",
            level=oas,
            kind="hy_oas_percentile",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"HY OAS {oas:.2f}% above {HY_OAS_CRISIS_FLOOR:.1f}% — CRISIS regime. "
                "Default cycle accelerating ; haven_bid dominant ; HY-led risk-off."
            ),
        )
    if oas > HY_OAS_NORMAL_CEILING:
        return KeyLevel(
            asset="USD",
            level=oas,
            kind="hy_oas_percentile",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"HY OAS {oas:.2f}% above {HY_OAS_NORMAL_CEILING:.1f}% — elevated "
                "stress. HY-led risk-off building ; funding-stress proxy via "
                "Brunnermeier-Pedersen 2009 channel."
            ),
        )
    # NORMAL band 3-5%
    return None
