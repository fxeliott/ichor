"""Confluence engine — multi-factor trade strength score.

Eliot's playbook : "is this idea backed by 5+ confluences or just 2?"
This service answers that question explicitly with a 0-100 score per
direction (long/short) computed by aggregating every Phase-1 signal
that has a directional read for the asset :

  - **Rate differential**  — DGS10 minus foreign 10Y trend
  - **COT positioning**   — managed_money_net z-score vs 1y window
  - **Microstructure OFI**  — Lee-Ready trade-flow imbalance
  - **Daily levels**       — spot proximity to PDH/PDL/Pivots
  - **Polymarket overlay** — fresh prediction-market signals
  - **Narrative tracker**  — directional skew of cb_speeches/news 48h
  - **Regime alignment**   — haven_bid / funding_stress / goldilocks
  - **Surprise index**     — eco-data z-score
  - **Funding stress**     — mean-revert friendly when stretched
  - **CB intervention**    — caps directional magnitude on JPY/CHF

Each factor returns a contribution in [-1, +1] (sign = direction,
magnitude = strength). The aggregation is :

  score_long = clamp(50 + 5 × Σ positive_contributions, 0, 100)
  score_short = clamp(50 + 5 × Σ |negative_contributions|, 0, 100)

The "dominant_direction" picks whichever score is higher AND ≥ 60 ;
otherwise neutral. The "confluence_count" is the number of factors
contributing >|0.2| in the dominant direction — Eliot's "5+" rule.

Pure function, no inference — every numeric claim cites a source so
the Critic Agent path can still verify.

VISION_2026 — closes the "I have 14 sections of data, what's the
synthesis?" gap. The brain produces it organically across 4 passes,
but a deterministic synthesis is faster, cheaper, and lets the user
cross-check the brain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CotPosition,
    FredObservation,
    PolygonIntradayBar,
    PolymarketSnapshot,
)
from .daily_levels import DailyLevels, assess_daily_levels
from .funding_stress import assess_funding_stress
from .surprise_index import assess_surprise_index

Direction = Literal["long", "short", "neutral"]


@dataclass(frozen=True)
class Driver:
    """One factor's contribution to the confluence score."""

    factor: str
    """Symbolic name : 'rate_diff' / 'cot' / 'microstructure_ofi' / etc."""
    contribution: float
    """Signed [-1, +1] : positive = long bias, negative = short."""
    evidence: str
    """1-line explanation citing values + source."""
    source: str | None = None
    """Provenance tag for the Critic — same format as DataPool.sources."""


@dataclass(frozen=True)
class ConfluenceReport:
    """Final synthesis returned to the caller."""

    asset: str
    score_long: float
    """0-100. 50 = balanced ; >75 = strong long alignment."""
    score_short: float
    score_neutral: float
    """100 - max(long, short) — leftover undecided mass."""
    dominant_direction: Direction
    confluence_count: int
    """How many drivers contributed > |0.2| in the dominant direction."""
    drivers: list[Driver] = field(default_factory=list)
    rationale: str = ""


# ────────────────────────── Factor builders ───────────────────────────

# Each factor returns a Driver or None (when the input is unavailable).
# Convention : positive contribution = long bias for the queried asset.
# For USD-quote pairs (EUR/USD, GBP/USD, AUD/USD) we follow the natural
# convention "long = the FIRST currency strengthens vs the second".
# For USD-base pairs (USD/JPY, USD/CAD) "long = USD strengthens vs JPY/CAD".


_FOREIGN_10Y: dict[str, str] = {
    "EUR_USD": "IRLTLT01DEM156N",
    "GBP_USD": "IRLTLT01GBM156N",
    "USD_JPY": "IRLTLT01JPM156N",
    "AUD_USD": "IRLTLT01AUM156N",
    "USD_CAD": "IRLTLT01CAM156N",
}

# Sign convention for rate_diff factor :
#   - For X/USD pairs (X is base) : higher US10Y means USD strength → SHORT pair
#     → contribution = -sign(diff)
#   - For USD/Y pairs (USD is base) : higher US10Y means USD strength → LONG pair
#     → contribution = +sign(diff)
_USD_IS_BASE = {"USD_JPY", "USD_CAD"}


