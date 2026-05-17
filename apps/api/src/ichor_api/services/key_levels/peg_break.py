"""Peg break key levels — ADR-083 D3 phase 2 (r55).

Currency pegs are macro/microstructure switches : the central bank
commits to defending a fixed rate or band ; when market price
approaches the band edges, intervention probability rises sharply.

Pegs implemented r55 :
- **HKMA hard peg** : USD/HKD = 7.80 with convertibility band
  [7.75, 7.85]. HKMA commits to buy HKD at 7.85 (weak-side, USD
  strengthening) and sell HKD at 7.75 (strong-side). Intervention
  empirically observed multiple times 2022-2024 at the weak-side.

Pegs deferred r56+ :
- **PBOC daily fix CFETS ± 2σ** : requires CFETS daily reference
  rate (not in FRED natively, needs separate ADR for cfets.org.cn
  scraping or alternative source). Plus DEXCHUS only has 2 rows
  in DB at r55 time, insufficient for ±2σ historical band.

Doctrine (HKMA convertibility undertaking, Jul 2005) :
- Rate ≥ 7.85 : weak-side intervention LIVE — HKMA buying HKD,
  HKD-bid expected, USD/HKD ceiling defended.
- 7.82 ≤ rate < 7.85 : approaching weak-side — HKD bid likely
  (intervention probability elevated within 0.03 of band edge).
- 7.78 < rate < 7.82 : neutral mid-band (no actionable signal).
- 7.75 < rate ≤ 7.78 : approaching strong-side — HKD offer likely.
- Rate ≤ 7.75 : strong-side intervention LIVE — HKMA selling HKD.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.fred_observation import FredObservation
from .types import KeyLevel

# HKMA convertibility band edges (USD/HKD).
HKMA_WEAK_SIDE_EDGE = 7.85  # HKMA buys HKD here (USD/HKD ceiling)
HKMA_STRONG_SIDE_EDGE = 7.75  # HKMA sells HKD here (USD/HKD floor)
HKMA_PEG_CENTER = 7.80
# "Approaching" zone : within ±0.03 of band edge. Catches real-time
# market movement before the actual intervention. Empirically derived
# from HKMA 2022-2024 intervention episodes (weak-side mostly,
# rate spent significant time in 7.82-7.85 window before each
# intervention round).
HKMA_APPROACH_DELTA = 0.03


async def compute_hkma_peg_break(session: AsyncSession) -> KeyLevel | None:
    """Compute HKMA USD/HKD peg-break KeyLevel from FRED `DEXHKUS`.

    Returns a KeyLevel with `kind="peg_break_hkma"` if the latest
    USD/HKD rate is in or approaching either intervention band. Returns
    None if no DEXHKUS data OR rate is in the neutral 7.78-7.82 mid-band.
    """
    stmt = (
        select(FredObservation.value, FredObservation.observation_date)
        .where(FredObservation.series_id == "DEXHKUS")
        .order_by(FredObservation.observation_date.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None or row[0] is None:
        return None

    rate = float(row[0])
    obs_date = row[1]
    source = f"FRED:DEXHKUS {obs_date:%Y-%m-%d}"

    # Weak-side intervention LIVE
    if rate >= HKMA_WEAK_SIDE_EDGE:
        return KeyLevel(
            asset="USDHKD",
            level=HKMA_WEAK_SIDE_EDGE,
            kind="peg_break_hkma",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"USD/HKD {rate:.4f} at-or-above weak-side edge {HKMA_WEAK_SIDE_EDGE} — "
                "HKMA intervention LIVE (buying HKD to defend ceiling). "
                "HKD bid pressure ; affects HKMA reserves + Asian liquidity proxy."
            ),
        )
    # Approaching weak-side (within HKMA_APPROACH_DELTA of edge)
    if rate >= HKMA_WEAK_SIDE_EDGE - HKMA_APPROACH_DELTA:
        return KeyLevel(
            asset="USDHKD",
            level=HKMA_WEAK_SIDE_EDGE,
            kind="peg_break_hkma",
            side="above_risk_off_below_risk_on",
            source=source,
            note=(
                f"USD/HKD {rate:.4f} approaching weak-side edge {HKMA_WEAK_SIDE_EDGE} "
                f"(within {HKMA_APPROACH_DELTA:.2f}). HKMA intervention probability "
                "elevated ; watch for ceiling defence + HKD bid."
            ),
        )
    # Strong-side intervention LIVE
    if rate <= HKMA_STRONG_SIDE_EDGE:
        return KeyLevel(
            asset="USDHKD",
            level=HKMA_STRONG_SIDE_EDGE,
            kind="peg_break_hkma",
            side="above_risk_on_below_risk_off",
            source=source,
            note=(
                f"USD/HKD {rate:.4f} at-or-below strong-side edge {HKMA_STRONG_SIDE_EDGE} — "
                "HKMA intervention LIVE (selling HKD to defend floor). "
                "HKD offer pressure ; expansionary for HK monetary base."
            ),
        )
    # Approaching strong-side
    if rate <= HKMA_STRONG_SIDE_EDGE + HKMA_APPROACH_DELTA:
        return KeyLevel(
            asset="USDHKD",
            level=HKMA_STRONG_SIDE_EDGE,
            kind="peg_break_hkma",
            side="above_risk_on_below_risk_off",
            source=source,
            note=(
                f"USD/HKD {rate:.4f} approaching strong-side edge {HKMA_STRONG_SIDE_EDGE} "
                f"(within {HKMA_APPROACH_DELTA:.2f}). HKMA intervention probability "
                "elevated ; watch for floor defence + HKD offer."
            ),
        )
    # Neutral mid-band — no actionable signal
    return None
