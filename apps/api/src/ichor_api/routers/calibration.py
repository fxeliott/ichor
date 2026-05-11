"""GET /v1/calibration — public calibration track-record.

Surfaces the Brier reliability of the 4-pass pipeline by asset / session
/ régime / time window. Powers the `/calibration` Next.js page (delta H
of VISION_2026.md, ADR-017 capability #8).

Four responses :
  - GET /v1/calibration            → overall summary + reliability bins
  - GET /v1/calibration/by-asset   → per-asset breakdown
  - GET /v1/calibration/by-regime  → per-régime breakdown
  - GET /v1/calibration/scoreboard → multi-window matrix (asset × session_type)
                                     for trader-grade UI (W101, ADR-082/083)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import SessionCardAudit
from ..services.brier import (
    CalibrationSummary,
    ReliabilityBucket,
    reliability_buckets,
    summarize,
)
from ..services.brier_optimizer import derive_realized_outcome
from ._session_type import SESSION_TYPE_REGEX

router = APIRouter(prefix="/v1/calibration", tags=["calibration"])

# W101e — `_VALID_SESSION_TYPES` + `_SESSION_TYPE_RE` extracted to
# `_session_type.py` (shared between calibration.py + sessions.py) per
# code-review H2 finding : previous version was duplicated in both
# routers, with sessions.py hardcoded to 3 windows while calibration.py
# (post-W101) was already at 5. This re-fragmentation now closes the
# drift permanently.
_SESSION_TYPE_RE = SESSION_TYPE_REGEX


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


# W101 — scoreboard shapes : multi-window matrix (asset × session_type)
# for the trader-grade Living Analysis View (ADR-083 D4).


class ScoreboardCellOut(BaseModel):
    """One (asset, session_type) cell at a given rolling window."""

    asset: str
    session_type: str
    n_cards: int
    """Count of reconciled cards (with brier_contribution non-null)."""
    mean_brier: float
    skill_vs_naive: float
    """skill = mean_brier(naive) - mean_brier(model). >0 = beats coin-flip."""
    hits: int
    misses: int


class ScoreboardWindowOut(BaseModel):
    """All cells for one rolling window (e.g. last 30 days)."""

    window_label: str  # "30d" | "90d" | "all"
    window_days: int  # numeric days for filtering UI
    n_cells: int  # convenience : len(cells)
    cells: list[ScoreboardCellOut]


class ScoreboardOut(BaseModel):
    """Top-level scoreboard response : multi-window matrix.

    UI consumes : windows[0..N], each window has cells[0..M] of
    (asset, session_type) cell summaries. Empty cells (no reconciled
    cards in window) are OMITTED, not zero-filled — the UI fills the
    matrix gaps from the Cartesian product.
    """

    generated_at: datetime
    windows: list[ScoreboardWindowOut]


# ──────────────────────────── Helpers ──────────────────────────────────


async def _fetch_reconciled(
    session: AsyncSession,
    *,
    since: datetime,
    asset: str | None,
    session_type: str | None,
    regime_quadrant: str | None,
) -> list[SessionCardAudit]:
    stmt = select(SessionCardAudit).where(
        SessionCardAudit.realized_at.is_not(None),
        SessionCardAudit.brier_contribution.is_not(None),
        SessionCardAudit.generated_at >= since,
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

    W101e — code-review H1 fix : delegated y-recovery to
    `services.brier_optimizer.derive_realized_outcome` (single source).
    Pre-W101e, this function re-implemented the inversion math locally
    with a subtle bug : neutral cards (bias_direction='neutral', p_up=0.5)
    have identical Brier contributions for y=0 and y=1, so the original
    `min(candidates, key=abs(...))` always defaulted to y=0, polluting
    `hits/misses` with directionally-meaningless rows.

    The canonical helper returns None on neutral cards (and on any case
    where the two y candidates are equidistant within tolerance). We
    skip those rows entirely — they carry zero directional signal.
    """
    from ..services.brier import conviction_to_p_up

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
        y = derive_realized_outcome(bias, c.conviction_pct, c.brier_contribution)
        if y is None:
            # Neutral cards (p_up = 0.5) carry no directional information ;
            # skipping them is the documented invariant (brier_optimizer.py
            # L266-267) so the summary doesn't mis-credit neutral rows
            # as hits or misses.
            continue
        p = conviction_to_p_up(bias, c.conviction_pct)  # type: ignore[arg-type]
        p_ups.append(p)
        ys.append(y)
        brier_contribs.append(c.brier_contribution)
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
    session_type: str | None = Query(None, regex=_SESSION_TYPE_RE),
    regime_quadrant: str | None = Query(
        None,
        regex=r"^(haven_bid|funding_stress|goldilocks|usd_complacency)$",
    ),
    window_days: int = Query(90, ge=1, le=730),
) -> CalibrationOut:
    since = datetime.now(UTC) - timedelta(days=window_days)
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
    since = datetime.now(UTC) - timedelta(days=window_days)
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
    since = datetime.now(UTC) - timedelta(days=window_days)
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


