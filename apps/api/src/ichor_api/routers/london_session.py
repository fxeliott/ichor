"""``GET /v1/london-session/{asset}`` — London-morning read for the NY view (§6.2).

Exposes the owner's CAPITAL §6.2 point as a frontend-pollable endpoint : how the
asset traded during the LONDON MORNING window (08:00-12:00 London local, the
session running before/into the NY open) — open/high/low/close, net change,
direction, and whether it was unusually active vs the typical London morning.
This is the read-side that ``<LondonSessionPanel>`` polls while the briefing
page is visible (mirror ``<StirPanel>`` r192 + ``<PreviousSessionContextPanel>``
r187 + ``/v1/origin-zone/{asset}`` r184 pattern). The Pass-2 LLM already
consumes the same ``load_london_session`` via the data_pool renderer.

**Surface contract** (mirror ``/v1/origin-zone``) :

- 200 OK + ``LondonSessionOut`` when ``load_london_session()`` returns a window
- 404 Not Found when it returns None (no London-morning bars OR window has
  < 30 1-min bars — honest absence per doctrine #11) ; the frontend renders an
  honest « lecture Londres indisponible » state (FX-centric : SPX/NAS London
  windows can be thin/empty)
- 422 when the asset path param is malformed (FastAPI ``Path`` constraint)

**Caching** : ``Cache-Control: private, no-store`` — the read is LIVE state
from rolling ``polygon_intraday`` bars ; the frontend polls every 60s.

**ADR-079 watermark** : ``/v1/london-session`` is PURE FACTUAL data derived from
raw market bars (no LLM emission) → deliberately OUT of the watermark prefix set.

**ADR-017 boundary** : ``direction`` is ``up``/``down``/``range`` — a GEOMETRIC
price-action label for the PREVIOUS/CURRENT London morning, INPUT context for
the trader, NEVER a directional signal for the NY session.

ADR refs : ADR-099 §Impl (this endpoint) ; ADR-017 (boundary) ; ADR-079
(watermark exclusion rationale).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.london_session import LondonSessionRead, load_london_session

router = APIRouter(prefix="/v1/london-session", tags=["london_session"])


class LondonSessionOut(BaseModel):
    """JSON-friendly read-only projection of ``LondonSessionRead``.

    Frozen + ``extra='forbid'`` so a future frontend lockstep CI guard can pin
    the field set (mirror ``OriginZoneOut`` r184 discipline).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    asset: str = Field(min_length=3, max_length=16)
    """Asset code (e.g. ``"EUR_USD"``)."""

    session_date: date
    """London-local date of the summarised morning window."""

    is_today: bool
    """``True`` when the window is today's London morning (live), else a prior
    session — drives the « ce matin (en direct) » vs « dernière séance » label."""

    open_price: float
    high: float
    low: float
    close: float

    range_abs: float = Field(ge=0.0)
    """``high - low`` of the London-morning window."""

    net_change: float
    """``close - open`` — signed (negative = lower into the NY pre-open)."""

    direction: Literal["up", "down", "range"]
    """Geometric direction of the morning. INPUT context, never a NY signal."""

    bar_count: int = Field(ge=30)
    """1-min bars in the window. ``ge=30`` — never emitted below (mirror
    origin-zone Cohen 1988 §3.3 small-sample floor)."""

    avg_range: float | None = None
    """Mean range of up to 5 prior London windows, or None if no baseline."""

    range_ratio: float | None = None
    """``range_abs / avg_range`` — >1.4 ≈ active morning, <0.6 ≈ calm. None
    when no baseline. Frontend turns this into the ACTIVE/CALM activity tag."""

    computed_at_utc: datetime
    """Wall-clock UTC of computation — frontend renders « calculé il y a N min »."""

    provenance: Literal["practitioner_stamp"] = "practitioner_stamp"
    """Honest stamp : the London-morning→NY calibration is a practitioner
    price-action read (Eliot Fathom §6.2), NOT a peer-reviewed academic metric."""


def _project(read: LondonSessionRead, asset: str, now_utc: datetime) -> LondonSessionOut:
    """Pure projection of the internal dataclass to the JSON surface."""
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
        404: {"description": "No London-morning window OR bar_count < 30 (honest absence)"},
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

    Pure read — ``load_london_session`` fetches the last 7 days of
    ``polygon_intraday`` 1-min bars and computes the most-recent
    complete-enough London-morning window (DST-correct). Returns 404 honestly
    when no usable window exists (FX-centric — equity-index London windows can
    be thin/empty).
    """
    now_utc = datetime.now(UTC)
    read = await load_london_session(session, asset, now_utc=now_utc)
    if read is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No London-morning read for asset={asset} : no usable bars in "
                f"the 08:00-12:00 London window OR fewer than 30 1-min bars "
                f"(honest absence per doctrine #11)."
            ),
        )
    response.headers["Cache-Control"] = "private, no-store"
    return _project(read, asset=asset, now_utc=now_utc)
