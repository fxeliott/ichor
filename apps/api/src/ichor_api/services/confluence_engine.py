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
from datetime import UTC, datetime, timedelta
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
from .risk_appetite import assess_risk_appetite
from .surprise_index import assess_surprise_index
from .vix_term_structure import assess_vix_term

Direction = Literal["long", "short", "neutral"]


@dataclass(frozen=True)
class Driver:
    """One factor's contribution to the confluence score.

    ADR-017 boundary (r142 trader RED-1 + code-reviewer hardening) :
    the `contribution` sign is an INTERNAL engine aggregation artifact
    (it drives the score_long / score_short summation below). It is
    NEVER exported to user-facing surfaces as a directional trade
    instruction — the r142 frontend
    (`apps/web2/components/briefing/ConvictionGroundingPanel.tsx`)
    explicitly strips the sign and displays only the absolute magnitude
    so users see "rate_diff 0.45" rather than "rate_diff +0.45". The
    internal sign convention is documented at the factor-builder level
    (lines below) and used only by the score aggregator inside this
    module + the brier_optimizer.
    """

    factor: str
    """Symbolic name : 'rate_diff' / 'cot' / 'microstructure_ofi' / etc."""
    contribution: float
    """Signed [-1, +1] : magnitude = factor strength, sign = INTERNAL
    aggregation parity with the engine's hypothesized asset-frame
    direction. Consumed by `assess_confluence()` to build score_long /
    score_short. NEVER displayed signed on user-facing surfaces per
    ADR-017 + r142 UI-boundary stripping."""
    evidence: str
    """1-line explanation citing values + source. NON-OPTIONAL — every
    engine factor MUST emit non-empty evidence so the frontend
    `evidence != null` filter reliably distinguishes engine entries
    from any future LLM-narrative entries that share the schema."""
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


async def _factor_rate_diff(session: AsyncSession, asset: str) -> Driver | None:
    """US10Y minus foreign 10Y, normalized by 1bp/+1 wide window."""
    if asset not in _FOREIGN_10Y:
        return None

    async def latest(series_id: str) -> tuple[float, datetime] | None:
        cutoff = datetime.now(UTC).date() - timedelta(days=14)
        row = (
            (
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
            )
            .scalars()
            .first()
        )
        if row is None or row.value is None:
            return None
        return float(row.value), datetime.combine(
            row.observation_date, datetime.min.time(), tzinfo=UTC
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
        )
        .scalars()
        .all()
    )
    if len(rows) < 4:
        return None
    nets = [float(r.managed_money_net) for r in rows]
    cur = nets[0]
    mean = sum(nets) / len(nets)
    var = sum((x - mean) ** 2 for x in nets) / max(1, len(nets) - 1)
    std = var**0.5 if var > 0 else 1.0
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


async def _factor_microstructure(session: AsyncSession, asset: str) -> Driver | None:
    """Lee-Ready signed-volume OFI computed inline from last 4h of bars."""
    cutoff = datetime.now(UTC) - timedelta(hours=4)
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
        )
        .scalars()
        .all()
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
        evidence = f"spot {spot:.5f} at {pos * 100:.0f}% of PDH-PDL range ({pdl:.5f}-{pdh:.5f})"
    elif pos > 1.0:
        contribution = -0.5  # swept upside → reversal short
        evidence = f"spot {spot:.5f} ABOVE PDH {pdh:.5f} (swept upside) → reversal bias"
    else:
        contribution = 0.5  # swept downside → reversal long
        evidence = f"spot {spot:.5f} BELOW PDL {pdl:.5f} (swept downside) → reversal bias"
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


