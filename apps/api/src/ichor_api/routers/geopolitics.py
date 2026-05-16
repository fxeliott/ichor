"""GET /v1/geopolitics — aggregated GDELT events by country.

Powers the `/geopolitics` Next.js heatmap (delta Q VISION_2026).
Aggregates the recent GDELT corpus by `sourcecountry` and emits :
  - count       : number of events per country
  - mean_tone   : average GDELT tone (-10..+10, negative = bearish)
  - sample      : 3 most-negative event titles for hover tooltip
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import GdeltEvent, GprObservation

router = APIRouter(prefix="/v1/geopolitics", tags=["geopolitics"])

# AI-GPR (Caldara & Iacoviello) is normalised so 100 = the 1985-2019
# mean. Bands are expressed strictly as a ratio to that PUBLISHED
# baseline — no fabricated academic thresholds (anti-hallucination).
_GPR_BASELINE = 100.0


def _gpr_band(value: float) -> str:
    r = value / _GPR_BASELINE
    if r < 0.8:
        return "bas"
    if r < 1.3:
        return "normal"
    if r < 2.2:
        return "élevé"
    return "très élevé"


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


# ─── /briefing : AI-GPR headline + most-negative GDELT (briefing panel) ───
# Mirrors services/data_pool.py:_section_geopolitics so the /briefing
# dashboard surfaces the SAME geopolitical read the 4-pass LLM sees
# (ADR-099 Tier 1.2). Read-only, ADR-017-safe (pure risk description).


class GprReading(BaseModel):
    value: float
    observation_date: date
    as_of_days: int  # staleness vs today (GPR source lags a few days)
    band: str  # bas | normal | élevé | très élevé — ratio to base 100
    baseline: float = _GPR_BASELINE


class GdeltNegative(BaseModel):
    tone: float
    title: str
    domain: str | None = None
    query_label: str | None = None
    url: str | None = None


class GeopoliticsBriefingOut(BaseModel):
    gpr: GprReading | None
    gdelt_window_hours: int
    n_events_window: int
    gdelt_negatives: list[GdeltNegative]


@router.get("/briefing", response_model=GeopoliticsBriefingOut)
async def briefing(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: int = Query(24, ge=1, le=168),
    top: int = Query(5, ge=1, le=20),
) -> GeopoliticsBriefingOut:
    gpr_row = (
        (
            await session.execute(
                select(GprObservation).order_by(desc(GprObservation.observation_date)).limit(1)
            )
        )
        .scalars()
        .first()
    )

    gpr: GprReading | None = None
    if gpr_row is not None:
        gpr = GprReading(
            value=round(float(gpr_row.ai_gpr), 1),
            observation_date=gpr_row.observation_date,
            as_of_days=(datetime.now(UTC).date() - gpr_row.observation_date).days,
            band=_gpr_band(float(gpr_row.ai_gpr)),
        )

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = list(
        (await session.execute(select(GdeltEvent).where(GdeltEvent.seendate >= cutoff)))
        .scalars()
        .all()
    )
    negatives = sorted(rows, key=lambda r: r.tone)[:top]

    return GeopoliticsBriefingOut(
        gpr=gpr,
        gdelt_window_hours=hours,
        n_events_window=len(rows),
        gdelt_negatives=[
            GdeltNegative(
                tone=round(float(r.tone), 1),
                title=r.title,
                domain=r.domain,
                query_label=r.query_label,
                url=r.url,
            )
            for r in negatives
        ],
    )
