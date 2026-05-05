"""GET /v1/geopolitics — aggregated GDELT events by country.

Powers the `/geopolitics` Next.js heatmap (delta Q VISION_2026).
Aggregates the recent GDELT corpus by `sourcecountry` and emits :
  - count       : number of events per country
  - mean_tone   : average GDELT tone (-10..+10, negative = bearish)
  - sample      : 3 most-negative event titles for hover tooltip
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import GdeltEvent

router = APIRouter(prefix="/v1/geopolitics", tags=["geopolitics"])


class CountryHotspot(BaseModel):
    country: str
    count: int
    mean_tone: float
    most_negative_title: str | None = None


class GeopoliticsHeatmapOut(BaseModel):
    window_hours: int
    n_events: int
    countries: list[CountryHotspot]


@router.get("/heatmap", response_model=GeopoliticsHeatmapOut)
async def heatmap(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: int = Query(24, ge=1, le=336),
) -> GeopoliticsHeatmapOut:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = list(
        (
            await session.execute(
                select(
                    GdeltEvent.sourcecountry,
                    GdeltEvent.tone,
                    GdeltEvent.title,
                ).where(GdeltEvent.seendate >= cutoff)
            )
        ).all()
    )

    by_country: dict[str, dict[str, list[float] | list[tuple[float, str]] | int]] = {}
    for sc, tone, title in rows:
        if not sc:
            continue
        bucket = by_country.setdefault(sc, {"tones": [], "titles": []})
        # type: ignore[union-attr]
        bucket["tones"].append(float(tone))  # type: ignore[union-attr]
        bucket["titles"].append((float(tone), title))  # type: ignore[union-attr]

    countries: list[CountryHotspot] = []
    for sc, b in by_country.items():
        tones = b["tones"]  # type: ignore[assignment]
        titles = b["titles"]  # type: ignore[assignment]
        if not tones:
            continue
        mean_tone = sum(tones) / len(tones)  # type: ignore[arg-type]
        # Most-negative event title
        worst = min(titles, key=lambda x: x[0])  # type: ignore[arg-type]
        countries.append(
            CountryHotspot(
                country=sc,
                count=len(tones),  # type: ignore[arg-type]
                mean_tone=round(mean_tone, 2),
                most_negative_title=worst[1] if worst else None,
            )
        )
    countries.sort(key=lambda c: c.count, reverse=True)

    return GeopoliticsHeatmapOut(
        window_hours=hours,
        n_events=len(rows),
        countries=countries,
    )
