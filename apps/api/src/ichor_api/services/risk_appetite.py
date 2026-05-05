"""Risk appetite composite — sentiment + credit + vol blended into one score.

Aggregates 5 normalized inputs to surface a single -1 (extreme risk-off)
to +1 (extreme risk-on) score :

  - **VIX**        : low VIX → risk-on. Scale : VIX < 14 = +0.4, > 30 = -0.4
  - **HY OAS**     : tight = risk-on. < 3% = +0.3, > 6% = -0.3
  - **IG OAS**     : tight = risk-on. < 0.9% = +0.2, > 2% = -0.2
  - **T10Y2Y**     : steepening = risk-on (growth pricing). > 0.5 = +0.1
  - **UMCSENT**    : > 90 = +0.2 (consumer confident), < 70 = -0.2

This is a coarse but transparent composite. It surfaces a "risk weather"
panel for the dashboard and feeds the confluence engine.

VISION_2026 — closes the "what's the sentiment score?" gap. Used by the
trader as a top-level filter before drilling into pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation

RiskBand = Literal[
    "extreme_risk_off",
    "risk_off",
    "neutral",
    "risk_on",
    "extreme_risk_on",
]


@dataclass(frozen=True)
class RiskAppetiteComponent:
    name: str
    series_id: str
    value: float | None
    contribution: float
    """Signed [-1, +1]. Positive = risk-on tilt."""
    rationale: str


@dataclass(frozen=True)
class RiskAppetiteReading:
    composite: float
    """Sum of contributions, clamped to [-1, +1]."""
    band: RiskBand
    components: list[RiskAppetiteComponent] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _band(c: float) -> RiskBand:
    if c >= 0.5:
        return "extreme_risk_on"
    if c >= 0.2:
        return "risk_on"
    if c <= -0.5:
        return "extreme_risk_off"
    if c <= -0.2:
        return "risk_off"
    return "neutral"


async def _latest(session: AsyncSession, series_id: str, max_age_days: int = 35) -> float | None:
    """Latest value for `series_id`. Allow 35d staleness for monthly data."""
    cutoff = datetime.now(UTC).date() - timedelta(days=max_age_days)
    row = (
        await session.execute(
            select(FredObservation.value)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(desc(FredObservation.observation_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    return float(row) if row is not None else None


def _vix_contribution(v: float | None) -> tuple[float, str]:
    if v is None:
        return 0.0, "VIX n/a"
    if v >= 30:
        return -0.4, f"VIX {v:.1f} ≥ 30 (panique) → risk-off fort"
    if v >= 22:
        return -0.2, f"VIX {v:.1f} ≥ 22 (élevé) → risk-off"
    if v <= 14:
        return +0.4, f"VIX {v:.1f} ≤ 14 (calme) → risk-on fort"
    if v <= 18:
        return +0.2, f"VIX {v:.1f} ≤ 18 (normal-bas) → risk-on"
    return 0.0, f"VIX {v:.1f} (zone neutre)"


def _hy_oas_contribution(v: float | None) -> tuple[float, str]:
    if v is None:
        return 0.0, "HY OAS n/a"
    if v >= 6:
        return -0.3, f"HY OAS {v:.2f}% ≥ 6 → credit risk-off"
    if v >= 4:
        return -0.15, f"HY OAS {v:.2f}% élevé → credit prudent"
    if v <= 3:
        return +0.3, f"HY OAS {v:.2f}% ≤ 3 → credit risk-on"
    if v <= 3.5:
        return +0.15, f"HY OAS {v:.2f}% serré → credit favorable"
    return 0.0, f"HY OAS {v:.2f}% (zone neutre)"


def _ig_oas_contribution(v: float | None) -> tuple[float, str]:
    if v is None:
        return 0.0, "IG OAS n/a"
    if v >= 2.0:
        return -0.2, f"IG OAS {v:.2f}% large → credit qualité stressé"
    if v <= 0.9:
        return +0.2, f"IG OAS {v:.2f}% serré → IG risk-on"
    return 0.0, f"IG OAS {v:.2f}% (zone neutre)"


def _curve_contribution(v: float | None) -> tuple[float, str]:
    if v is None:
        return 0.0, "T10Y2Y n/a"
    if v >= 0.50:
        return +0.10, f"Curve 10Y-2Y {v:+.2f}pp pente positive → growth pricing"
    if v <= -0.50:
        return -0.10, f"Curve 10Y-2Y {v:+.2f}pp inversée → recession pricing"
    return 0.0, f"Curve 10Y-2Y {v:+.2f}pp (peu de pente)"


def _sentiment_contribution(v: float | None) -> tuple[float, str]:
    if v is None:
        return 0.0, "UMCSENT n/a"
    if v >= 90:
        return +0.20, f"UMCSENT {v:.1f} ≥ 90 (confiance haute) → risk-on"
    if v >= 80:
        return +0.10, f"UMCSENT {v:.1f} ≥ 80 (confiance ok)"
    if v <= 60:
        return -0.20, f"UMCSENT {v:.1f} ≤ 60 (méfiance forte) → risk-off"
    if v <= 70:
        return -0.10, f"UMCSENT {v:.1f} ≤ 70 (méfiance)"
    return 0.0, f"UMCSENT {v:.1f} (zone neutre)"


async def assess_risk_appetite(session: AsyncSession) -> RiskAppetiteReading:
    components: list[RiskAppetiteComponent] = []
    sources: list[str] = []

    # 1. VIX
    vix = await _latest(session, "VIXCLS", max_age_days=14)
    contrib, rat = _vix_contribution(vix)
    components.append(
        RiskAppetiteComponent(
            name="VIX 1M",
            series_id="VIXCLS",
            value=vix,
            contribution=contrib,
            rationale=rat,
        )
    )
    if vix is not None:
        sources.append("FRED:VIXCLS")

    # 2. HY OAS
    hy = await _latest(session, "BAMLH0A0HYM2", max_age_days=14)
    contrib, rat = _hy_oas_contribution(hy)
    components.append(
        RiskAppetiteComponent(
            name="HY OAS",
            series_id="BAMLH0A0HYM2",
            value=hy,
            contribution=contrib,
            rationale=rat,
        )
    )
    if hy is not None:
        sources.append("FRED:BAMLH0A0HYM2")

    # 3. IG OAS
    ig = await _latest(session, "BAMLC0A0CM", max_age_days=14)
    contrib, rat = _ig_oas_contribution(ig)
    components.append(
        RiskAppetiteComponent(
            name="IG OAS",
            series_id="BAMLC0A0CM",
            value=ig,
            contribution=contrib,
            rationale=rat,
        )
    )
    if ig is not None:
        sources.append("FRED:BAMLC0A0CM")

    # 4. Curve slope
    cv = await _latest(session, "T10Y2Y", max_age_days=14)
    contrib, rat = _curve_contribution(cv)
    components.append(
        RiskAppetiteComponent(
            name="Curve 10Y-2Y",
            series_id="T10Y2Y",
            value=cv,
            contribution=contrib,
            rationale=rat,
        )
    )
    if cv is not None:
        sources.append("FRED:T10Y2Y")

    # 5. UMCSENT (35d staleness — it's monthly)
    sent = await _latest(session, "UMCSENT", max_age_days=45)
    contrib, rat = _sentiment_contribution(sent)
    components.append(
        RiskAppetiteComponent(
            name="UMCSENT",
            series_id="UMCSENT",
            value=sent,
            contribution=contrib,
            rationale=rat,
        )
    )
    if sent is not None:
        sources.append("FRED:UMCSENT")

    composite = max(-1.0, min(1.0, sum(c.contribution for c in components)))
    return RiskAppetiteReading(
        composite=round(composite, 3),
        band=_band(composite),
        components=components,
        sources=sources,
    )


def render_risk_appetite_block(r: RiskAppetiteReading) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    lines = [f"## Risk appetite ({r.band}, composite {r.composite:+.2f})"]
    for c in r.components:
        if c.value is None:
            lines.append(f"- {c.name:>13s} : n/a")
            continue
        sign = "+" if c.contribution >= 0 else ""
        lines.append(f"- {c.name:>13s} : {sign}{c.contribution:+.2f}  — {c.rationale}")
    return "\n".join(lines), list(r.sources)
