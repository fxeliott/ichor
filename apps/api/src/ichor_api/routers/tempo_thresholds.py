"""GET /v1/tempo-thresholds — per-asset tempo classification thresholds.

r126 ADR-099 §Impl(r126) — Mission centrale Axis-7 (auto-amélioration en
autonomie) partial extension. Reads from `tempo_thresholds` (migration 0051,
populated by the weekly cron `ichor-tempo-recalibration.timer` →
`run_tempo_recalibration` CLI). Consumed by the r127 frontend wire in
`<TodaySessionPulse>` (sessionPulse.ts will accept an optional
`thresholdsOverride` and the briefing page will await the fetcher — backend
ships first, wire splits to r127 for confidence on populated data).

Endpoint surface (deliberately minimal — r126 ships the read API surface
that r127 will consume ; historical-trail endpoint deferred to a future
round if/when audit-of-drift becomes a UI surface) :

  - `GET /v1/tempo-thresholds`         → latest per asset, all assets
  - `GET /v1/tempo-thresholds/{asset}` → latest for one asset (404 if absent)

ADR-017 boundary : thresholds are DESCRIPTIVE percentile baselines, never
predictive — they classify today's realized range vs the asset's recent
60-90 day distribution, not predict the next range. The endpoint passes
the calibration metadata through (sample_size + window_days + computed_at)
so the frontend can show staleness honestly (data-honesty per ADR-104).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import TempoThreshold
from ..services.tempo_recalibration import DEFAULT_RECALIBRATION_ASSETS

router = APIRouter(prefix="/v1/tempo-thresholds", tags=["tempo-thresholds"])

_VALID_ASSETS = frozenset(DEFAULT_RECALIBRATION_ASSETS) | {
    # Forward-compat — D1 6th asset (ADR-083) when the route ships.
    "USD_CAD",
}

# Recommend a 5-min public cache + 15-min stale-while-revalidate to the
# downstream Next.js fetch + any intermediary CDN. The cron writes once
# per week — the data is effectively static between fires, so a 5-min
# max-age is comfortably tight. Concordant YELLOW from api-designer + code-
# reviewer ; matches `well_known.py` Cache-Control prior art.
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=900"


class TempoThresholdOut(BaseModel):
    """One per-asset tempo threshold snapshot — the latest row by
    `computed_at DESC` per asset."""

    asset: str = Field(..., description="ADR-083 asset code (underscore-uppercase)")
    breakout_bp: float = Field(..., description="p90 of daily-range bp distribution")
    active_bp: float = Field(..., description="p75 of daily-range bp distribution")
    trending_bp: float = Field(..., description="p50 (median)")
    range_bound_bp: float = Field(..., description="p25")
    sample_size: int = Field(..., description="Number of Paris-days in calibration sample")
    window_days: int = Field(..., description="Rolling window over polygon_intraday")
    computed_at: datetime = Field(..., description="When the cron computed this row")


class TempoThresholdsListOut(BaseModel):
    """Wrapper for the list endpoint — explicit shape for forward-compat
    (paging or summary fields can land without a breaking change)."""

    items: list[TempoThresholdOut]


def _to_out(row: TempoThreshold) -> TempoThresholdOut:
    return TempoThresholdOut(
        asset=row.asset,
        breakout_bp=float(row.breakout_bp),
        active_bp=float(row.active_bp),
        trending_bp=float(row.trending_bp),
        range_bound_bp=float(row.range_bound_bp),
        sample_size=row.sample_size,
        window_days=row.window_days,
        computed_at=row.computed_at,
    )


@router.get("", response_model=TempoThresholdsListOut)
async def list_latest_thresholds(
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> TempoThresholdsListOut:
    """Return the latest tempo threshold row per asset (the row with
    MAX(computed_at) per asset). Empty list if the cron hasn't fired yet
    or no recalibration has been persisted.

    The frontend r127 wire will call this once per briefing render (cached
    by Next.js fetch revalidate ; the per-asset thresholds change weekly
    at most, so a 5-min ISR is comfortable)."""
    # DISTINCT ON (asset) ORDER BY asset, computed_at DESC — Postgres
    # native pattern, single index scan via the
    # `ix_tempo_thresholds_asset_computed_at_desc` index.
    stmt = (
        select(TempoThreshold)
        .distinct(TempoThreshold.asset)
        .order_by(TempoThreshold.asset, desc(TempoThreshold.computed_at))
    )
    rows = (await session.execute(stmt)).scalars().all()
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return TempoThresholdsListOut(items=[_to_out(r) for r in rows])


@router.get("/{asset}", response_model=TempoThresholdOut)
async def get_latest_threshold(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> TempoThresholdOut:
    """Return the latest tempo threshold row for one asset. 400 on unknown
    asset code, 404 if the asset is known but no recalibration row exists
    yet (cron hasn't fired, or asset is in DEFAULT_RECALIBRATION_ASSETS
    but skipped due to sample_size < min_sample_days)."""
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r}",
        )

    stmt = (
        select(TempoThreshold)
        .where(TempoThreshold.asset == asset_norm)
        .order_by(desc(TempoThreshold.computed_at))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no tempo threshold row for asset {asset_norm!r} "
                "(cron has not fired yet or sample_size was below "
                "min_sample_days on the most recent run)"
            ),
        )
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return _to_out(row)