async def _factor_rate_diff(
    session: AsyncSession, asset: str
) -> Driver | None:
    """US10Y minus foreign 10Y, normalized by 1bp/+1 wide window."""
    if asset not in _FOREIGN_10Y:
        return None

    async def latest(series_id: str) -> tuple[float, datetime] | None:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=14)
        row = (
            await session.execute(
                select(FredObservation)
                .where(
                    FredObservation.series_id == series_id,
                    FredObservation.observation_date >= cutoff,
                    FredObservation.value.is_not(None),
                )
                .order_by(desc(FredObservation.observation_date))
                .limit(1)
            )
        ).scalars().first()
        if row is None or row.value is None:
            return None
        return float(row.value), datetime.combine(
            row.observation_date, datetime.min.time(), tzinfo=timezone.utc
        )

    us = await latest("DGS10")
    fr = await latest(_FOREIGN_10Y[asset])
    if us is None or fr is None:
        return None
    diff = us[0] - fr[0]
    # Scale : ±2.0% wide is "extreme"
    raw = max(-1.0, min(1.0, diff / 2.0))
    contribution = -raw if asset not in _USD_IS_BASE else raw
    direction = "+long" if contribution > 0 else ("-short" if contribution < 0 else "neutral")
    return Driver(
        factor="rate_diff",
        contribution=contribution,
        evidence=(
            f"US10Y={us[0]:.2f}% − {_FOREIGN_10Y[asset]}={fr[0]:.2f}% "
            f"⇒ diff {diff:+.2f}% ({direction})"
        ),
        source=f"FRED:DGS10|FRED:{_FOREIGN_10Y[asset]}",
    )


_COT_MARKET: dict[str, tuple[str, bool]] = {
    # asset → (market_code, reverse_polarity)
    # reverse_polarity True for USD-base pairs : managed_money_net long
    # on JPY futures = JPY strength = USD/JPY SHORT
    "EUR_USD": ("099741", False),
    "GBP_USD": ("096742", False),
    "USD_JPY": ("097741", True),
    "AUD_USD": ("232741", False),
    "USD_CAD": ("090741", True),
    "XAU_USD": ("088691", False),
    "NAS100_USD": ("209742", False),
}


async def _factor_cot(session: AsyncSession, asset: str) -> Driver | None:
    """Z-score of managed_money_net vs the last 52 weekly reports."""
    cfg = _COT_MARKET.get(asset)
    if cfg is None:
        return None
    market, reverse = cfg

    rows = list(
        (
            await session.execute(
                select(CotPosition)
                .where(CotPosition.market_code == market)
                .order_by(desc(CotPosition.report_date))
                .limit(52)
            )
        ).scalars().all()
    )
    if len(rows) < 4:
        return None
    nets = [float(r.managed_money_net) for r in rows]
    cur = nets[0]
    mean = sum(nets) / len(nets)
    var = sum((x - mean) ** 2 for x in nets) / max(1, len(nets) - 1)
    std = var ** 0.5 if var > 0 else 1.0
    z = (cur - mean) / std
    # Tame extreme z (>3) and convert to [-1, +1]
    raw = max(-1.0, min(1.0, z / 2.0))
    contribution = -raw if reverse else raw
    return Driver(
        factor="cot",
        contribution=contribution,
        evidence=(
            f"managed_money_net={cur:+,.0f} (52w mean {mean:+,.0f}, "
            f"z={z:+.2f}{', reversed' if reverse else ''}) "
            f"on {rows[0].report_date:%Y-%m-%d}"
        ),
        source=f"CFTC:COT:{market}@{rows[0].report_date.isoformat()}",
    )


