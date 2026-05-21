"""GET /v1/geopolitics — aggregated GDELT events by country.

Powers the `/geopolitics` Next.js heatmap (delta Q VISION_2026).
Aggregates the recent GDELT corpus by `sourcecountry` and emits :
  - count       : number of events per country
  - mean_tone   : average GDELT tone (-10..+10, negative = bearish)
  - sample      : 3 most-negative event titles for hover tooltip

r138 — `/v1/geopolitics/briefing` accepts an optional `?asset=` query
param (5 priority assets + 4 legacy) and narrows the top-N most-
negative GDELT events to those whose title / query_label / URL match
the asset's keyword affinity (cf `services/asset_news_affinity.py`).
The scarce-fallback rule mirrors `/v1/news` : below `_MIN_ASSET_MATCHES`
asset-matching negatives we fall back to the global ranking and surface
`filter.applied=False` honestly. AI-GPR is asset-agnostic by nature
(a single global risk index) and is always returned unchanged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import GdeltEvent, GprObservation
from ..services.asset_news_affinity import (
    NEWS_KEYWORDS,
    filter_rows_by_asset_affinity,
)

router = APIRouter(prefix="/v1/geopolitics", tags=["geopolitics"])

# AI-GPR (Caldara & Iacoviello) is normalised so 100 = the 1985-2019
# mean. Bands are expressed strictly as a ratio to that PUBLISHED
# baseline — no fabricated academic thresholds (anti-hallucination).
_GPR_BASELINE = 100.0

# r138 — same threshold as /v1/news for filter discipline consistency.
_MIN_ASSET_MATCHES = 3
# r138 — pull a wider candidate pool for GDELT when filtering so the
# keyword filter has options before we pick the top-N most-negative.
_FILTER_FETCH_MULTIPLIER = 8
_FILTER_MAX_FETCH = 500
_ASSET_REGEX = r"^[A-Z0-9_]{3,16}$"


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
# r138 adds optional `?asset=` filter for per-asset narrative relevance.


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


class GeopoliticsFilterMeta(BaseModel):
    """r138 — asset-filter disclosure for the GDELT negatives ranking.

    AI-GPR is global by construction (single index) and is unaffected
    by the filter. The `applied=False` case (matched < min_required)
    means the negatives list is the GLOBAL ranking — the frontend
    should disclose the fallback honestly.
    """

    asset: str
    matched: int
    applied: bool
    min_required: int = _MIN_ASSET_MATCHES
    known_asset: bool = True


class GeopoliticsBriefingOut(BaseModel):
    gpr: GprReading | None
    gdelt_window_hours: int
    n_events_window: int
    gdelt_negatives: list[GdeltNegative]
    # r138 — disclosed asset-filter status. `None` for back-compat when
    # `?asset=` is not supplied.
    filter: GeopoliticsFilterMeta | None = None


@router.get("/briefing", response_model=GeopoliticsBriefingOut)
async def briefing(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: int = Query(24, ge=1, le=168),
    top: int = Query(5, ge=1, le=20),
    asset: str | None = Query(None, pattern=_ASSET_REGEX),
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
    # r138 — when filtering by asset, pull a wider candidate pool so the
    # keyword filter has options before we pick the top-N most-negative.
    # The pool is ordered by tone-ascending up to `_FILTER_MAX_FETCH`,
    # filtered, then re-ranked. Without `asset=`, behaviour matches
    # the r137 query (top-N most-negative across the whole window).
    base_stmt = (
        select(GdeltEvent).where(GdeltEvent.seendate >= cutoff).order_by(GdeltEvent.tone.asc())
    )
    if asset:
        pool_cap = min(
            _FILTER_MAX_FETCH, max(top * _FILTER_FETCH_MULTIPLIER, _MIN_ASSET_MATCHES * 8)
        )
        rows = list((await session.execute(base_stmt.limit(pool_cap))).scalars().all())
    else:
        rows = list((await session.execute(base_stmt.limit(top))).scalars().all())

    # Window total (for context disclosure) — count of ALL events in
    # window (NOT limited to the candidate pool above — this is what
    # the panel surfaces as "GDELT · N events / Wh"). r138 preserves
    # the r137 semantics : the count is the full window cardinality,
    # independent of the asset filter or the candidate-pool cap.
    n_events_window = int(
        (
            await session.execute(
                select(func.count()).select_from(GdeltEvent).where(GdeltEvent.seendate >= cutoff)
            )
        ).scalar()
        or 0
    )

    filter_meta: GeopoliticsFilterMeta | None = None
    if asset:
        asset_uc = asset.upper()
        known = asset_uc in NEWS_KEYWORDS

        def _gd_key(r: GdeltEvent) -> tuple[str, str]:
            # r138 — match against title PLUS query_label (collector-side
            # topic tag) PLUS URL ; query_label often carries semantic
            # tags like "iran-conflict" or "china-tariff" that boost
            # asset-affinity precision over title-only.
            blob = " ".join([r.title or "", r.query_label or "", r.domain or ""])
            return blob, r.url or ""

        filtered_rows, matched, applied = filter_rows_by_asset_affinity(
            rows,
            asset_uc,
            key=_gd_key,
            min_required=_MIN_ASSET_MATCHES,
        )
        negatives_rows = sorted(filtered_rows, key=lambda r: r.tone)[:top]
        filter_meta = GeopoliticsFilterMeta(
            asset=asset_uc,
            matched=matched,
            applied=applied,
            min_required=_MIN_ASSET_MATCHES,
            known_asset=known,
        )
    else:
        negatives_rows = rows[:top]

    return GeopoliticsBriefingOut(
        gpr=gpr,
        gdelt_window_hours=hours,
        n_events_window=n_events_window,
        gdelt_negatives=[
            GdeltNegative(
                tone=round(float(r.tone), 1),
                title=r.title,
                domain=r.domain,
                query_label=r.query_label,
                url=r.url,
            )
            for r in negatives_rows
        ],
        filter=filter_meta,
    )
