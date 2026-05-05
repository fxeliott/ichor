"""GET /v1/data-pool/{asset} — debug view of what the brain sees.

Returns the exact markdown + sources list that `build_data_pool()`
assembles for an asset, so Eliot can sanity-check what's flowing
into the 4-pass pipeline without running --live.

VISION_2026 — operator transparency tool.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.data_pool import build_data_pool

router = APIRouter(prefix="/v1/data-pool", tags=["data-pool"])


class DataPoolOut(BaseModel):
    asset: str
    generated_at: datetime
    markdown_chars: int
    sections_emitted: list[str]
    sources_count: int
    sources: list[str]
    markdown: str


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


_VALID_SESSION_TYPES = {
    "pre_londres",
    "pre_ny",
    "ny_mid",
    "ny_close",
    "event_driven",
}
_VALID_REGIMES = {
    "haven_bid",
    "funding_stress",
    "goldilocks",
    "usd_complacency",
}


@router.get("/{asset}", response_model=DataPoolOut)
async def get_pool(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_type: str | None = None,
    regime: str | None = None,
    conviction_pct: float = 50.0,
) -> DataPoolOut:
    """Build the data pool for an asset and return its full payload.

    Optional query params let the caller request the
    `session_scenarios` preview block :
      - `session_type` ∈ pre_londres / pre_ny / ny_mid / ny_close / event_driven
      - `regime` ∈ haven_bid / funding_stress / goldilocks / usd_complacency
      - `conviction_pct` (0-100) — defaults to 50 (neutral preview)

    Without `session_type`, the scenarios block is skipped.
    """
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r} (expected one of {sorted(_VALID_ASSET)})",
        )
    if session_type is not None and session_type not in _VALID_SESSION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unknown session_type {session_type!r} "
                f"(expected one of {sorted(_VALID_SESSION_TYPES)})"
            ),
        )
    if regime is not None and regime not in _VALID_REGIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"unknown regime {regime!r} (expected one of {sorted(_VALID_REGIMES)})"),
        )
    pool = await build_data_pool(
        session,
        asset_norm,
        session_type=session_type,  # type: ignore[arg-type]
        regime=regime,  # type: ignore[arg-type]
        conviction_pct=conviction_pct,
    )
    return DataPoolOut(
        asset=pool.asset,
        generated_at=pool.generated_at,
        markdown_chars=len(pool.markdown),
        sections_emitted=list(pool.sections_emitted),
        sources_count=len(pool.sources),
        sources=list(pool.sources),
        markdown=pool.markdown,
    )