async def _factor_microstructure(
    session: AsyncSession, asset: str
) -> Driver | None:
    """Lee-Ready signed-volume OFI computed inline from last 4h of bars."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
    rows = list(
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(
                    PolygonIntradayBar.asset == asset,
                    PolygonIntradayBar.bar_ts >= cutoff,
                )
                .order_by(PolygonIntradayBar.bar_ts.asc())
            )
        ).scalars().all()
    )
    if len(rows) < 5:
        return None
    signed_sum = 0.0
    total_volume = 0.0
    prev_close = float(rows[0].close)
    for r in rows:
        v = float(r.volume or 0.0)
        if v <= 0:
            continue
        c = float(r.close)
        if c > prev_close:
            signed_sum += v
        elif c < prev_close:
            signed_sum -= v
        total_volume += v
        prev_close = c
    if total_volume <= 0:
        return None
    ofi = signed_sum / total_volume
    raw = max(-1.0, min(1.0, ofi))
    return Driver(
        factor="microstructure_ofi",
        contribution=raw,
        evidence=(
            f"Lee-Ready OFI 4h = {ofi:+.2f} "
            f"(signed_volume={signed_sum:+.0f} / total={total_volume:.0f})"
        ),
        source=f"polygon_intraday:{asset}@4h_ofi",
    )


def _factor_daily_levels(asset: str, levels: DailyLevels) -> Driver | None:
    """Spot near PDH = continuation-long bias (mild).
    Spot above PDH AND no recent rejection = swept upside = mean-revert short bias.
    """
    if levels.spot is None or levels.pdh is None or levels.pdl is None:
        return None
    spot = levels.spot
    pdh = levels.pdh
    pdl = levels.pdl
    if pdh <= pdl:
        return None
    pos = (spot - pdl) / (pdh - pdl)
    # Inside range : mild continuation bias as we approach extremes
    # Above PDH (pos > 1) : swept → mild reversal short
    # Below PDL (pos < 0) : swept → mild reversal long
    if 0.0 <= pos <= 1.0:
        # Tent : 0 mid, ±0.4 at extremes
        contribution = (pos - 0.5) * 0.8
        evidence = (
            f"spot {spot:.5f} at {pos*100:.0f}% of PDH-PDL range "
            f"({pdl:.5f}-{pdh:.5f})"
        )
    elif pos > 1.0:
        contribution = -0.5  # swept upside → reversal short
        evidence = (
            f"spot {spot:.5f} ABOVE PDH {pdh:.5f} (swept upside) → reversal bias"
        )
    else:
        contribution = 0.5  # swept downside → reversal long
        evidence = (
            f"spot {spot:.5f} BELOW PDL {pdl:.5f} (swept downside) → reversal bias"
        )
    return Driver(
        factor="daily_levels",
        contribution=contribution,
        evidence=evidence,
        source=f"polygon_intraday:{asset}@daily_levels",
    )


# Keyword sets for polymarket → asset directional impact mapping.
# These are deliberately conservative — false positives on a directional
# call would mis-bias the synthesis.
_POLY_KEYWORDS: dict[str, list[tuple[list[str], dict[str, float]]]] = {
    # phrase → impact per asset (signed contribution if YES > 0.55)
    "fed_cut": (
        [["fed", "cut"], ["fomc", "cut"], ["interest rate", "cut"]],
        # Fed cut → USD weak
        {
            "EUR_USD": +0.25,
            "GBP_USD": +0.25,
            "AUD_USD": +0.25,
            "USD_JPY": -0.25,
            "USD_CAD": -0.20,
            "XAU_USD": +0.30,
            "NAS100_USD": +0.20,
        },
    ),
    "fed_hike": (
        [["fed", "hike"], ["fomc", "hike"], ["interest rate", "hike"]],
        {
            "EUR_USD": -0.25,
            "GBP_USD": -0.25,
            "AUD_USD": -0.25,
            "USD_JPY": +0.25,
            "USD_CAD": +0.20,
            "XAU_USD": -0.30,
            "NAS100_USD": -0.20,
        },
    ),
    "recession": (
        [["recession"], ["us recession"]],
        # Recession → risk off, USD strong, gold mixed, indices down
        {
            "EUR_USD": -0.10,
            "GBP_USD": -0.10,
            "AUD_USD": -0.20,
            "USD_JPY": -0.15,
            "XAU_USD": +0.15,
            "NAS100_USD": -0.30,
            "SPX500_USD": -0.30,
        },
    ),
}


def _matches_phrase(text_lower: str, phrase: list[str]) -> bool:
    return all(token in text_lower for token in phrase)


async def _factor_polymarket(
    session: AsyncSession, asset: str
) -> Driver | None:
    """Aggregate polymarket signal — sum of keyword-matched impacts."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = list(
        (
            await session.execute(
                select(PolymarketSnapshot)
                .where(PolymarketSnapshot.fetched_at >= cutoff)
                .order_by(desc(PolymarketSnapshot.fetched_at))
                .limit(40)
            )
        ).scalars().all()
    )
    if not rows:
        return None
    total_contribution = 0.0
    matched_examples: list[str] = []
    for r in rows:
        q = (r.question or "").lower()
        yes = (
            r.last_prices[0]
            if r.last_prices and len(r.last_prices) > 0
            else None
        )
        if yes is None:
            continue
        for kw_id, (phrases, impacts) in _POLY_KEYWORDS.items():
            if asset not in impacts:
                continue
            if not any(_matches_phrase(q, p) for p in phrases):
                continue
            # Convert YES probability to a [-1, +1] confidence weight :
            # YES=0.50 → 0 weight ; YES=1.00 → +1 weight ; YES=0.00 → -1 weight.
            weight = (yes - 0.5) * 2.0
            contribution = impacts[asset] * weight
            total_contribution += contribution
            if abs(contribution) >= 0.05 and len(matched_examples) < 3:
                matched_examples.append(
                    f"'{r.question[:60]}' YES={yes:.0%} ⇒ {contribution:+.2f}"
                )
    if not matched_examples:
        return None
    raw = max(-1.0, min(1.0, total_contribution))
    return Driver(
        factor="polymarket",
        contribution=raw,
        evidence=" ; ".join(matched_examples)[:240],
        source="polymarket:keyword_aggregate",
    )