async def _factor_polymarket(session: AsyncSession, asset: str) -> Driver | None:
    """Aggregate polymarket signal — sum of keyword-matched impacts."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    rows = list(
        (
            await session.execute(
                select(PolymarketSnapshot)
                .where(PolymarketSnapshot.fetched_at >= cutoff)
                .order_by(desc(PolymarketSnapshot.fetched_at))
                .limit(40)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    total_contribution = 0.0
    matched_examples: list[str] = []
    for r in rows:
        q = (r.question or "").lower()
        yes = r.last_prices[0] if r.last_prices and len(r.last_prices) > 0 else None
        if yes is None:
            continue
        for _kw_id, (phrases, impacts) in _POLY_KEYWORDS.items():
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
                matched_examples.append(f"'{r.question[:60]}' YES={yes:.0%} ⇒ {contribution:+.2f}")
    if not matched_examples:
        return None
    raw = max(-1.0, min(1.0, total_contribution))
    return Driver(
        factor="polymarket",
        contribution=raw,
        evidence=" ; ".join(matched_examples)[:240],
        source="polymarket:keyword_aggregate",
    )


async def _factor_funding_stress(session: AsyncSession, asset: str) -> Driver | None:
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


async def _factor_vix_term(session: AsyncSession, asset: str) -> Driver | None:
    """VIX term structure : backwardation = mean-revert friendly equity-long."""
    r = await assess_vix_term(session)
    if r.ratio is None:
        return None
    # Backwardation (>1.0) → bullish equities short-term, bearish gold mean-revert
    # Stretched contango (<0.80) → late-cycle warning, mild bearish equities
    raw = (r.ratio - 0.95) * 2.0  # ratio 1.0 → +0.10, 1.15 → +0.40
    raw = max(-0.6, min(0.6, raw))

    if asset in {"NAS100_USD", "SPX500_USD"}:
        contribution = raw  # backwardation good for equities
    elif asset == "XAU_USD":
        contribution = -raw * 0.5  # backwardation slightly bearish gold (mean-revert risk-off)
    elif asset in _USD_IS_BASE:
        contribution = -raw * 0.3  # USD/JPY: backwardation = haven JPY bid, USD weak
    else:
        contribution = raw * 0.3  # X/USD : risk-on long pair
    return Driver(
        factor="vix_term",
        contribution=round(contribution, 3),
        evidence=(f"VIX 1M={r.vix_1m:.1f} / 3M={r.vix_3m:.1f} ratio={r.ratio:.2f} ({r.regime})"),
        source="FRED:VIXCLS|FRED:VXVCLS",
    )


async def _factor_btc_risk_proxy(session: AsyncSession, asset: str) -> Driver | None:
    """BTC/USD 24h % change as risk-on/off proxy.

    BTC is a leading indicator of speculative risk appetite (esp. for
    NAS100, AUD/USD, JPY carry). Strong BTC up = risk-on tailwind.
    """
    cutoff_now = datetime.now(UTC)
    cutoff_24h = cutoff_now - timedelta(hours=24)

    last = (
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(PolygonIntradayBar.asset == "BTC_USD")
                .order_by(desc(PolygonIntradayBar.bar_ts))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    first = (
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(
                    PolygonIntradayBar.asset == "BTC_USD",
                    PolygonIntradayBar.bar_ts <= cutoff_24h,
                )
                .order_by(desc(PolygonIntradayBar.bar_ts))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    # Fallback : use earliest bar if 24h window too narrow
    if first is None:
        first = (
            (
                await session.execute(
                    select(PolygonIntradayBar)
                    .where(PolygonIntradayBar.asset == "BTC_USD")
                    .order_by(PolygonIntradayBar.bar_ts.asc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
    if last is None or first is None or first.close <= 0:
        return None
    pct_change = (float(last.close) / float(first.close) - 1.0) * 100.0
    # Scale : ±10% wide → cap ±1.0 contribution
    raw = max(-1.0, min(1.0, pct_change / 10.0))

    # BTC up = risk-on. Map per asset :
    if asset in {"NAS100_USD", "SPX500_USD"}:
        contribution = raw * 0.5  # equity beta to risk
    elif asset == "AUD_USD":
        contribution = raw * 0.3  # commodity FX risk currency
    elif asset == "USD_JPY":
        contribution = raw * 0.3  # carry trade : long USD/JPY in risk-on
    elif asset == "XAU_USD":
        contribution = raw * 0.1  # weak link, BTC sometimes correlates with gold
    elif asset in {"EUR_USD", "GBP_USD"}:
        contribution = -raw * 0.2  # USD haven sells off in risk-on
    else:
        contribution = 0.0
    if abs(contribution) < 0.05:
        return None
    return Driver(
        factor="btc_risk_proxy",
        contribution=round(contribution, 3),
        evidence=(
            f"BTC/USD 24h change = {pct_change:+.1f}% "
            f"(spot {last.close:.0f}, t-24h {first.close:.0f})"
        ),
        source=f"polygon_intraday:BTC_USD@{last.bar_ts.isoformat()}",
    )


async def _factor_risk_appetite(session: AsyncSession, asset: str) -> Driver | None:
    """Composite risk-on/off score → tilts equities + commodity FX."""
    r = await assess_risk_appetite(session)
    if not r.components:
        return None
    raw = r.composite  # already in [-1, +1]
    if asset in {"NAS100_USD", "SPX500_USD"}:
        contribution = raw * 0.5  # equity beta to risk
    elif asset == "AUD_USD":
        contribution = raw * 0.4  # commodity risk currency
    elif asset == "XAU_USD":
        contribution = -raw * 0.2  # gold haven (slight)
    elif asset == "USD_JPY":
        contribution = raw * 0.3  # carry trade : long USD/JPY in risk-on
    elif asset == "USD_CAD":
        contribution = -raw * 0.2  # CAD oil-linked → risk-on hurts USD/CAD
    else:
        contribution = -raw * 0.2  # EUR/USD, GBP/USD : risk-on hurts USD haven
    return Driver(
        factor="risk_appetite",
        contribution=round(contribution, 3),
        evidence=f"composite {r.composite:+.2f} ({r.band}, n={len(r.components)} components)",
        source="empirical_model:risk_appetite",
    )


async def _factor_surprise_index(session: AsyncSession, asset: str) -> Driver | None:
    reading = await assess_surprise_index(session)
    composite = getattr(reading, "composite", None)
    if composite is None or not isinstance(composite, (int, float)):
        return None
    z = float(composite)
    # r135 — `composite` is now a GROWTH-surprise signal only (inflation
    # series are z-scored per-series but excluded from the composite, so
    # this growth-direction mapping is correct — a hot-CPI print no longer
    # leaks in mislabelled as growth). Positive growth-surprise = US data
    # beats → USD strong.
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
        evidence=f"US growth-surprise composite z = {z:+.2f}",
        source="empirical_model:surprise_index",
    )


async def _factor_inflation_surprise(session: AsyncSession, asset: str) -> Driver | None:
    """r137 — inflation-surprise factor, SEPARATE from the growth
    `surprise_index` factor (orthogonal regime axes — never merged ; the
    Critic + Brier optimizer audit/weight them apart). Built on the
    ichor-trader r137 advisory :

    - **USD leg is regime-ROBUST** : a hot inflation surprise (+z) is
      USD-positive across BOTH reflation and stagflation (hawkish Fed
      repricing), so the USD-base / X-USD sign is UNCONDITIONAL.
    - **Equity leg is regime-CONDITIONED** : hot inflation is equity-
      negative (discount-rate channel) ONLY when growth is soft
      (stagflation) ; when growth is ALSO hot (reflation), nominal-earnings
      growth offsets it, so the equity-negative contribution is dampened
      toward ~0. Conditioned on the growth composite (same reading, no
      extra query).
    - **XAU = 0** : gold's inflation reaction is a genuine 3-way tug
      (nominal yields ↑ bearish / real-yield path ambiguous / inflation-
      hedge bid bullish / USD-strength bearish). A guessed sign would be
      fabricated certainty (doctrine #11) — surfaced as context, zero
      contribution.
    - **Smaller coefficient (×0.3 vs growth ×0.5)** : inflation→price runs
      through a noisier, lagged Fed-reaction-function channel.
    """
    reading = await assess_surprise_index(session)
    infl = getattr(reading, "inflation_composite", None)
    if infl is None or not isinstance(infl, (int, float)):
        return None
    z = float(infl)
    raw = max(-1.0, min(1.0, z * 0.3))  # smaller coeff than growth (lagged)

    # Reflation dampener for the equity leg : how "hot" is growth (0..1).
    growth_z = reading.composite if isinstance(reading.composite, (int, float)) else 0.0
    reflation = max(0.0, min(1.0, float(growth_z)))
    equity_damp = 1.0 - 0.7 * reflation  # 1.0 (stagflation) .. 0.3 (reflation)

    if asset in {"NAS100_USD", "SPX500_USD"}:
        # Hot inflation = hawkish = equity-negative, dampened under reflation.
        contribution = -raw * equity_damp
    elif asset == "XAU_USD":
        contribution = 0.0  # honest zero — sign genuinely ambiguous
    elif asset in _USD_IS_BASE:
        contribution = raw  # USD-base : hot inflation → USD strong (robust)
    else:
        contribution = -raw  # X/USD : USD strong → short the pair (robust)

    # Label aligned with the damp engagement (any positive growth dampens
    # the equity leg → "reflation" ; growth ≤ 0 → full hawkish hit →
    # "stagflation-leaning"). r137 trader YELLOW : threshold was 0.1 while
    # equity_damp engages from >0 — aligned to 0 for consistency.
    regime = "reflation" if reflation > 0.0 else "stagflation-leaning"
    return Driver(
        factor="inflation_surprise",
        contribution=contribution,
        evidence=(
            f"US inflation-surprise composite z = {z:+.2f} "
            f"(growth backdrop {regime} ; equity impact regime-conditioned, "
            f"XAU neutral by design)"
        ),
        source="empirical_model:surprise_index",
    )


async def _factor_event_anticipation(session: AsyncSession, asset: str) -> Driver | None:
    """r147 Engine 8 — Event-Driven anticipation per profondeur
    (Mission centrale axis-4). Literature-cited PRIOR drift expectation
    keyed on (event_class, impact_tier, time-to-event, VIX regime,
    business-cycle phase).

    Foundations (verbatim citations -- NOT memory) :
    - Lucca-Moench (2015) JoF 70:329-371 — original pre-FOMC drift
      (~50bp avg S&P 500 return in 24h pre-FOMC window, 1994-2011).
    - Kurov-Halova-Wolfe-Gilbert (2021) — drift attenuation post-2016
      attributed to FedWatch popularity ; alive in high-VIX regimes
      2022-2024 (QuantSeeker replication through Dec 2024).
    - Boyd-Hu-Jagannathan (2005) JoF — "bad news is good news"
      business-cycle asymmetry : reaction SIGN flips with cycle phase.
    - arXiv 2212.04525 (2022) — monetary-uncertainty conditioning of
      MNA reaction (counter-intuitive regime guard).

    HONEST SCOPE : magnitude is a LITERATURE-CITED PRIOR, not Ichor-
    data-calibrated. Sign defaults to expansion (+1) when output_gap
    proxy unavailable (doctrine #11 + lesson #37 explicit caveat in
    Driver.evidence). Per-asset transmission :

    - **USD-base / X-USD pairs** : positive expected drift → USD bid
      anticipation (default expansion sign). Routes to long-USD
      contribution via `_USD_IS_BASE` mapping (parity with
      inflation_surprise).
    - **Equity indices (SPX/NAS)** : positive drift is equity-positive
      under expansion (Lucca-Moench original finding), regime-flipped
      to equity-negative under contraction (Boyd-Hu-Jagannathan).
    - **XAU** : ambiguous (rates ↑ bearish / inflation-hedge bid bullish
      / USD-strength bearish) → zero contribution honestly (doctrine
      #11 -- parity with `_factor_inflation_surprise` XAU=0 design).

    Coefficient calibration (r147 code-reviewer SF-1 + post-empirical-math
    review) : raw_bp / 100 × 1.2, capped at ±0.6. This calibrates against
    the r142 `ENGINE_DRIVER_MIN_ABS_CONTRIBUTION = 0.2` threshold gating
    surface visibility on `<ConvictionGroundingPanel>` 4th tile. At
    coefficient=0.4 + cap=0.5 (initial r147 v0), even FOMC firing-now-peak-
    VIX yielded contribution=0.2 (boundary, threshold is strict >0.2) so
    drivers NEVER displayed. At coefficient=1.2 + cap=0.6 :

      FOMC peak    50/100 × 1.2 = 0.60 (cap)  ✓ displays
      ECB  peak    35/100 × 1.2 = 0.42        ✓ displays
      BoE  peak    25/100 × 1.2 = 0.30        ✓ displays
      NFP  peak    20/100 × 1.2 = 0.24        ✓ displays
      CPI  peak    20/100 × 1.2 = 0.24        ✓ displays
      BoJ  peak    15/100 × 1.2 = 0.18        × silent (acceptable -
                                                 BoJ literature weakest)

    Range respects r137 inflation_surprise budget (±1.0 cap with z×0.3
    coefficient) ; cap ±0.6 leaves room for other factors in score
    aggregator (parity with `_factor_inflation_surprise` philosophy).

    r147 trader YELLOW-2 fix : attenuate magnitude × 0.5 when
    `confidence='low'` AND `vix_regime_gate='unavailable'` to preserve
    driver visibility without overweighting degraded data.
    """
    from .event_proximity_engine import assess_event_proximity

    factor = await assess_event_proximity(session=session, asset=asset)
    if factor is None:
        return None  # no future events in window → empty
    if factor.expected_drift_magnitude_bp is None:
        return None  # event_class unmapped OR magnitude below noise floor

    # Scale bp magnitude to confluence contribution range (SF-1 calibration).
    raw = factor.expected_drift_magnitude_bp / 100.0 * 1.2
    raw = max(-0.6, min(0.6, raw))

    # r147 trader YELLOW-2 : attenuate × 0.5 on degraded VIX-unavailable
    # confidence — preserves driver visibility (vs binary suppression)
    # but halves the magnitude budget, matching the "honest gap" framing.
    if factor.vix_regime_gate == "unavailable" and factor.confidence == "low":
        raw = raw * 0.5

    # Per-asset transmission (parity with _factor_inflation_surprise
    # asset-conditional sign discipline).
    if asset in {"NAS100_USD", "SPX500_USD"}:
        # Positive drift = equity-positive under expansion ; regime-flipped
        # under contraction (already encoded in factor.expected_drift_direction
        # via business_cycle_sign).
        contribution = raw
    elif asset == "XAU_USD":
        contribution = 0.0  # honest zero — sign genuinely ambiguous
    elif asset in _USD_IS_BASE:
        # USD-base : positive drift → USD strong (long the pair under expansion).
        contribution = raw
    else:
        # X/USD : USD strong → short the pair.
        contribution = -raw

    # Evidence string : verbatim event title + minutes until + VIX gate +
    # caveat for downstream Critic verification (source-stamping per ADR-017).
    evidence_parts = []
    if factor.next_event_title and factor.next_event_minutes_until is not None:
        evidence_parts.append(
            f"{factor.next_event_title} dans {factor.next_event_minutes_until} min"
        )
    evidence_parts.append(f"gate VIX={factor.vix_regime_gate}")
    evidence_parts.append(f"drift attendu {factor.expected_drift_magnitude_bp:+.0f}bp")
    evidence_parts.append(factor.caveat)
    evidence = " | ".join(evidence_parts)

    return Driver(
        factor="event_anticipation",
        contribution=round(contribution, 3),
        evidence=evidence,
        source="empirical_model:event_proximity_engine|FRED:VIXCLS|literature:Lucca-Moench-2015",
    )


# ────────────────────────── Aggregator ────────────────────────────────


async def assess_confluence(
    session: AsyncSession,
    asset: str,
    *,
    levels: DailyLevels | None = None,
    regime: str = "all",
) -> ConfluenceReport:
    """Run every factor builder, aggregate scores.

    Brier-optimized factor weights are loaded from
    `confluence_weights_history` (active row for the given asset+regime).
    Empty / missing → equal-weight fallback (1.0 per factor) preserves
    the legacy behavior pre-Brier-feedback wiring.
    """
    from .brier_optimizer import latest_active_weights

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
        await _factor_inflation_surprise(session, asset),
        await _factor_vix_term(session, asset),
        await _factor_risk_appetite(session, asset),
        await _factor_btc_risk_proxy(session, asset),
        await _factor_event_anticipation(session, asset),  # r147 Engine 8
    ):
        if factor is not None:
            drivers.append(factor)

    # Brier-optimized weights — active row from confluence_weights_history.
    # Try (asset, regime) first, then global (asset=None, regime). Equal-
    # weight if neither exists yet (cold start / pre-optimizer-run).
    weights: dict[str, float] | None = None
    try:
        weights = await latest_active_weights(session, asset=asset, regime=regime)
        if weights is None:
            weights = await latest_active_weights(session, asset=None, regime=regime)
    except Exception:
        # Defensive : if the table is missing or query fails, fall back
        # to equal-weights rather than crash the brain pipeline.
        weights = None

    def _factor_weight(name: str) -> float:
        if weights is None:
            return 1.0
        return float(weights.get(name, 1.0))

    pos = sum(d.contribution * _factor_weight(d.factor) for d in drivers if d.contribution > 0)
    neg = sum(-d.contribution * _factor_weight(d.factor) for d in drivers if d.contribution < 0)
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
            lines.append(f"  · {d.factor:>20s}  {sign}{d.contribution:+.2f}  — {d.evidence}")
    sources: list[str] = [d.source for d in r.drivers if d.source is not None]
    return "\n".join(lines), sources
