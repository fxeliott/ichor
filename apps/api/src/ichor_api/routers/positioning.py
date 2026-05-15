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

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session

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