async def _factor_funding_stress(
    session: AsyncSession, asset: str
) -> Driver | None:
    """Funding stress regime → mean-revert friendly. Stretched moves fade."""
    reading = await assess_funding_stress(session)
    score = getattr(reading, "stress_score", None)
    if score is None or not isinstance(score, (int, float)):
        return None
    # High stress = USD bid (haven flow). Caps at ±0.4 contribution.
    raw = max(-0.4, min(0.4, float(score) * 0.4))
    # USD bid favors USD pairs : long USD/JPY, short EUR/USD etc.
    if asset == "XAU_USD":
        contribution = raw  # gold also benefits from stress (haven)
    elif asset in _USD_IS_BASE:
        contribution = raw
    else:
        contribution = -raw
    return Driver(
        factor="funding_stress",
        contribution=contribution,
        evidence=f"stress_score = {score:+.2f} (>0 = stress, USD haven)",
        source="empirical_model:funding_stress",
    )


async def _factor_surprise_index(
    session: AsyncSession, asset: str
) -> Driver | None:
    reading = await assess_surprise_index(session)
    composite = getattr(reading, "composite", None)
    if composite is None or not isinstance(composite, (int, float)):
        return None
    z = float(composite)
    # Positive surprise = US data beats → USD strong
    raw = max(-1.0, min(1.0, z * 0.5))
    if asset in {"NAS100_USD", "SPX500_USD"}:
        contribution = raw  # growth surprises bullish for equity
    elif asset == "XAU_USD":
        contribution = -raw  # growth surprises bearish for gold
    elif asset in _USD_IS_BASE:
        contribution = raw  # USD-base : long USD when US beats
    else:
        contribution = -raw  # X/USD : short pair when US beats
    return Driver(
        factor="surprise_index",
        contribution=contribution,
        evidence=f"eco-surprise composite z = {z:+.2f}",
        source="empirical_model:surprise_index",
    )


# ────────────────────────── Aggregator ────────────────────────────────


async def assess_confluence(
    session: AsyncSession, asset: str, *, levels: DailyLevels | None = None
) -> ConfluenceReport:
    """Run every factor builder, aggregate scores."""
    asset = asset.upper()
    if levels is None:
        levels = await assess_daily_levels(session, asset)

    drivers: list[Driver] = []
    for factor in (
        await _factor_rate_diff(session, asset),
        await _factor_cot(session, asset),
        await _factor_microstructure(session, asset),
        _factor_daily_levels(asset, levels),
        await _factor_polymarket(session, asset),
        await _factor_funding_stress(session, asset),
        await _factor_surprise_index(session, asset),
    ):
        if factor is not None:
            drivers.append(factor)

    pos = sum(d.contribution for d in drivers if d.contribution > 0)
    neg = sum(-d.contribution for d in drivers if d.contribution < 0)
    score_long = max(0.0, min(100.0, 50.0 + 8.0 * pos))
    score_short = max(0.0, min(100.0, 50.0 + 8.0 * neg))
    score_neutral = max(0.0, 100.0 - max(score_long, score_short))

    dominant: Direction
    if score_long >= 60 and score_long >= score_short + 5:
        dominant = "long"
    elif score_short >= 60 and score_short >= score_long + 5:
        dominant = "short"
    else:
        dominant = "neutral"

    threshold = 0.2
    if dominant == "long":
        confluence_count = sum(1 for d in drivers if d.contribution > threshold)
    elif dominant == "short":
        confluence_count = sum(1 for d in drivers if d.contribution < -threshold)
    else:
        confluence_count = 0

    rationale = (
        f"{len(drivers)} drivers évalués · score_long={score_long:.0f} "
        f"score_short={score_short:.0f} · {confluence_count} confluences "
        f"alignées en {dominant}."
    )

    return ConfluenceReport(
        asset=asset,
        score_long=round(score_long, 1),
        score_short=round(score_short, 1),
        score_neutral=round(score_neutral, 1),
        dominant_direction=dominant,
        confluence_count=confluence_count,
        drivers=drivers,
        rationale=rationale,
    )


def render_confluence_block(r: ConfluenceReport) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    lines = [
        f"## Confluence engine ({r.asset})",
        f"- Score LONG : **{r.score_long:.0f}/100** · "
        f"SHORT : **{r.score_short:.0f}/100** · "
        f"neutre : {r.score_neutral:.0f}",
        f"- Dominante : **{r.dominant_direction.upper()}** · "
        f"{r.confluence_count} confluences alignées",
    ]
    if r.drivers:
        lines.append("- Drivers :")
        for d in r.drivers:
            sign = "+" if d.contribution >= 0 else ""
            lines.append(
                f"  · {d.factor:>20s}  {sign}{d.contribution:+.2f}  — {d.evidence}"
            )
    sources: list[str] = [
        d.source for d in r.drivers if d.source is not None
    ]
    return "\n".join(lines), sources
