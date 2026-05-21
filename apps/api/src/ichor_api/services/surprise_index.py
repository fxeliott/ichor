"""Citi-style Economic Surprise Index — period-CHANGE z-score proxy (r135).

The "true" Citi Eco Surprise is `(actual - consensus) / std_consensus`
per release, EMA-aggregated. Bloomberg-only consensus data isn't free,
so we ship a defensible *proxy*.

r135 METHODOLOGY FIX (transcript + web-research grounded). The original
proxy z-scored the raw LEVEL :

    surprise_t = (level_t - mean_24_levels) / std_24_levels   # OLD — weak

For a TRENDING series (CPI index 332→335→338..., PAYEMS total payrolls,
real GDP) the latest level is almost always the highest in the window, so
the level z-score is dominated by the secular trend and pins at ~+1.7
every month regardless of whether the print actually surprised. That is
not a "surprise" — it is "the line goes up". The honest standardized-
surprise proxy z-scores the PERIOD-OVER-PERIOD CHANGE instead :

    Δ_t        = level_t - level_{t-1}                 # the period change
    surprise_t = (Δ_t - mean(prior Δ)) / std(prior Δ)  # NEW — r135

This matches how these series are actually reported + reacted to (NFP =
jobs ADDED = the change ; CPI MoM = the change ≈ inflation ; ΔUNRATE =
the move). A print only registers when its CHANGE breaks the series'
own change-distribution — the macro "data path bends" signal the brain's
Pass-1 régime call wants. (This is the closest free analogue of the Citi
"actual vs the distribution of expectations" idea the macro-desk method
teaches : the analyst-range isn't free, but the series' own realized
change-distribution is an honest stand-in.) Direction-of-shock preserved
(positive = upside change-surprise, negative = downside).

NOT identical to Citi (no real consensus feed) — disclosed proxy, not a
fabricated certainty. Captures the moment the data path bends.

Stack covered :
  - PAYEMS    : nonfarm payrolls
  - UNRATE    : unemployment rate (inverted polarity)
  - CPIAUCSL  : CPI all urban
  - PCEPI     : PCE price index
  - INDPRO    : industrial production
  - GDPC1     : real GDP (quarterly)

Requires deep FRED history (≥6 prints → ≥5 changes ; ideally ≥25 prints
→ 24 changes) — see `fetch_history` / `cli/run_fred_backfill.py` (r135),
because the routine `fetch_latest` poll only stores the single latest
observation (the reason this index was dark — composite=None — before
r135).

Future : add per-region (EZ HICP, UK CPI, JP CPI) when the BLS/ECB/
BoE collectors land.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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

# r135 — GROWTH vs INFLATION split (trader MUST-FIX). The composite must
# NOT blend growth + inflation surprises : a hot-CPI upside surprise and a
# strong-NFP upside surprise are OPPOSITE regimes (stagflation vs
# expansion), yet averaging them nets to a meaningless ~0 OR — worse — the
# downstream `confluence_engine._factor_surprise_index` reads the composite
# as a pure GROWTH signal ("data beats → USD strong → bullish equity,
# bearish gold"). Folding inflation into that composite would mislabel a
# hot-inflation print as growth-bullish for SPX/NAS when hot CPI is
# actually equity-NEGATIVE (Fed-repricing channel). So the COMPOSITE is
# built from GROWTH series only ; inflation series are still z-scored and
# surfaced per-series, just excluded from the composite. This mirrors the
# macro cycle taxonomy (growth × inflation = expansion / reflation /
# deflation / stagflation) — the two axes are orthogonal, never summed.
_GROWTH_SERIES: frozenset[str] = frozenset({"PAYEMS", "UNRATE", "INDPRO", "GDPC1"})
_INFLATION_SERIES: frozenset[str] = frozenset({"CPIAUCSL", "PCEPI"})


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
    """GROWTH-only composite : average of polarity-corrected z-scores over
    the _GROWTH_SERIES with > 5 history (inflation excluded — see split)."""
    band: str  # "strong_negative" / "negative" / "neutral" / "positive" / "strong_positive"
    series: list[SeriesSurprise]
    n_series_used: int
    inflation_composite: float | None = None
    """r137 — SEPARATE inflation-surprise composite : average of the
    _INFLATION_SERIES change-z (NOT polarity-inverted ; +z = hotter
    inflation than its own trend). Orthogonal to the growth `composite`
    (never summed) ; consumed by the regime-conditioned
    `confluence_engine._factor_inflation_surprise` driver. None when no
    inflation series has enough history."""


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


async def _series_history(session: AsyncSession, series_id: str, *, n: int = 25) -> list[float]:
    """Last `n` non-null observations for `series_id`, oldest-first.

    r135 : default bumped 24→25 levels so the period-CHANGE transform
    yields 24 changes (matching the Citi 24-window convention)."""
    cutoff = datetime.now(UTC).date() - timedelta(days=365 * 6)
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


def _to_period_changes(levels: list[float]) -> list[float]:
    """First-difference a level series into period-over-period changes
    (r135). [l0, l1, l2] → [l1-l0, l2-l1]. The macro surprise lives in
    the CHANGE, not the (trend-dominated) level — see module docstring."""
    return [levels[i] - levels[i - 1] for i in range(1, len(levels))]


def _z_score(series: list[float]) -> tuple[float | None, float | None, float | None]:
    """(last, mean, std) of the LAST element vs the prior distribution.
    Returns (None, None, None) if < 5 history or zero variance.

    r135 : callers now pass the CHANGE series (not levels), so `last`
    is the latest period-change and the z is the standardized surprise."""
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
    inflation_z_scores: list[float] = []  # r137 — separate inflation axis
    for sid, label in _SERIES_LABELS.items():
        history = await _series_history(session, sid)
        last_value = history[-1] if history else None
        # r135 : z-score the period-CHANGE distribution, not the
        # trend-dominated level. Need ≥6 levels → ≥5 changes.
        changes = _to_period_changes(history)
        last, mean, std = _z_score(changes)
        if last is None or mean is None or std in (None, 0.0):
            series_results.append(
                SeriesSurprise(
                    series_id=sid,
                    label=label,
                    last_value=last_value,
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
                # last_value stays the latest LEVEL (for display) ;
                # the z is the standardized surprise of the latest CHANGE.
                last_value=last_value,
                rolling_mean=mean,
                rolling_std=std,
                z_score=round(z, 3),
                n_history=len(history),
            )
        )
        # r135 — GROWTH series only feed the growth composite (see
        # _GROWTH_SERIES rationale). r137 — inflation series feed a
        # SEPARATE inflation composite (orthogonal axis, never summed into
        # growth). Each series keeps its per-series z above regardless.
        if sid in _GROWTH_SERIES:
            z_scores.append(z)
        elif sid in _INFLATION_SERIES:
            inflation_z_scores.append(z)

    composite = sum(z_scores) / len(z_scores) if z_scores else None
    if composite is not None:
        composite = round(composite, 3)

    inflation_composite = (
        sum(inflation_z_scores) / len(inflation_z_scores) if inflation_z_scores else None
    )
    if inflation_composite is not None:
        inflation_composite = round(inflation_composite, 3)

    return SurpriseIndexReading(
        region="US",
        composite=composite,
        band=_band(composite),
        series=series_results,
        n_series_used=len(z_scores),
        inflation_composite=inflation_composite,
    )


def render_surprise_index_block(
    r: SurpriseIndexReading,
) -> tuple[str, list[str]]:
    """Markdown + sources for data_pool.py."""
    lines = [f"## Eco Surprise Index ({r.region})"]
    if r.composite is None:
        lines.append("- (insufficient FRED history to compute z-scores yet)")
        return "\n".join(lines), []

    # r135 — composite is GROWTH-surprise only (inflation series shown
    # per-series but excluded from the composite to avoid conflating the
    # growth and inflation regime axes — see _GROWTH_SERIES). The z-score
    # is the standardized surprise of each series' latest period-CHANGE.
    lines.append(
        f"- **Growth-surprise composite z = {r.composite:+.2f}** → band: **{r.band}** "
        f"({r.n_series_used} growth series ; +z = data accelerating vs trend)"
    )
    if r.inflation_composite is not None:
        # r137 — orthogonal inflation axis (NOT summed into growth). +z =
        # inflation running hotter than its own trend (hawkish-leaning) ;
        # the directional read is regime-conditioned downstream.
        lines.append(
            f"- **Inflation-surprise composite z = {r.inflation_composite:+.2f}** "
            f"(separate axis ; +z = hotter than trend ; equity impact depends on the "
            f"growth backdrop — reflation if growth also hot, stagflation if growth soft)"
        )
    lines.append("- Per-series (change-surprise z ; inflation kept on its own axis) :")
    sources: list[str] = []
    for s in r.series:
        z_str = "n/a" if s.z_score is None else f"{s.z_score:+.2f}"
        last_str = "n/a" if s.last_value is None else f"{s.last_value:.3f}"
        lines.append(f"  · {s.series_id:10s} ({s.label}) z={z_str} last={last_str}")
        sources.append(f"FRED:{s.series_id}")
    return "\n".join(lines), sources
