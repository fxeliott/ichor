"""``GET /v1/origin-zone/{asset}`` — r184 frontend endpoint exposing the
r179 G5 EXECUTION-phase previous-session origin zone classifier.

Per ROADMAP §3 r183-close binding-default : extend r179/r180 backend
arc to the frontend visibility wave. Pass-2 consumer wiring r180 was
the backend-side ; this endpoint is the read-side that the frontend
``<PreviousSessionContextPanel>`` (r185+) will poll every 60s while
the briefing page is visible (Page Visibility API pause/resume,
mirror ``<FreshDataBanner>`` r140 + ``<DxyCorrelationPanel>`` r171b
pattern).

**Surface contract** :

- 200 OK + ``OriginZoneOut`` JSON when ``compute_previous_session_
  origin_zone()`` returns a valid snapshot
- 404 Not Found when classifier returns None (no bars in window OR
  dominant zone bar_count < 30 — honest absence per doctrine #11) ;
  caller renders an honest « contexte indisponible » state
- 422 Unprocessable Entity when asset path param malformed (FastAPI
  Path constraint)
- 500 only on internal DB error (caller retries with exponential backoff)

**Caching policy** : ``Cache-Control: private, no-store`` — the
snapshot is LIVE state derived from rolling 24h polygon_intraday bars.
The frontend polls every 60s, server reads from the indexed bar_ts +
asset PK in O(log n).

**ADR-079 watermark** : the route prefix ``/v1/origin-zone`` does NOT
need to be added to ``AIWatermarkMiddleware`` tagged prefixes
because the response is PURE FACTUAL DATA derived from raw market
bars (no LLM emission). Pure data routes are explicitly excluded
from the watermark per ADR-079.

**ADR-017 boundary** : OriginZoneOut.direction is ``"up"``/``"down"``/
``"range"`` — these are GEOMETRIC/PROBABILISTIC labels for the
PREVIOUS session, NEVER directional bias for the CURRENT session.
The Pydantic class itself is verifier-friendly (frozen, max_length
on string fields) ; the frontend consumer presents this snapshot as
INPUT context not OUTPUT signal.

ADR refs : ADR-099 §Impl(r184) (this endpoint) ; ADR-017 (boundary) ;
ADR-079 (watermark exclusion rationale).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.previous_session_origin_zone import (
    OriginZoneSnapshot,
    compute_previous_session_origin_zone,
)

router = APIRouter(prefix="/v1/origin-zone", tags=["origin_zone"])


class OriginZoneOut(BaseModel):
    """JSON-friendly read-only projection of ``OriginZoneSnapshot``.

    Mirror of the r174 FOUNDATION + r179 EXECUTION dataclass. Frozen
    Pydantic for structural-immutability discipline ; ``extra='forbid'``
    so future r185+ frontend lockstep CI guard can pin field set.

    Why a separate Pydantic vs returning the dataclass directly :
    FastAPI handles dataclasses via fastapi.encoders.jsonable_encoder
    but the response_model field-level documentation (OpenAPI schema)
    is cleaner with Pydantic Field(description=...). Explicit Pydantic
    also ensures forward-compat if the internal ``OriginZoneSnapshot``
    grows extra fields not meant for the frontend surface.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    asset: str = Field(min_length=3, max_length=16)
    """Asset code (e.g. ``"EUR_USD"``)."""

    session_zone: Literal["asian", "london", "ny"]
    """Which session zone dominated the previous 24h window."""

    direction: Literal["up", "down", "range"]
    """Net direction of the dominant move. Geometric/probabilistic
    label NEVER a trade signal for the current session."""

    high_price: float
    """Maximum bar.high observed during the dominant zone window."""

    low_price: float
    """Minimum bar.low observed during the dominant zone window."""

    range_observed: float = Field(ge=0.0)
    """``high_price - low_price`` — pre-computed for frontend convenience
    so consumers don't need to recompute. ``ge=0.0`` enforces sanity."""

    bar_count: int = Field(ge=30)
    """Number of 1-min bars in the dominant zone window. ``ge=30``
    enforced (Cohen 1988 §3.3 small-sample threshold ; snapshot is
    NEVER emitted with fewer)."""

    start_utc: datetime
    """Inclusive UTC start of the dominant zone window."""

    end_utc: datetime
    """Exclusive UTC end of the dominant zone window."""

    computed_at_utc: datetime
    """Wall-clock UTC of the snapshot computation. Frontend renders
    « calculé il y a N min » from this field."""

    provenance: Literal["practitioner_stamp"] = "practitioner_stamp"
    """Honest stamp per Pattern #20 mechanical R59-pre-commit-mandatory.
    The « previous-session origin zone » framing is practitioner-stamp
    (Eliot Fathom transcript §V), NOT peer-reviewed academic concept."""


def _project_snapshot(snapshot: OriginZoneSnapshot, asset: str, now_utc: datetime) -> OriginZoneOut:
    """Pure : project internal ``OriginZoneSnapshot`` dataclass to JSON-
    friendly ``OriginZoneOut`` Pydantic. Computes ``range_observed`` +
    stamps ``computed_at_utc`` for frontend freshness display."""
    return OriginZoneOut(
        asset=asset,
        session_zone=snapshot.session_zone,
        direction=snapshot.direction,
        high_price=snapshot.high_price,
        low_price=snapshot.low_price,
        range_observed=snapshot.high_price - snapshot.low_price,
        bar_count=snapshot.bar_count,
        start_utc=snapshot.start_utc,
        end_utc=snapshot.end_utc,
        computed_at_utc=now_utc,
    )


@router.get(
    "/{asset}",
    response_model=OriginZoneOut,
    responses={
        404: {"description": "No bars in window OR bar_count < 30 (honest absence)"},
        422: {"description": "Asset path param malformed"},
    },
)
async def get_origin_zone(
    response: Response,
    asset: Annotated[
        str,
        Path(
            pattern=r"^[A-Z0-9]{3,8}_[A-Z]{3,8}$|^[A-Z0-9]{3,8}$",
            description="Asset code (e.g., EUR_USD, NAS100_USD, SPX500_USD)",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OriginZoneOut:
    """Return the previous-session origin zone snapshot for ``asset``.

    Pure read endpoint — the snapshot is computed deterministically by
    ``compute_previous_session_origin_zone()`` from the previous 24h
    of ``polygon_intraday`` 1-min bars. Returns 404 honestly when no
    bars are available OR the dominant zone has fewer than 30 bars
    (Cohen 1988 §3.3 small-sample threshold).
    """
    now_utc = datetime.now(UTC)
    snapshot = await compute_previous_session_origin_zone(session, asset=asset, now_utc=now_utc)

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No previous-session origin zone for asset={asset} : "
                f"no bars in [now-24h, now) OR dominant zone has < 30 "
                f"bars (Cohen 1988 §3.3 small-sample threshold). "
                f"Honest absence per doctrine #11."
            ),
        )

    response.headers["Cache-Control"] = "private, no-store"
    return _project_snapshot(snapshot, asset=asset, now_utc=now_utc)
