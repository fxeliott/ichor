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
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
    "XAU_USD", "NAS100_USD", "SPX500_USD", "US100", "US30",
}


@router.get("/{asset}", response_model=DataPoolOut)
async def get_pool(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataPoolOut:
    """Build the data pool for an asset and return its full payload."""
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r} (expected one of {sorted(_VALID_ASSET)})",
        )
    pool = await build_data_pool(session, asset_norm)
    return DataPoolOut(
        asset=pool.asset,
        generated_at=pool.generated_at,
        markdown_chars=len(pool.markdown),
        sections_emitted=list(pool.sections_emitted),
        sources_count=len(pool.sources),
        sources=list(pool.sources),
        markdown=pool.markdown,
    )
