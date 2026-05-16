"""GET /v1/positioning — MyFXBook retail long/short outlook (contrarian).

r69 — exposes the `myfxbook_outlooks` table (W77 collector LIVE since
2026-05-09, ADR-074) which had NO read endpoint. Same "data exists but
unprojected" class as the r66 session_type + r68 scenarios gaps : the
collector ingests fine but nothing surfaces it to the dashboard.

Contrarian doctrine (W77 / ADR-074) : the MyFXBook retail population is
self-selected and historically wrong at extremes — crowded retail short
often precedes a bounce, crowded retail long often precedes a fade. We
expose the raw split + a *context tilt* descriptor. This is NOT a
trade signal (ADR-017 boundary) — it is sentiment context, expressed in
the same directional-context vocabulary as the rest of Ichor
(bullish/bearish *tilt*, never BUY/SELL).

Coverage : MyFXBook is FX/metals only. EUR/USD, GBP/USD, XAU/USD have
data ; SPX500/NAS100 (equity indices) do NOT — callers render "N/A for
indices" gracefully.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import CftcTffObservation, CotPosition

router = APIRouter(prefix="/v1/positioning", tags=["positioning"])

# Contrarian bands on the dominant-side percentage (0-100).
_EXTREME_PCT = 80.0
_CROWDED_PCT = 65.0


class PositioningEntry(BaseModel):
    pair: str
    long_pct: float
    short_pct: float
    long_volume: float | None
    short_volume: float | None
    long_positions: int | None
    short_positions: int | None
    fetched_at: datetime
    dominant_side: Literal["long", "short", "balanced"]
    intensity: Literal["balanced", "crowded", "extreme"]
    contrarian_tilt: Literal["bullish", "bearish", "neutral"]
    note: str


class PositioningOut(BaseModel):
    generated_at: datetime
    n_pairs: int
    entries: list[PositioningEntry]


def _classify(long_pct: float, short_pct: float) -> tuple[str, str, str, str]:
    """Return (dominant_side, intensity, contrarian_tilt, note)."""
    dominant_pct = max(long_pct, short_pct)
    if dominant_pct >= _EXTREME_PCT:
        intensity = "extreme"
    elif dominant_pct >= _CROWDED_PCT:
        intensity = "crowded"
    else:
        intensity = "balanced"

    if intensity == "balanced":
        return (
            "balanced",
            "balanced",
            "neutral",
            f"Retail réparti {long_pct:.0f}% long / {short_pct:.0f}% short — "
            "pas de signal contrarian (foule non extrême).",
        )

    if short_pct > long_pct:
        # Crowded/extreme retail SHORT → contrarian BULLISH tilt.
        return (
            "short",
            intensity,
            "bullish",
            f"Retail {short_pct:.0f}% short ({intensity}). La foule retail est "
            "structurellement à contre-sens aux extrêmes — biais contrarian "
            "HAUSSIER (squeeze des shorts possible). Contexte, pas un ordre.",
        )
    # Crowded/extreme retail LONG → contrarian BEARISH tilt.
    return (
        "long",
        intensity,
        "bearish",
        f"Retail {long_pct:.0f}% long ({intensity}). La foule retail est "
        "structurellement à contre-sens aux extrêmes — biais contrarian "
        "BAISSIER (fade des longs possible). Contexte, pas un ordre.",
    )


@router.get("", response_model=PositioningOut)
async def get_positioning(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PositioningOut:
    """Latest MyFXBook retail outlook per pair (DISTINCT ON pair).

    Empty `entries` if the collector hasn't run yet (graceful — the
    dashboard renders an "indisponible" empty state).
    """
    stmt = text(
        """
        SELECT DISTINCT ON (pair)
               pair, long_pct, short_pct, long_volume, short_volume,
               long_positions, short_positions, fetched_at
        FROM myfxbook_outlooks
        ORDER BY pair, fetched_at DESC
        """
    )
    rows = (await session.execute(stmt)).all()

    entries: list[PositioningEntry] = []
    newest = datetime.now().astimezone()
    for (
        pair,
        long_pct,
        short_pct,
        long_volume,
        short_volume,
        long_positions,
        short_positions,
        fetched_at,
    ) in rows:
        dominant, intensity, tilt, note = _classify(float(long_pct), float(short_pct))
        entries.append(
            PositioningEntry(
                pair=pair,
                long_pct=float(long_pct),
                short_pct=float(short_pct),
                long_volume=float(long_volume) if long_volume is not None else None,
                short_volume=float(short_volume) if short_volume is not None else None,
                long_positions=long_positions,
                short_positions=short_positions,
                fetched_at=fetched_at,
                dominant_side=dominant,  # type: ignore[arg-type]
                intensity=intensity,  # type: ignore[arg-type]
                contrarian_tilt=tilt,  # type: ignore[arg-type]
                note=note,
            )
        )

    return PositioningOut(
        generated_at=newest,
        n_pairs=len(entries),
        entries=entries,
    )


# ─── /institutional : CFTC TFF + COT (the "acteurs du marché" layer) ───
# ADR-099 Tier 1.4a. Mirrors data_pool._section_tff_positioning +
# _section_cot EXACTLY (same trader conventions) so the dashboard
# surfaces the SAME institutional read the 4-pass LLM sees. CFTC is
# weekly, data cut-off Tuesday, released ~Friday — `report_date` makes
# the lag explicit (honest, no fake freshness). ADR-017-safe: pure
# positioning facts + a descriptive smart-money divergence flag, no
# BUY/SELL. TFF covers all 5 priority assets (incl. SPX500 13874A) ;
# COT covers 4 (no SPX500 E-mini in the collector yet).


class TffPositioning(BaseModel):
    market_code: str
    report_date: date
    open_interest: int
    dealer_net: int
    asset_mgr_net: int
    lev_money_net: int
    other_net: int
    dealer_dw: int | None
    asset_mgr_dw: int | None
    lev_money_dw: int | None
    smart_money_divergence: bool


class CotPositioning(BaseModel):
    market_code: str
    report_date: date
    open_interest: int
    managed_money_net: int
    swap_dealer_net: int
    producer_net: int
    delta_1w: int | None
    delta_4w: int | None
    delta_12w: int | None
    pattern: Literal["accelerating", "reversal", "stable"]


class InstitutionalPositioningOut(BaseModel):
    asset: str
    cadence: str = "Hebdomadaire — données CFTC arrêtées au mardi, publiées ~vendredi"
    tff: TffPositioning | None
    cot: CotPositioning | None


@router.get("/institutional", response_model=InstitutionalPositioningOut)
async def get_institutional_positioning(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: Annotated[str, Query(min_length=3, max_length=16)],
) -> InstitutionalPositioningOut:
    """CFTC TFF (4-class + smart-money divergence) + COT (managed-money
    trend) for one asset. Each block is `null` if the asset is not in
    that source's tracked-market map or has no rows (ADR-093 degraded-
    explicit — the dashboard renders an honest empty state)."""
    asset = asset.upper().replace("-", "_")
    # Lazy import : the market maps are the single source of truth in
    # data_pool (anti-doublon) ; importing inside the handler avoids any
    # module-load/circular-import risk against that very large module.
    from ..services.data_pool import _COT_MARKET_BY_ASSET, _TFF_MARKET_BY_ASSET

    tff: TffPositioning | None = None
    tff_market = _TFF_MARKET_BY_ASSET.get(asset)
    if tff_market is not None:
        rows = list(
            (
                await session.execute(
                    select(CftcTffObservation)
                    .where(CftcTffObservation.market_code == tff_market)
                    .order_by(desc(CftcTffObservation.report_date))
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
        if rows:
            cur = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            dealer_net = cur.dealer_long - cur.dealer_short
            am_net = cur.asset_mgr_long - cur.asset_mgr_short
            lev_net = cur.lev_money_long - cur.lev_money_short
            other_net = cur.other_rept_long - cur.other_rept_short
            dealer_dw = am_dw = lev_dw = None
            if prev is not None:
                prev_dealer = prev.dealer_long - prev.dealer_short
                # Trader convention (mirror _section_tff_positioning):
                # positive = longer this week in the trader's own direction.
                dealer_dw = -((prev_dealer) - dealer_net)
                am_dw = am_net - (prev.asset_mgr_long - prev.asset_mgr_short)
                lev_dw = lev_net - (prev.lev_money_long - prev.lev_money_short)
            divergence = lev_net != 0 and am_net != 0 and (lev_net > 0) != (am_net > 0)
            tff = TffPositioning(
                market_code=tff_market,
                report_date=cur.report_date,
                open_interest=cur.open_interest,
                dealer_net=dealer_net,
                asset_mgr_net=am_net,
                lev_money_net=lev_net,
                other_net=other_net,
                dealer_dw=dealer_dw,
                asset_mgr_dw=am_dw,
                lev_money_dw=lev_dw,
                smart_money_divergence=divergence,
            )

    cot: CotPositioning | None = None
    cot_market = _COT_MARKET_BY_ASSET.get(asset)
    if cot_market is not None:
        crows = list(
            (
                await session.execute(
                    select(CotPosition)
                    .where(CotPosition.market_code == cot_market)
                    .order_by(desc(CotPosition.report_date))
                    .limit(13)
                )
            )
            .scalars()
            .all()
        )
        if crows:
            c = crows[0]
            d1 = c.managed_money_net - crows[1].managed_money_net if len(crows) > 1 else None
            d4 = c.managed_money_net - crows[4].managed_money_net if len(crows) > 4 else None
            d12 = c.managed_money_net - crows[12].managed_money_net if len(crows) > 12 else None
            pattern: Literal["accelerating", "reversal", "stable"] = "stable"
            if d1 is not None and d4 is not None:
                if d1 * d4 < 0 and abs(d4) > 5000:
                    pattern = "reversal"
                elif abs(d1) > 0.3 * abs(d4) and abs(d4) > 10_000:
                    pattern = "accelerating"
            cot = CotPositioning(
                market_code=cot_market,
                report_date=c.report_date,
                open_interest=c.open_interest,
                managed_money_net=c.managed_money_net,
                swap_dealer_net=c.swap_dealer_net,
                producer_net=c.producer_net,
                delta_1w=d1,
                delta_4w=d4,
                delta_12w=d12,
                pattern=pattern,
            )

    return InstitutionalPositioningOut(asset=asset, tff=tff, cot=cot)
