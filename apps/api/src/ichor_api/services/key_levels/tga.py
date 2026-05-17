"""TGA (Treasury General Account) key level computer — ADR-083 D3 phase 1.

The Fed's TGA balance is one of the canonical "liquidity gate"
thresholds per ADR-083 D3. Doctrine (Brunnermeier-Pedersen 2009
funding-liquidity, Acharya-Eisert-Eufinger-Hirsch 2018) :

- **TGA falling fast** (Treasury repaying / spending down) →
  cash flows from Treasury account back into the banking system →
  reserves rise → **liquidity injection imminent**, USD-bearish for
  short horizons (M1 expansion proxy).
- **TGA rising fast** (Treasury rebuilding cash / refunding) →
  cash drained from banks into Treasury account → reserves fall →
  **liquidity drain expected**, USD-bid in funding-stress regimes.

Source : FRED `WTREGEN` (Treasury General Account Weekly average,
billions USD). Published every Wednesday by Treasury, ingested via
`ichor-collector@dts_treasury.service` daily 04:00 Paris.

Threshold doctrine — empirical bands from 2020-2026 historical range :
- **< $300B** : LOW. Liquidity injection imminent (drain almost done).
- **300-700B** : MID. Neutral.
- **> $700B** : HIGH. Liquidity drain expected (rebuilding for refunding).

Outside these bands triggers a `KeyLevel` with `side` set to the
appropriate direction. Within mid-band, returns None (no actionable
threshold-cross signal).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.fred_observation import FredObservation
from .types import KeyLevel

# Empirical bands ($billions). Source : FRED WTREGEN 2020-2026 quartiles.
# Sept 2021 (post-extraordinary-measures) hit $1.6T peak ; June 2023
# debt-ceiling resolution low was $23B. Median ~$500B. We pick wide
# bands to avoid false-trigger noise.
TGA_LOW_THRESHOLD_BN = 300.0
TGA_HIGH_THRESHOLD_BN = 700.0


async def compute_tga_key_level(session: AsyncSession) -> KeyLevel | None:
    """Compute the current TGA-based liquidity-gate KeyLevel.

    Returns None if :
      - no WTREGEN data in DB (collector not yet ingested)
      - latest TGA value falls within the neutral mid-band
        (300B <= TGA <= 700B) — no actionable threshold cross.

    Returns a KeyLevel with `kind="tga_liquidity_gate"` if the latest
    TGA value crosses below LOW or above HIGH threshold.
    """
    stmt = (
        select(FredObservation.value, FredObservation.observation_date)
        .where(FredObservation.series_id == "WTREGEN")
        .order_by(FredObservation.observation_date.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None or row[0] is None:
        return None

    # FRED WTREGEN is reported in MILLIONS of USD per FRED metadata
    # (https://fred.stlouisfed.org/series/WTREGEN unit = "Millions of
    # Dollars"). Convert to billions for human-readable thresholds and
    # consistent doctrine bands.
    value_bn = float(row[0]) / 1000.0
    obs_date = row[1]

    if value_bn < TGA_LOW_THRESHOLD_BN:
        return KeyLevel(
            asset="USD",
            level=value_bn,
            kind="tga_liquidity_gate",
            side="above_liquidity_drain_below_inject",
            source=f"FRED:WTREGEN {obs_date:%Y-%m-%d}",
            note=(
                f"TGA ${value_bn:.0f}B below ${TGA_LOW_THRESHOLD_BN:.0f}B threshold — "
                "liquidity injection imminent (Treasury cash floor approaching, refill cycle next), "
                "USD-bearish at short horizons via reserves expansion."
            ),
        )
    if value_bn > TGA_HIGH_THRESHOLD_BN:
        return KeyLevel(
            asset="USD",
            level=value_bn,
            kind="tga_liquidity_gate",
            side="above_liquidity_drain_below_inject",
            source=f"FRED:WTREGEN {obs_date:%Y-%m-%d}",
            note=(
                f"TGA ${value_bn:.0f}B above ${TGA_HIGH_THRESHOLD_BN:.0f}B threshold — "
                "liquidity drain expected (Treasury rebuilding cash for refunding ops), "
                "USD-bid in funding-stress regimes via reserves contraction."
            ),
        )
    return None
