"""Portfolio exposure synthesizer — net basket exposure across all 8 cards.

Aggregates the latest session card per asset into 5 exposure axes :
  - **USD**    : sum of "long USD" minus "short USD" weighted by conviction × magnitude
  - **EQUITY** : NAS100 + SPX500 net long position
  - **GOLD**   : XAU_USD bias × conviction
  - **JPY**    : USD_JPY net short = JPY haven exposure
  - **COMMODITY_FX** : AUD/CAD aggregate (risk-on commodities)

Each axis returns a normalized [-1, +1] score where +1 = max long, -1 = max short.
Identifies CONCENTRATION RISK : if 5+ cards lean USD-long, the trader needs
to know they're effectively running a single-currency basket bet.

Pure function. Reads only the most-recent session_card_audit per (asset).

VISION_2026 — closes the "what's my net exposure across all cards?" gap.
A trader picking 6 individual signals can end up unwittingly long USD on
all of them ; this surfaces it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SessionCardAudit

# Per-asset USD impact when bias=long :
#   For X/USD pairs : long X/USD → SHORT USD (negative for USD axis)
#   For USD/Y pairs : long USD/Y → LONG USD (positive for USD axis)
_USD_AXIS: dict[str, float] = {
    "EUR_USD": -1.0,
    "GBP_USD": -1.0,
    "AUD_USD": -1.0,
    "USD_JPY": +1.0,
    "USD_CAD": +1.0,
    "XAU_USD": -0.6,  # gold ↑ generally USD-neutral but slight haven
    "NAS100_USD": -0.3,  # NAS strong → USD slight risk-on bid
    "SPX500_USD": -0.3,
}

# Per-asset equity beta (NAS / SPX direct ; AUD some risk beta)
_EQUITY_AXIS: dict[str, float] = {
    "NAS100_USD": +1.0,
    "SPX500_USD": +1.0,
    "AUD_USD": +0.4,  # commodity risk currency
    "USD_JPY": +0.3,  # carry, risk-on rises
    "XAU_USD": -0.3,  # equity up → gold soft
}

# Gold axis : direct exposure
_GOLD_AXIS: dict[str, float] = {
    "XAU_USD": +1.0,
    "USD_JPY": -0.3,  # JPY weak ↔ gold up (correlated risk dimension)
}

# JPY axis : long JPY = haven exposure
_JPY_AXIS: dict[str, float] = {
    "USD_JPY": -1.0,  # short USD/JPY = long JPY
    "EUR_USD": +0.0,
    "XAU_USD": +0.3,  # gold haven correlates with JPY haven
    "NAS100_USD": -0.3,
}

# Commodity FX axis (AUD + CAD risk-on)
_COMMODITY_AXIS: dict[str, float] = {
    "AUD_USD": +1.0,
    "USD_CAD": -1.0,  # short USD/CAD = long CAD
}


@dataclass(frozen=True)
class CardLite:
    asset: str
    bias: str
    """long / short / neutral."""
    conviction_pct: float
    magnitude_pips_low: float | None
    magnitude_pips_high: float | None
    session_type: str
    created_at: datetime


@dataclass(frozen=True)
class ExposureAxis:
    name: str
    score: float
    """[-1, +1]. Positive = long that axis."""
    contributors: list[tuple[str, float]] = field(default_factory=list)
    """List of (asset, weighted_contribution) for the top contributors."""


@dataclass(frozen=True)
class ExposureReport:
    n_cards: int
    cards: list[CardLite]
    axes: list[ExposureAxis]
    concentration_warnings: list[str] = field(default_factory=list)
    """e.g. "5/8 cards lean USD-long — concentration risk."""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_PHASE1_ASSETS = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)


