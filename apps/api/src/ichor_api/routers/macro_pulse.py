"""GET /v1/macro-pulse — bundled macro health snapshot.

Single endpoint that returns VIX term + risk appetite + yield curve +
funding stress + surprise index in one payload, so the /macro-pulse
dashboard makes a single fetch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.funding_stress import assess_funding_stress
from ..services.risk_appetite import assess_risk_appetite
from ..services.surprise_index import assess_surprise_index
from ..services.vix_term_structure import assess_vix_term
from ..services.yield_curve import assess_yield_curve

router = APIRouter(prefix="/v1/macro-pulse", tags=["macro-pulse"])


class VixTermOut(BaseModel):
    vix_1m: float | None
    vix_3m: float | None
    ratio: float | None
    spread: float | None
    regime: str
    interpretation: str


class RiskComponentOut(BaseModel):
    name: str
    series_id: str
    value: float | None
    contribution: float
    rationale: str


class RiskAppetiteOut(BaseModel):
    composite: float
    band: str
    components: list[RiskComponentOut]


class YieldPointOut(BaseModel):
    label: str
    tenor_years: float
    yield_pct: float | None


class YieldCurveOut(BaseModel):
    points: list[YieldPointOut]
    slope_3m_10y: float | None
    slope_2y_10y: float | None
    slope_5y_30y: float | None
    real_yield_10y: float | None
    inverted_segments: int
    shape: str
    note: str


class FundingStressOut(BaseModel):
    sofr: float | None
    iorb: float | None
    sofr_iorb_spread: float | None
    sofr_effr_spread: float | None
    rrp_usage: float | None
    hy_oas: float | None
    stress_score: float


class SurpriseSeriesOut(BaseModel):
    series_id: str
    label: str
    last_value: float | None
    z_score: float | None


class SurpriseOut(BaseModel):
    region: str
    composite: float | None
    band: str
    series: list[SurpriseSeriesOut]


class MacroPulseOut(BaseModel):
    generated_at: datetime
    vix_term: VixTermOut
    risk_appetite: RiskAppetiteOut
    yield_curve: YieldCurveOut
    funding_stress: FundingStressOut
    surprise_index: SurpriseOut


@router.get("", response_model=MacroPulseOut)
async def get_macro_pulse(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MacroPulseOut:
    vix = await assess_vix_term(session)
    risk = await assess_risk_appetite(session)
    yc = await assess_yield_curve(session)
    fs = await assess_funding_stress(session)
    si = await assess_surprise_index(session)

    return MacroPulseOut(
        generated_at=datetime.now(timezone.utc),
        vix_term=VixTermOut(
            vix_1m=vix.vix_1m,
            vix_3m=vix.vix_3m,
            ratio=vix.ratio,
            spread=vix.spread,
            regime=vix.regime,
            interpretation=vix.interpretation,
        ),
        risk_appetite=RiskAppetiteOut(
            composite=risk.composite,
            band=risk.band,
            components=[
                RiskComponentOut(
                    name=c.name,
                    series_id=c.series_id,
                    value=c.value,
                    contribution=c.contribution,
                    rationale=c.rationale,
                )
                for c in risk.components
            ],
        ),
        yield_curve=YieldCurveOut(
            points=[
                YieldPointOut(
                    label=p.label,
                    tenor_years=p.tenor_years,
                    yield_pct=p.yield_pct,
                )
                for p in yc.points
            ],
            slope_3m_10y=yc.slope_3m_10y,
            slope_2y_10y=yc.slope_2y_10y,
            slope_5y_30y=yc.slope_5y_30y,
            real_yield_10y=yc.real_yield_10y,
            inverted_segments=yc.inverted_segments,
            shape=yc.shape,
            note=yc.note,
        ),
        funding_stress=FundingStressOut(
            sofr=fs.sofr,
            iorb=fs.iorb,
            sofr_iorb_spread=fs.sofr_iorb_spread,
            sofr_effr_spread=fs.sofr_effr_spread,
            rrp_usage=fs.rrp_usage,
            hy_oas=fs.hy_oas,
            stress_score=fs.stress_score,
        ),
        surprise_index=SurpriseOut(
            region=si.region,
            composite=si.composite,
            band=si.band,
            series=[
                SurpriseSeriesOut(
                    series_id=s.series_id,
                    label=s.label,
                    last_value=s.last_value,
                    z_score=s.z_score,
                )
                for s in si.series
            ],
        ),
    )
