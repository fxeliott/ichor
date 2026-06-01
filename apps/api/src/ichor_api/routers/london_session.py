"""``GET /v1/london-session/{asset}`` — §6.2 frontend endpoint exposing the
London-morning read that calibrates the upcoming NY session.

The owner's CAPITAL point (§6.2) : read how the asset traded during the
LONDON MORNING (08:00–12:00 London local, the session running before / into
the NY open) to inform the NY-session view. The backend
``services/london_session.py`` already feeds this into the Pass-2 prompt
(``_section_london_session``) ; this endpoint is the read-side that the
frontend ``<LondonSessionPanel>`` polls every 60s while the briefing page is
visible (Page Visibility API pause/resume, mirror ``<FreshDataBanner>`` r140 +
``<PreviousSessionContextPanel>`` r184 pattern).

**Surface contract** :

- 200 OK + ``LondonSessionOut`` JSON when ``compute_london_session_for_asset()``
  returns a usable London-morning read
- 404 Not Found when it returns None (no London bars in the last 7d OR the
  most-recent window has < 30 bars — honest absence per doctrine #11) ; caller
  renders an honest « lecture Londres indisponible » state
- 422 Unprocessable Entity when the asset path param is malformed
- 500 only on internal DB error (caller retries with exponential backoff)

**Caching policy** : ``Cache-Control: private, no-store`` — the read is LIVE
state derived from rolling ``polygon_intraday`` bars (the London morning is
in-progress / just closed). The frontend polls every 60s.

**ADR-079 watermark** : the route prefix ``/v1/london-session`` does NOT need to
be added to ``AIWatermarkMiddleware`` tagged prefixes — the response is PURE
FACTUAL DATA derived from raw market bars (no LLM emission). Pure data routes
are explicitly excluded from the watermark.

**ADR-017 boundary** : ``LondonSessionOut.direction`` is ``"up"`` / ``"down"`` /
``"range"`` — a GEOMETRIC label for how the LONDON MORNING traded, NEVER a
directional bias for the upcoming NY session. The snapshot is INPUT context the
frontend presents as calibration, not an OUTPUT trade signal.

ADR refs : ADR-017 (boundary) ; ADR-079 (watermark exclusion rationale).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.london_session import (
    LondonSessionRead,
    compute_london_session_for_asset,
)

router = APIRouter(prefix="/v1/london-session", tags=["london_session"])


class LondonSessionOut(BaseModel):
    """JSON-friendly read-only projection of ``LondonSessionRead``.

    Frozen Pydantic for structural-immutability discipline ; ``extra='forbid'``
    so a future frontend lockstep CI guard can pin the field set. Mirrors the
    r184 ``OriginZoneOut`` projection pattern.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    asset: str = Field(min_length=3, max_length=16)
    """Asset code (e.g. ``"EUR_USD"``)."""

    session_date: date
    """London-local date of the read window (today when live, else the last
    usable London morning)."""

    is_today: bool
    """``True`` when the window is today's London morning (« en direct, ce
    matin ») — the frontend renders a live vs last-session badge from this."""

    open_price: float
    """Open of the London-morning window (first bar)."""

    high: float
    """Highest bar.high in the window."""

    low: float
    """Lowest bar.low in the window."""

    close: float
    """Close of the window (last bar) — live mid when the morning is in
    progress, settle when complete."""

    range_abs: float = Field(ge=0.0)
    """``high - low`` — the morning's traded range."""

    net_change: float
    """``close - open_price`` — signed move across the window (sign is
    descriptive, NEVER a bias)."""

    direction: Literal["up", "down", "range"]
    """Body/range ≥ 0.3 directional read of the London morning. Geometric
    label for the PRIOR window, NEVER a signal for the NY session."""

    bar_count: int = Field(ge=30)
    """1-min bars in the window. ``ge=30`` enforced (the read is never emitted
    with fewer — small-sample floor)."""

    avg_range: float | None = None
    """Average range of up to 5 prior London windows, or ``None`` when there is
    no prior-window baseline yet."""

    range_ratio: float | None = Field(default=None, ge=0.0)
    """``range_abs / avg_range`` — today's activity vs the typical London
    morning. ``> 1.4`` ≈ active, ``< 0.6`` ≈ calm. ``None`` when no baseline."""

    computed_at_utc: datetime
    """Wall-clock UTC of the computation. Frontend renders « calculé il y a N
    min » from this field."""

    provenance: Literal["practitioner_stamp"] = "practitioner_stamp"
    """The « London-morning read » framing is practitioner-stamp (Eliot Fathom
    §6.2 methodology), NOT a peer-reviewed academic concept."""


def _project_read(read: LondonSessionRead, asset: str, now_utc: datetime) -> LondonSessionOut:
    """Pure : project the internal ``LondonSessionRead`` dataclass to the
    JSON-friendly ``LondonSessionOut`` Pydantic, stamping ``asset`` and
    ``computed_at_utc`` for the frontend freshness display."""
    return LondonSessionOut(
        asset=asset,
        session_date=read.session_date,
        is_today=read.is_today,
        open_price=read.open_price,
        high=read.high,
        low=read.low,
        close=read.close,
        range_abs=read.range_abs,
        net_change=read.net_change,
        direction=read.direction,
        bar_count=read.bar_count,
        avg_range=read.avg_range,
        range_ratio=read.range_ratio,
        computed_at_utc=now_utc,
    )


@router.get(
    "/{asset}",
    response_model=LondonSessionOut,
    responses={
        404: {"description": "No usable London-morning window (honest absence)"},
        422: {"description": "Asset path param malformed"},
    },
)
async def get_london_session(
    response: Response,
    asset: Annotated[
        str,
        Path(
            pattern=r"^[A-Z0-9]{3,8}_[A-Z]{3,8}$|^[A-Z0-9]{3,8}$",
            description="Asset code (e.g., EUR_USD, NAS100_USD, SPX500_USD)",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LondonSessionOut:
    """Return the London-morning read for ``asset``.

    Pure read endpoint — the read is computed deterministically by
    ``compute_london_session_for_asset()`` from the last 7d of
    ``polygon_intraday`` 1-min bars (DST-correct London window via ZoneInfo).
    Returns 404 honestly when no usable London window exists (no bars OR the
    most-recent window has fewer than 30 bars — small-sample floor).
    """
    now_utc = datetime.now(UTC)
    read = await compute_london_session_for_asset(session, asset, now_utc=now_utc)

    if read is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No usable London-morning read for asset={asset} : no "
                f"polygon_intraday bars in the last 7d OR the most-recent "
                f"London window has < 30 bars (small-sample floor). Honest "
                f"absence per doctrine #11."
            ),
        )

    response.headers["Cache-Control"] = "private, no-store"
    return _project_read(read, asset=asset, now_utc=now_utc)