# ──────────────────────────── W101 — Scoreboard ─────────────────────────


def _parse_window(label: str) -> int | None:
    """Parse one window label into days. Returns None if invalid.

    Accepted formats : "30d", "90d", "365d", "all" (== 730 d cap).
    Days hard-capped to [1, 730] to match `window_days` Query param of
    the existing routes (same range to avoid surprise).
    """
    if label == "all":
        return 730
    if not label.endswith("d"):
        return None
    head = label[:-1]
    if not head.isdigit():
        return None
    n = int(head)
    if n < 1 or n > 730:
        return None
    return n


@router.get("/scoreboard", response_model=ScoreboardOut)
async def calibration_scoreboard(
    session: Annotated[AsyncSession, Depends(get_session)],
    windows: list[str] = Query(default=["30d", "90d", "all"]),
) -> ScoreboardOut:
    """Multi-window scoreboard for trader-grade Living Analysis View.

    For each requested rolling window, returns a per-cell summary
    keyed by `(asset, session_type)`. The default 3 windows
    `30d / 90d / all` mirror what a trader expects when sanity-checking
    a calibration trend.

    Cells with zero reconciled cards in a window are omitted (UI
    responsible for filling Cartesian gaps).

    Errors :
        400 if all `windows` query values are invalid (none parse).
    """
    parsed: list[tuple[str, int]] = []
    for raw in windows:
        days = _parse_window(raw)
        if days is not None:
            parsed.append((raw, days))
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail=(
                "no valid windows ; expected list of 'Nd' (1<=N<=730) "
                "or 'all', got: " + repr(windows)
            ),
        )

    now = datetime.now(UTC)
    out_windows: list[ScoreboardWindowOut] = []
    for label, days in parsed:
        since = now - timedelta(days=days)
        cards = await _fetch_reconciled(
            session,
            since=since,
            asset=None,
            session_type=None,
            regime_quadrant=None,
        )
        buckets: dict[tuple[str, str], list[SessionCardAudit]] = {}
        for c in cards:
            if c.asset and c.session_type:
                buckets.setdefault((c.asset, c.session_type), []).append(c)

        cells: list[ScoreboardCellOut] = []
        for (asset, st), gcards in sorted(buckets.items()):
            summary, _ = _aggregate(gcards)
            cells.append(
                ScoreboardCellOut(
                    asset=asset,
                    session_type=st,
                    n_cards=summary.n_cards,
                    mean_brier=summary.mean_brier,
                    skill_vs_naive=summary.skill_vs_naive,
                    hits=summary.hits,
                    misses=summary.misses,
                )
            )
        out_windows.append(
            ScoreboardWindowOut(
                window_label=label,
                window_days=days,
                n_cells=len(cells),
                cells=cells,
            )
        )

    return ScoreboardOut(generated_at=now, windows=out_windows)
