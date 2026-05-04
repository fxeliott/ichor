"""VIX term structure — contango / backwardation detection.

VIX (1-month implied vol) vs VIX3M (3-month) tells you a lot about
forward risk pricing :

  - **Contango** (VIX < VIX3M, ratio < 1.0) : market expects future
    vol to rise → relaxed near-term, hedging the medium-term. Typical
    in bull markets / risk-on regimes.
  - **Backwardation** (VIX > VIX3M, ratio > 1.0) : market expects
    near-term turbulence → panic / mean-revert friendly. Historical
    backwardation episodes : 2008, March 2020 COVID, August 2024 carry
    unwind. Bullish equities on a 1-3 month basis (mean revert).
  - **Normal** : ratio 0.85-0.95 (mild contango).
  - **Stretched contango** : ratio < 0.80 (overly complacent — late-cycle
    warning).

Pure-stdlib computation. Single source = FRED VIXCLS + VXVCLS.

VISION_2026 — closes the "what's the forward vol picture?" gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation


VixRegime = Literal[
    "stretched_contango",
    "contango",
    "normal",
    "flat",
    "backwardation",
    "extreme_backwardation",
]


@dataclass(frozen=True)
class VixTermReading:
    vix_1m: float | None
    vix_3m: float | None
    ratio: float | None
    """VIX / VIX3M. <1 contango, >1 backwardation."""
    spread: float | None
    """VIX - VIX3M, in vol points."""
    regime: VixRegime
    """Bucketed regime tag."""
    interpretation: str
    """1-line plain-language explanation."""
    observation_date: datetime | None
    sources: list[str] = field(default_factory=list)


def _classify(ratio: float | None) -> VixRegime:
    if ratio is None:
        return "flat"
    if ratio >= 1.15:
        return "extreme_backwardation"
    if ratio >= 1.02:
        return "backwardation"
    if ratio >= 0.95:
        return "flat"
    if ratio >= 0.85:
        return "normal"
    if ratio >= 0.78:
        return "contango"
    return "stretched_contango"


def _interpretation(regime: VixRegime, vix: float | None) -> str:
    if regime == "extreme_backwardation":
        return (
            "Backwardation extrême — panique près-terme, opportunité "
            "mean-revert long equity 1-3 mois historiquement positive."
        )
    if regime == "backwardation":
        return (
            "Backwardation — stress près-terme, hedge cher. Habituellement "
            "des opportunités long equity à court terme."
        )
    if regime == "flat":
        return "Term structure flat — transition, pas de signal directionnel clair."
    if regime == "normal":
        return "Contango normal — risk-on, courbe vol classique en hausse."
    if regime == "contango":
        return "Contango marqué — complacence, hedge bon marché."
    # stretched_contango
    if vix is not None and vix < 13:
        return (
            f"Stretched contango (VIX {vix:.1f}) — complacence prononcée, "
            "vigilance sur signaux de tournement."
        )
    return (
        "Stretched contango — complacence marquée, watch out for mean-revert "
        "vol-spike events."
    )


async def _latest(
    session: AsyncSession, series_id: str, max_age_days: int = 14
) -> tuple[float, datetime] | None:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
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
    return (
        float(row.value),
        datetime.combine(
            row.observation_date, datetime.min.time(), tzinfo=timezone.utc
        ),
    )


async def assess_vix_term(session: AsyncSession) -> VixTermReading:
    v1 = await _latest(session, "VIXCLS")
    v3 = await _latest(session, "VXVCLS")
    sources: list[str] = []
    if v1 is not None:
        sources.append("FRED:VIXCLS")
    if v3 is not None:
        sources.append("FRED:VXVCLS")

    if v1 is None or v3 is None:
        return VixTermReading(
            vix_1m=v1[0] if v1 else None,
            vix_3m=v3[0] if v3 else None,
            ratio=None,
            spread=None,
            regime="flat",
            interpretation="Données FRED VIX/VIX3M incomplètes.",
            observation_date=v1[1] if v1 else (v3[1] if v3 else None),
            sources=sources,
        )

    ratio = v1[0] / v3[0] if v3[0] > 0 else None
    spread = v1[0] - v3[0]
    regime = _classify(ratio)
    return VixTermReading(
        vix_1m=v1[0],
        vix_3m=v3[0],
        ratio=round(ratio, 3) if ratio else None,
        spread=round(spread, 2),
        regime=regime,
        interpretation=_interpretation(regime, v1[0]),
        observation_date=max(v1[1], v3[1]),
        sources=sources,
    )


def render_vix_term_block(r: VixTermReading) -> tuple[str, list[str]]:
    if r.vix_1m is None or r.vix_3m is None:
        return (
            "## VIX term structure\n- " + r.interpretation,
            list(r.sources),
        )
    lines = [
        f"## VIX term structure ({r.regime})",
        f"- VIX 1M = {r.vix_1m:.2f} · VIX 3M = {r.vix_3m:.2f} · "
        f"ratio = {r.ratio:.3f} · spread = {r.spread:+.2f}",
        f"- Reading : {r.interpretation}",
    ]
    if r.observation_date:
        lines.append(f"- Latest obs : {r.observation_date:%Y-%m-%d}")
    return "\n".join(lines), list(r.sources)
