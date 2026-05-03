"""Funding stress proxies — SOFR-IORB / FRA-OIS / SOFR-EFFR spreads.

These are the institutional plumbing signals that announce
USD-funding squeezes hours before they show up in DXY or VIX.
Eliot's vision asks for a 90% non-AT analysis stack ; without these
the macro layer is missing the most important early-warning lights.

VISION_2026 delta B — funding/liquidity stack institutional.

Sources :
  - SOFR    : Secured Overnight Financing Rate (NY Fed) — already
              in fred.SERIES_TO_POLL
  - IORB    : Interest on Reserve Balances — Fed admin rate. Not in
              FRED directly ; use IOER (renamed IORB after 2021) via
              the IORB constructed series in FRED (`IORB`).
  - EFFR    : Effective Federal Funds Rate (DFF in FRED)
  - HY OAS  : ICE BAML High Yield OAS (BAMLH0A0HYM2)
  - RRP    : Reverse Repo overnight (RRPONTSYD)

The SOFR-IORB spread is the Greenwood-Hanson-Stein (2015) "RIORF"
proxy — when it goes positive (SOFR > IORB), banks are paying up to
borrow cash, which is the textbook signal of a funding squeeze.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation


@dataclass(frozen=True)
class FundingStressReading:
    """Snapshot of the funding-stress block at a single point in time."""

    sofr: float | None
    iorb: float | None
    effr: float | None
    sofr_iorb_spread: float | None
    """SOFR - IORB. Positive = banks pay up to borrow cash → squeeze."""
    sofr_effr_spread: float | None
    """SOFR - EFFR. Positive = secured > unsecured → repo dislocation."""
    rrp_usage: float | None
    """RRP balance, in $bn. Drop = liquidity drained from RRP into markets."""
    hy_oas: float | None
    """HY OAS spread, %. > 4% historically = credit risk-off territory."""
    stress_score: float
    """Composite [-1, +1] : negative = relaxed, +0.5 = elevated, +1 = squeeze.

    Heuristic blend :
      0.4 * (sofr_iorb_spread > 0)              # positive spread → stress
      0.3 * (hy_oas > 4)                        # credit pricing in
      0.2 * (sofr_effr_spread > 0.05)           # repo dislocation
      0.1 * (rrp_usage drop > 100bn vs 30d ma)  # liquidity migration
    """
    note: str = ""


async def _latest(session: AsyncSession, series: str) -> float | None:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=14)
    stmt = (
        select(FredObservation.value)
        .where(
            FredObservation.series_id == series,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    val = (await session.execute(stmt)).scalar_one_or_none()
    return float(val) if val is not None else None


async def assess_funding_stress(session: AsyncSession) -> FundingStressReading:
    """Build a FundingStressReading from the latest FRED data."""
    sofr = await _latest(session, "SOFR")
    iorb = await _latest(session, "IORB")
    effr = await _latest(session, "DFF")
    rrp = await _latest(session, "RRPONTSYD")
    hy_oas = await _latest(session, "BAMLH0A0HYM2")

    sofr_iorb = (
        round(sofr - iorb, 4) if (sofr is not None and iorb is not None) else None
    )
    sofr_effr = (
        round(sofr - effr, 4) if (sofr is not None and effr is not None) else None
    )

    score = 0.0
    notes: list[str] = []
    if sofr_iorb is not None and sofr_iorb > 0:
        score += 0.4
        notes.append(f"SOFR-IORB +{sofr_iorb:.3f}% (squeeze)")
    if hy_oas is not None and hy_oas > 4.0:
        score += 0.3
        notes.append(f"HY OAS {hy_oas:.2f}% > 4% (credit risk-off)")
    elif hy_oas is not None and hy_oas > 3.0:
        score += 0.1
        notes.append(f"HY OAS {hy_oas:.2f}% elevated")
    if sofr_effr is not None and sofr_effr > 0.05:
        score += 0.2
        notes.append(f"SOFR-EFFR +{sofr_effr:.3f}% (repo dislocation)")
    if rrp is not None and rrp < 100:
        score += 0.1
        notes.append(f"RRP {rrp:.0f}bn near-zero (liquidity drained)")

    score = max(-1.0, min(1.0, score))
    note = "; ".join(notes) if notes else "no stress signals"

    return FundingStressReading(
        sofr=sofr,
        iorb=iorb,
        effr=effr,
        sofr_iorb_spread=sofr_iorb,
        sofr_effr_spread=sofr_effr,
        rrp_usage=rrp,
        hy_oas=hy_oas,
        stress_score=score,
        note=note,
    )


def render_funding_stress_block(r: FundingStressReading) -> tuple[str, list[str]]:
    """Markdown block + sources list, matching data_pool.py contract."""
    lines = ["## Funding stress (FRED, latest)"]
    sources: list[str] = []

    def fmt(v: float | None, suffix: str = "") -> str:
        return "n/a" if v is None else f"{v:.3f}{suffix}"

    lines.append(f"- SOFR (secured overnight) = {fmt(r.sofr, '%')} (FRED:SOFR)")
    sources.append("FRED:SOFR")
    lines.append(f"- IORB (Fed admin rate)    = {fmt(r.iorb, '%')} (FRED:IORB)")
    sources.append("FRED:IORB")
    lines.append(f"- EFFR (eff. fed funds)    = {fmt(r.effr, '%')} (FRED:DFF)")
    sources.append("FRED:DFF")
    lines.append(
        f"- SOFR-IORB spread         = {fmt(r.sofr_iorb_spread, '%')} "
        "(positive = funding squeeze)"
    )
    lines.append(
        f"- SOFR-EFFR spread         = {fmt(r.sofr_effr_spread, '%')} "
        "(positive = repo dislocation)"
    )
    lines.append(f"- RRP overnight usage      = {fmt(r.rrp_usage, ' $bn')} (FRED:RRPONTSYD)")
    sources.append("FRED:RRPONTSYD")
    lines.append(f"- HY OAS                   = {fmt(r.hy_oas, '%')} (FRED:BAMLH0A0HYM2)")
    sources.append("FRED:BAMLH0A0HYM2")
    lines.append(
        f"- Composite stress score   = **{r.stress_score:+.2f}** ({r.note})"
    )
    return "\n".join(lines), sources
