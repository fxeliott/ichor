"""GET /v1/trade-plan/{asset} — concrete RR plan from a verdict.

Translates the brain's last-known verdict (bias + magnitude pips) into
a concrete entry zone / stop / TP1 / TP3 / TP-extended that respects
Eliot's RR=3 standard with BE at RR=1 and 90% close at RR=3.

Reads :
  - Last bar from `polygon_intraday` for spot
  - Latest `session_card_audit` row for {asset} (any session_type)
    to extract bias + magnitude_pips_low/high + conviction_pct
  - Daily levels (PDH/PDL) for SL sanity warnings

Returns the rendered markdown block + the structured RRPlan fields so
the frontend can format with charts.

VISION_2026 — closes the "I have a verdict, now what's my actual stop
and target?" gap. Pure macro intelligence isn't enough — the trader
needs the operational plan one click away.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import PolygonIntradayBar, SessionCardAudit
from ..services.daily_levels import assess_daily_levels
from ..services.rr_analysis import RRPlan, assess_rr_plan, render_rr_block

router = APIRouter(prefix="/v1/trade-plan", tags=["trade-plan"])


_VALID_ASSET = {
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
    "US100",
    "US30",
}


class TradePlanOut(BaseModel):
    asset: str
    spot: float | None
    bias: Literal["long", "short", "neutral"]
    conviction_pct: float
    magnitude_pips_low: float | None
    magnitude_pips_high: float | None

    entry_zone_low: float | None
    entry_zone_high: float | None
    stop_loss: float | None
    tp1: float | None
    tp3: float | None
    tp_extended: float | None
    risk_pips: float | None
    reward_pips_tp3: float | None
    rr_target: float

    notes: str
    """Warnings about SL placement vs PDH/PDL, low conviction etc."""

    markdown: str
    """Rendered markdown block (the same one fed to the brain)."""

    sources: list[str]

    derived_from: dict[str, str | None] | None = None
    """Provenance — which session card / bar / level source was used."""


def _to_plan_out(
    *,
    asset: str,
    spot: float | None,
    bias: Literal["long", "short", "neutral"],
    conviction_pct: float,
    magnitude_pips_low: float | None,
    magnitude_pips_high: float | None,
    plan: RRPlan,
    md: str,
    sources: list[str],
    derived_from: dict[str, str | None],
) -> TradePlanOut:
    return TradePlanOut(
        asset=asset,
        spot=spot,
        bias=bias,
        conviction_pct=conviction_pct,
        magnitude_pips_low=magnitude_pips_low,
        magnitude_pips_high=magnitude_pips_high,
        entry_zone_low=plan.entry_zone_low,
        entry_zone_high=plan.entry_zone_high,
        stop_loss=plan.stop_loss,
        tp1=plan.tp1,
        tp3=plan.tp3,
        tp_extended=plan.tp_extended,
        risk_pips=plan.risk_pips,
        reward_pips_tp3=plan.reward_pips_tp3,
        rr_target=plan.rr_target,
        notes=plan.notes,
        markdown=md,
        sources=sources,
        derived_from=derived_from,
    )


@router.get("/{asset}", response_model=TradePlanOut)
async def get_trade_plan_from_latest_card(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    rr_target: Annotated[float, Query(ge=1.0, le=10.0)] = 3.0,
) -> TradePlanOut:
    """Build the trade plan from the most recent session card for `asset`.

    If no card exists, returns a neutral plan with `bias=neutral` and
    empty fields. The frontend should surface "no card yet, run --live".
    """
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r} (expected one of {sorted(_VALID_ASSET)})",
        )

    # 1. Latest spot
    last_bar = (
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(PolygonIntradayBar.asset == asset_norm)
                .order_by(desc(PolygonIntradayBar.bar_ts))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    spot = float(last_bar.close) if last_bar is not None else None

    # 2. Latest verdict for the asset (any session_type)
    card = (
        (
            await session.execute(
                select(SessionCardAudit)
                .where(SessionCardAudit.asset == asset_norm)
                .order_by(desc(SessionCardAudit.created_at))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if card is None:
        # No verdict → neutral plan
        plan = assess_rr_plan(
            asset=asset_norm,
            spot=spot,
            bias="neutral",
            conviction_pct=0.0,
            magnitude_pips_low=None,
            magnitude_pips_high=None,
            rr_target=rr_target,
        )
        md, sources = render_rr_block(plan)
        return _to_plan_out(
            asset=asset_norm,
            spot=spot,
            bias="neutral",
            conviction_pct=0.0,
            magnitude_pips_low=None,
            magnitude_pips_high=None,
            plan=plan,
            md=md,
            sources=sources,
            derived_from={"card_id": None, "card_session_type": None},
        )

    # 3. Pull PDH/PDL for SL sanity checks
    levels = await assess_daily_levels(session, asset_norm)

    bias_raw = (card.bias_direction or "neutral").lower()
    if bias_raw not in {"long", "short", "neutral"}:
        bias_raw = "neutral"
    bias = bias_raw  # type: ignore[assignment]

    plan = assess_rr_plan(
        asset=asset_norm,
        spot=spot,
        bias=bias,  # type: ignore[arg-type]
        conviction_pct=float(card.conviction_pct or 0.0),
        magnitude_pips_low=card.magnitude_pips_low,
        magnitude_pips_high=card.magnitude_pips_high,
        pdh=levels.pdh,
        pdl=levels.pdl,
        asian_high=levels.asian_high,
        asian_low=levels.asian_low,
        rr_target=rr_target,
    )
    md, sources = render_rr_block(plan)
    return _to_plan_out(
        asset=asset_norm,
        spot=spot,
        bias=bias,  # type: ignore[arg-type]
        conviction_pct=float(card.conviction_pct or 0.0),
        magnitude_pips_low=card.magnitude_pips_low,
        magnitude_pips_high=card.magnitude_pips_high,
        plan=plan,
        md=md,
        sources=sources,
        derived_from={
            "card_id": str(card.id),
            "card_session_type": card.session_type,
            "card_created_at": card.created_at.isoformat() if card.created_at else None,
        },
    )


class TradePlanIn(BaseModel):
    """Manual override — user supplies the verdict directly."""

    bias: Literal["long", "short", "neutral"]
    conviction_pct: float = Field(ge=0.0, le=100.0)
    magnitude_pips_low: float | None = Field(default=None, ge=0.0)
    magnitude_pips_high: float | None = Field(default=None, ge=0.0)
    rr_target: float = Field(default=3.0, ge=1.0, le=10.0)


@router.post("/{asset}/manual", response_model=TradePlanOut)
async def post_trade_plan_manual(
    asset: str,
    body: TradePlanIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TradePlanOut:
    """Compute a trade plan from explicit user inputs (counterfactual UI)."""
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r}",
        )
    last_bar = (
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(PolygonIntradayBar.asset == asset_norm)
                .order_by(desc(PolygonIntradayBar.bar_ts))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    spot = float(last_bar.close) if last_bar is not None else None
    levels = await assess_daily_levels(session, asset_norm)

    plan = assess_rr_plan(
        asset=asset_norm,
        spot=spot,
        bias=body.bias,
        conviction_pct=body.conviction_pct,
        magnitude_pips_low=body.magnitude_pips_low,
        magnitude_pips_high=body.magnitude_pips_high,
        pdh=levels.pdh,
        pdl=levels.pdl,
        asian_high=levels.asian_high,
        asian_low=levels.asian_low,
        rr_target=body.rr_target,
    )
    md, sources = render_rr_block(plan)
    return _to_plan_out(
        asset=asset_norm,
        spot=spot,
        bias=body.bias,
        conviction_pct=body.conviction_pct,
        magnitude_pips_low=body.magnitude_pips_low,
        magnitude_pips_high=body.magnitude_pips_high,
        plan=plan,
        md=md,
        sources=sources,
        derived_from={"card_id": None, "card_session_type": "manual"},
    )
