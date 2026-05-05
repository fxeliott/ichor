"""GEX persistence — write FlashAlpha snapshots into `gex_snapshots`.

Phase 2 fix for SPEC.md §2.2 #9 (FlashAlpha collected without persistence).
Pairs with the model `PolygonGexSnapshot` and the migration
`0008_gex_snapshots.py`.

Idempotency: we don't enforce a unique constraint on (asset, captured_at)
because the API may legitimately return identical timestamps under high
poll cadence; we accept duplicates and dedupe at read time via DISTINCT
ON (asset, captured_at).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..collectors.flashalpha import GexSnapshot
from ..models import PolygonGexSnapshot


def _to_decimal(v: float | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (TypeError, ValueError):
        return None


async def persist_gex_snapshots(
    session: AsyncSession,
    snapshots: list[GexSnapshot],
) -> int:
    """Insert all snapshots. Returns the count inserted."""
    if not snapshots:
        return 0
    now = datetime.now(UTC)
    rows = []
    for s in snapshots:
        rows.append(
            PolygonGexSnapshot(
                id=uuid4(),
                captured_at=s.as_of,
                created_at=now,
                asset=s.ticker,
                dealer_gex_total=_to_decimal(s.total_gex_usd),
                gamma_flip=_to_decimal(s.gamma_flip),
                call_wall=_to_decimal(s.call_wall),
                put_wall=_to_decimal(s.put_wall),
                vol_trigger=_to_decimal(s.zero_gamma),
                spot_at_capture=_to_decimal(s.spot),
                source="flashalpha",
                raw=s.raw if isinstance(s.raw, dict) else None,
            )
        )
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def latest_gex_per_asset(
    session: AsyncSession,
    *,
    assets: tuple[str, ...] = ("SPX", "NDX"),
    max_age_hours: int = 24,
) -> dict[str, PolygonGexSnapshot]:
    """Return the freshest snapshot per asset (None values dropped)."""
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    out: dict[str, PolygonGexSnapshot] = {}
    for asset in assets:
        row = (
            await session.execute(
                select(PolygonGexSnapshot)
                .where(
                    PolygonGexSnapshot.asset == asset,
                    PolygonGexSnapshot.captured_at >= cutoff,
                )
                .order_by(desc(PolygonGexSnapshot.captured_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            out[asset] = row
    return out


async def render_gex_block(
    session: AsyncSession,
    asset: str,
) -> tuple[str, list[str]]:
    """Markdown block for the data_pool `gex` section.

    The asset parameter is the Ichor symbol (e.g. NAS100_USD). We map it
    to the FlashAlpha ticker when applicable; otherwise we return an
    empty section (FX / metals don't have GEX).
    """
    asset_to_gex = {
        "NAS100_USD": "NDX",
        "SPX500_USD": "SPX",
    }
    gex_ticker = asset_to_gex.get(asset.upper())
    if gex_ticker is None:
        return "", []  # asset has no GEX coverage

    latest = await latest_gex_per_asset(session, assets=(gex_ticker,))
    snap = latest.get(gex_ticker)
    if snap is None:
        return (
            f"## Dealer GEX ({gex_ticker})\n"
            "- (no fresh snapshot — FlashAlpha may be down or quota exhausted)",
            [],
        )

    parts: list[str] = [f"## Dealer GEX ({gex_ticker})"]
    if snap.dealer_gex_total is not None:
        sign = "long" if float(snap.dealer_gex_total) > 0 else "short"
        parts.append(
            f"- Net gamma: {float(snap.dealer_gex_total):,.0f} USD "
            f"(dealers {sign} gamma — "
            f"{'vol-suppressing' if sign == 'long' else 'vol-amplifying'})"
        )
    if snap.gamma_flip is not None:
        parts.append(f"- Gamma flip: {float(snap.gamma_flip):.2f}")
    if snap.call_wall is not None:
        parts.append(f"- Call wall (resistance): {float(snap.call_wall):.2f}")
    if snap.put_wall is not None:
        parts.append(f"- Put wall (support): {float(snap.put_wall):.2f}")
    if snap.spot_at_capture is not None:
        parts.append(f"- Spot at capture: {float(snap.spot_at_capture):.2f}")
    parts.append(f"- Captured at: {snap.captured_at.isoformat()}")
    return "\n".join(parts), [f"flashalpha:{gex_ticker}"]
