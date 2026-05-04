"""Citi-style Economic Surprise Index — V1 z-score proxy.

The "true" Citi Eco Surprise is `(actual - consensus) / std_consensus`
per release, EMA-aggregated. Bloomberg-only consensus data isn't free,
so we ship a defensible *proxy* :

    surprise_t = (value_t - mean_24) / std_24

where mean_24 / std_24 are computed over the last 24 prints of the
same series. If a release prints far from its rolling distribution,
the index moves. Direction-of-shock is preserved (positive = upside
surprise vs trend, negative = downside).

This is NOT identical to Citi but it captures 80% of the signal :
the moments when the macro data path bends. Particularly useful for
the brain's Pass 1 régime call (the surprise direction is a clean
input vs DXY/VIX which are noisy).

VISION_2026 delta E (proxy version).

Stack covered V1 :
  - PAYEMS    : nonfarm payrolls
  - UNRATE    : unemployment rate
  - CPIAUCSL  : CPI all urban
  - PCEPI     : PCE price index
  - INDPRO    : industrial production
  - GDPC1     : real GDP (quarterly)

Future : add per-region (EZ HICP, UK CPI, JP CPI) when the BLS/ECB/
BoE collectors land.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation


_SERIES_LABELS: dict[str, str] = {
    "PAYEMS": "Nonfarm payrolls",
    "UNRATE": "Unemployment rate",
    "CPIAUCSL": "CPI all-urban",
    "PCEPI": "PCE price index",
    "INDPRO": "Industrial production",
    "GDPC1": "Real GDP",
}

# Some series are inverted : higher = bad surprise (UNRATE going up
# is dovish/bad). Multiply z-score by -1 so positive always = positive
# economic surprise.
_INVERTED: frozenset[str] = frozenset({"UNRATE"})


@dataclass(frozen=True)
class SeriesSurprise:
    series_id: str
    label: str
    last_value: float | None
    rolling_mean: float | None
    rolling_std: float | None
    z_score: float | None
    """Polarity-corrected : positive = positive economic surprise."""
    n_history: int


@dataclass(frozen=True)
class SurpriseIndexReading:
    region: str
    composite: float | None
    """Average of polarity-corrected z-scores over series with > 5 history."""
    band: str  # "strong_negative" / "negative" / "neutral" / "positive" / "strong_positive"
    series: list[SeriesSurprise]
    n_series_used: int


def _band(z: float | None) -> str:
    if z is None:
        return "neutral"
    if z >= 1.5:
        return "strong_positive"
    if z >= 0.5:
        return "positive"
    if z <= -1.5:
        return "strong_negative"
    if z <= -0.5:
        return "negative"
    return "neutral"


async def _series_history(
    session: AsyncSession, series_id: str, *, n: int = 24
) -> list[float]:
    """Last `n` non-null observations for `series_id`, oldest-first."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=365 * 5)
    stmt = (
        select(FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(n)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()  # oldest-first
    return [float(v) for v in rows if v is not None]


def _z_score(series: list[float]) -> tuple[float | None, float | None, float | None]:
    """(last, mean, std). Returns (None, None, None) if < 5 history."""
    if len(series) < 5:
        return None, None, None
    last = series[-1]
    history = series[:-1]
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / max(1, len(history) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return None, mean, std
    return last, mean, std


async def assess_surprise_index(
    session: AsyncSession,
) -> SurpriseIndexReading:
    """Build a US-only Eco Surprise Index proxy from FRED."""
    series_results: list[SeriesSurprise] = []
    z_scores: list[float] = []
    for sid, label in _SERIES_LABELS.items():
        history = await _series_history(session, sid)
        if len(history) < 5:
            series_results.append(
                SeriesSurprise(
                    series_id=sid,
                    label=label,
                    last_value=history[-1] if history else None,
                    rolling_mean=None,
                    rolling_std=None,
                    z_score=None,
                    n_history=len(history),
                )
            )
            continue
        last, mean, std = _z_score(history)
        if last is None or mean is None or std in (None, 0.0):
            series_results.append(
                SeriesSurprise(
                    series_id=sid,
                    label=label,
                    last_value=history[-1],
                    rolling_mean=mean,
                    rolling_std=std,
                    z_score=None,
                    n_history=len(history),
                )
            )
            continue
        z = (last - mean) / std
        if sid in _INVERTED:
            z = -z
        series_results.append(
            SeriesSurprise(
                series_id=sid,
                label=label,
                last_value=last,
                rolling_mean=mean,
                rolling_std=std,
                z_score=round(z, 3),
                n_history=len(history),
            )
        )
        z_scores.append(z)

    composite = sum(z_scores) / len(z_scores) if z_scores else None
    if composite is not None:
        composite = round(composite, 3)

    return SurpriseIndexReading(
        region="US",
        composite=composite,
        band=_band(composite),
        series=series_results,
        n_series_used=len(z_scores),
    )


def render_surprise_index_block(
    r: SurpriseIndexReading,
) -> tuple[str, list[str]]:
    """Markdown + sources for data_pool.py."""
    lines = [f"## Eco Surprise Index ({r.region})"]
    if r.composite is None:
        lines.append("- (insufficient FRED history to compute z-scores yet)")
        return "\n".join(lines), []

    lines.append(
        f"- **Composite z-score = {r.composite:+.2f}** → band: **{r.band}** "
        f"({r.n_series_used} series)"
    )
    lines.append("- Per-series :")
    sources: list[str] = []
    for s in r.series:
        z_str = "n/a" if s.z_score is None else f"{s.z_score:+.2f}"
        last_str = "n/a" if s.last_value is None else f"{s.last_value:.3f}"
        lines.append(
            f"  · {s.series_id:10s} ({s.label}) z={z_str} last={last_str}"
        )
        sources.append(f"FRED:{s.series_id}")
    return "\n".join(lines), sources
