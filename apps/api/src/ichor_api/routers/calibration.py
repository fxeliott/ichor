"""GET /v1/calibration — public calibration track-record.

Surfaces the Brier reliability of the 4-pass pipeline by asset / session
/ régime / time window. Powers the `/calibration` Next.js page (delta H
of VISION_2026.md, ADR-017 capability #8).

Three responses :
  - GET /v1/calibration            → overall summary + reliability bins
  - GET /v1/calibration/by-asset   → per-asset breakdown
  - GET /v1/calibration/by-regime  → per-régime breakdown
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import SessionCardAudit
from ..services.brier import (
    CalibrationSummary,
    ReliabilityBucket,
    conviction_to_p_up,
    reliability_buckets,
    summarize,
)

router = APIRouter(prefix="/v1/calibration", tags=["calibration"])


# ──────────────────────────── Response shapes ──────────────────────────


class ReliabilityBinOut(BaseModel):
    bin_lower: float
    bin_upper: float
    count: int
    mean_predicted: float
    mean_realized: float


class CalibrationOut(BaseModel):
    n_cards: int
    mean_brier: float
    skill_vs_naive: float
    hits: int
    misses: int
    window_days: int
    asset: str | None = None
    session_type: str | None = None
    regime_quadrant: str | None = None
    reliability: list[ReliabilityBinOut]


class CalibrationGroupOut(BaseModel):
    group_key: str  # e.g. "EUR_USD" or "haven_bid"
    summary: CalibrationOut


class CalibrationGroupsOut(BaseModel):
    groups: list[CalibrationGroupOut]


# ──────────────────────────── Helpers ──────────────────────────────────


async def _fetch_reconciled(
    session: AsyncSession,
    *,
    since: datetime,
    asset: str | None,
    session_type: str | None,
    regime_quadrant: str | None,
) -> list[SessionCardAudit]:
    stmt = (
        select(SessionCardAudit)
        .where(
            SessionCardAudit.realized_at.is_not(None),
            SessionCardAudit.brier_contribution.is_not(None),
            SessionCardAudit.generated_at >= since,
        )
    )
    if asset:
        stmt = stmt.where(SessionCardAudit.asset == asset.upper())
    if session_type:
        stmt = stmt.where(SessionCardAudit.session_type == session_type)
    if regime_quadrant:
        stmt = stmt.where(SessionCardAudit.regime_quadrant == regime_quadrant)
    return list((await session.execute(stmt)).scalars().all())


def _summary_to_out(
    summary: CalibrationSummary,
    bins: list[ReliabilityBucket],
    *,
    window_days: int,
    asset: str | None,
    session_type: str | None,
    regime_quadrant: str | None,
) -> CalibrationOut:
    return CalibrationOut(
        n_cards=summary.n_cards,
        mean_brier=summary.mean_brier,
        skill_vs_naive=summary.skill_vs_naive,
        hits=summary.hits,
        misses=summary.misses,
        window_days=window_days,
        asset=asset,
        session_type=session_type,
        regime_quadrant=regime_quadrant,
        reliability=[
            ReliabilityBinOut(
                bin_lower=b.bin_lower,
                bin_upper=b.bin_upper,
                count=b.count,
                mean_predicted=b.mean_predicted,
                mean_realized=b.mean_realized,
            )
            for b in bins
        ],
    )


def _aggregate(
    cards: list[SessionCardAudit],
) -> tuple[CalibrationSummary, list[ReliabilityBucket]]:
    """Compute summary + reliability from reconciled cards.

    `realized_outcome` (1 if up, else 0) is derived from
    realized_close_session vs the first bar's open. We approximate
    the open via realized_low_session being a lower bound and use the
    bias direction's predicted outcome match : a long card whose
    Brier was 0 means y=1, brier=1 means y=0. The math :
    Brier = (P_up - y)^2  →  y = round(P_up - sqrt(Brier))  if direction-correct,
                              y = round(P_up + sqrt(Brier))  otherwise.
    Cleaner approach : recompute P_up from (bias, conviction) and
    invert to recover y exactly (y is 0 or 1).
    """
    p_ups: list[float] = []
    ys: list[int] = []
    brier_contribs: list[float] = []
    direction_hits: list[int] = []
    for c in cards:
        if c.brier_contribution is None:
            continue
        bias = c.bias_direction
        if bias not in ("long", "short", "neutral"):
            continue
        p = conviction_to_p_up(bias, c.conviction_pct)  # type: ignore[arg-type]
        # Invert : y minimizes Brier → y = 1 if (1-p)^2 < (0-p)^2 i.e. p > 0.5
        # given the recorded brier; pick the y that matches the recorded brier.
        # candidate y=1 → brier (p-1)^2 ; candidate y=0 → brier p^2.
        candidates = {0: (p - 0) ** 2, 1: (p - 1) ** 2}
        y = min(candidates, key=lambda k: abs(candidates[k] - c.brier_contribution))
        p_ups.append(p)
        ys.append(y)
        brier_contribs.append(c.brier_contribution)
        # direction hit : forecast went the right way
        forecast_up = p > 0.5
        actually_up = y == 1
        direction_hits.append(1 if forecast_up == actually_up else 0)
    summary = summarize(brier_contribs, direction_hits)
    bins = reliability_buckets(p_ups, ys, n_bins=10)
    return summary, bins


# ──────────────────────────── Routes ───────────────────────────────────


@router.get("", response_model=CalibrationOut)
async def calibration_overall(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: str | None = Query(None, max_length=16),
    session_type: str | None = Query(None, regex=r"^(pre_londres|pre_ny|event_driven)$"),
    regime_quadrant: str | None = Query(
        None,
        regex=r"^(haven_bid|funding_stress|goldilocks|usd_complacency)$",
    ),
    window_days: int = Query(90, ge=1, le=730),
) -> CalibrationOut:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    cards = await _fetch_reconciled(
        session,
        since=since,
        asset=asset,
        session_type=session_type,
        regime_quadrant=regime_quadrant,
    )
    summary, bins = _aggregate(cards)
    return _summary_to_out(
        summary,
        bins,
        window_days=window_days,
        asset=asset,
        session_type=session_type,
        regime_quadrant=regime_quadrant,
    )


@router.get("/by-asset", response_model=CalibrationGroupsOut)
async def calibration_by_asset(
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: int = Query(90, ge=1, le=730),
) -> CalibrationGroupsOut:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    cards = await _fetch_reconciled(
        session, since=since, asset=None, session_type=None, regime_quadrant=None
    )
    by_asset: dict[str, list[SessionCardAudit]] = {}
    for c in cards:
        by_asset.setdefault(c.asset, []).append(c)
    groups: list[CalibrationGroupOut] = []
    for asset, asset_cards in sorted(by_asset.items()):
        summary, bins = _aggregate(asset_cards)
        groups.append(
            CalibrationGroupOut(
                group_key=asset,
                summary=_summary_to_out(
                    summary,
                    bins,
                    window_days=window_days,
                    asset=asset,
                    session_type=None,
                    regime_quadrant=None,
                ),
            )
        )
    return CalibrationGroupsOut(groups=groups)


@router.get("/by-regime", response_model=CalibrationGroupsOut)
async def calibration_by_regime(
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: int = Query(90, ge=1, le=730),
) -> CalibrationGroupsOut:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    cards = await _fetch_reconciled(
        session, since=since, asset=None, session_type=None, regime_quadrant=None
    )
    by_regime: dict[str, list[SessionCardAudit]] = {}
    for c in cards:
        key = c.regime_quadrant or "unknown"
        by_regime.setdefault(key, []).append(c)
    groups: list[CalibrationGroupOut] = []
    for regime, regime_cards in sorted(by_regime.items()):
        summary, bins = _aggregate(regime_cards)
        groups.append(
            CalibrationGroupOut(
                group_key=regime,
                summary=_summary_to_out(
                    summary,
                    bins,
                    window_days=window_days,
                    asset=None,
                    session_type=None,
                    regime_quadrant=regime if regime != "unknown" else None,
                ),
            )
        )
    return CalibrationGroupsOut(groups=groups)