async def _latest_card(
    session: AsyncSession, asset: str, max_age_hours: int = 24
) -> CardLite | None:
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    row = (
        (
            await session.execute(
                select(SessionCardAudit)
                .where(
                    SessionCardAudit.asset == asset,
                    SessionCardAudit.created_at >= cutoff,
                )
                .order_by(desc(SessionCardAudit.created_at))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return CardLite(
        asset=row.asset,
        bias=row.bias_direction or "neutral",
        conviction_pct=float(row.conviction_pct or 0),
        magnitude_pips_low=row.magnitude_pips_low,
        magnitude_pips_high=row.magnitude_pips_high,
        session_type=row.session_type,
        created_at=row.created_at,
    )


def _direction_sign(bias: str) -> float:
    if bias == "long":
        return +1.0
    if bias == "short":
        return -1.0
    return 0.0


def _card_weight(c: CardLite) -> float:
    """Weight a card by conviction × magnitude band."""
    sign = _direction_sign(c.bias)
    if sign == 0.0:
        return 0.0
    conv = max(0.0, min(1.0, c.conviction_pct / 100.0))
    mag = c.magnitude_pips_low or 20.0  # default fallback
    mag_norm = max(0.5, min(2.0, mag / 30.0))  # ~1 at 30 pips, capped
    return sign * conv * mag_norm


def _compute_axis(cards: list[CardLite], axis_map: dict[str, float], name: str) -> ExposureAxis:
    contributions: list[tuple[str, float]] = []
    total = 0.0
    for c in cards:
        coef = axis_map.get(c.asset)
        if coef is None or coef == 0.0:
            continue
        w = _card_weight(c)
        contribution = coef * w
        if abs(contribution) > 0.001:
            contributions.append((c.asset, round(contribution, 3)))
        total += contribution
    # Normalize : divide by sum of |coef| seen for active assets
    seen_coefs = sum(abs(axis_map.get(c.asset, 0.0)) for c in cards if c.bias != "neutral")
    if seen_coefs > 0:
        total = total / max(1.0, seen_coefs)
    score = max(-1.0, min(1.0, total))
    contributions.sort(key=lambda kv: abs(kv[1]), reverse=True)
    return ExposureAxis(
        name=name,
        score=round(score, 3),
        contributors=contributions[:5],
    )


async def assess_portfolio_exposure(
    session: AsyncSession, *, max_age_hours: int = 24
) -> ExposureReport:
    cards: list[CardLite] = []
    for asset in _PHASE1_ASSETS:
        c = await _latest_card(session, asset, max_age_hours=max_age_hours)
        if c is not None:
            cards.append(c)

    axes = [
        _compute_axis(cards, _USD_AXIS, "USD"),
        _compute_axis(cards, _EQUITY_AXIS, "Equity"),
        _compute_axis(cards, _GOLD_AXIS, "Gold"),
        _compute_axis(cards, _JPY_AXIS, "JPY haven"),
        _compute_axis(cards, _COMMODITY_AXIS, "Commodity FX"),
    ]

    # Concentration warnings
    warnings: list[str] = []
    n_long_usd = sum(
        1
        for c in cards
        if (c.bias == "long" and _USD_AXIS.get(c.asset, 0) > 0)
        or (c.bias == "short" and _USD_AXIS.get(c.asset, 0) < 0)
    )
    n_short_usd = sum(
        1
        for c in cards
        if (c.bias == "short" and _USD_AXIS.get(c.asset, 0) > 0)
        or (c.bias == "long" and _USD_AXIS.get(c.asset, 0) < 0)
    )
    if n_long_usd >= 5:
        warnings.append(
            f"{n_long_usd}/{len(cards)} cards alignées USD-long → "
            "tu fais peut-être un single-currency bet déguisé."
        )
    if n_short_usd >= 5:
        warnings.append(
            f"{n_short_usd}/{len(cards)} cards alignées USD-short → "
            "concentration risk : un seul retournement USD t'expose toutes les positions."
        )
    n_neutral = sum(1 for c in cards if c.bias == "neutral")
    if n_neutral == len(cards) and len(cards) > 0:
        warnings.append(
            "Toutes les cards sont neutral — aucune conviction directionnelle "
            "actuellement, attendre une fenêtre de session plus claire."
        )

    return ExposureReport(
        n_cards=len(cards),
        cards=cards,
        axes=axes,
        concentration_warnings=warnings,
    )


def render_portfolio_exposure_block(
    r: ExposureReport,
) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    if r.n_cards == 0:
        return (
            "## Portfolio exposure (latest 24h cards)\n"
            "- Aucune carte fraîche pour calculer l'exposition.",
            [],
        )
    lines = [f"## Portfolio exposure ({r.n_cards}/8 cards latest 24h)"]
    for ax in r.axes:
        sign = "+" if ax.score >= 0 else ""
        bar_len = int(abs(ax.score) * 10)
        bar_char = "█" if ax.score >= 0 else "░"
        bar = bar_char * bar_len + " " * (10 - bar_len)
        lines.append(f"- {ax.name:<15s} {sign}{ax.score:+.2f}  [{bar}]")
        if ax.contributors:
            top = ", ".join(f"{a} {v:+.2f}" for a, v in ax.contributors[:3])
            lines.append(f"  · top : {top}")
    if r.concentration_warnings:
        lines.append("- ⚠ Concentration warnings :")
        for w in r.concentration_warnings:
            lines.append(f"  · {w}")

    sources = [f"session_card_audit:{c.asset}@{c.created_at.isoformat()}" for c in r.cards]
    return "\n".join(lines), sources
