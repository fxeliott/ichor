"""Central-bank FX intervention probability — empirical model.

UNIQUE to Ichor (no competitor surfaces this systematically).

For each currency pair where the issuing central bank has a documented
history of FX intervention, we compute a probability that the next
session prints intervention based on :
  1. how far the current spot is from the historical "pain threshold"
     (where past interventions clustered),
  2. recent rhetoric (mentioned in `cb_speeches`).

Phase-1 V1 ships threshold-based logistic only. Rhetoric weighting
moves to V2 once `cb_speeches` ingestion stabilizes (currently 126
items as of 2026-05-04).

Methodology — sigmoid around the empirical threshold :

    P(intervention next 8h) = sigmoid( (spot - threshold) / scale )

For inverse pairs (where intervention defends a *floor*, e.g. BoJ
defending a *weak yen* = USD/JPY too high), the sign flips so high
spot → high probability. For pairs where the CB defends a strong
local currency (SNB historically defending against EUR/CHF *too low*
= protecting export competitiveness), the relationship inverts.

References on documented intervention spots :
  - BoJ : 1998 (147), 2011 (76 floor defense), Sep–Oct 2022 (145–152
    range), 2024 (interventions reported around 152–161)
  - SNB : Sep 2011 EUR/CHF peg installed at 1.20, removed Jan 2015 ;
    market intervention activity around 0.95–1.00 EUR/CHF in 2024
  - BoE : 1992 ERM (Black Wednesday) ; intervention since then is rare
    and usually verbal only

These are encoded as *empirical priors*, not predictions of policy.
The Critic Agent should always frame intervention as a *tail-risk
flag*, never as a base case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class InterventionProfile:
    """One CB's empirical intervention behaviour on one pair."""

    asset: str
    central_bank: str
    threshold: float
    """Spot level around which past interventions clustered."""
    scale: float
    """Sigmoid scale — smaller = sharper risk gradient near threshold."""
    direction: int
    """+1 = high spot → high P (e.g. BoJ on USD/JPY).
       -1 = low spot → high P (e.g. SNB defending CHF too strong)."""
    note: str = ""


_PROFILES: dict[str, InterventionProfile] = {
    "USD_JPY": InterventionProfile(
        asset="USD_JPY",
        central_bank="BoJ / MoF",
        threshold=152.0,
        scale=2.0,
        direction=+1,
        note="MoF historically intervenes when USD/JPY > 150, "
        "with sharp escalation 152+. 2022 + 2024 spotted.",
    ),
    "EUR_CHF": InterventionProfile(
        asset="EUR_CHF",
        central_bank="SNB",
        threshold=0.95,
        scale=0.02,
        direction=-1,
        note="SNB defends EUR/CHF floor — intervention risk rises "
        "as EUR/CHF drops below 0.95. 1.20 peg 2011-2015.",
    ),
    "USD_CNH": InterventionProfile(
        asset="USD_CNH",
        central_bank="PBoC",
        threshold=7.30,
        scale=0.05,
        direction=+1,
        note="PBoC tightens fix when USD/CNH > 7.30. Daily fix is itself "
        "an intervention tool ; spot vs fix gap = signal.",
    ),
}


@dataclass(frozen=True)
class InterventionRisk:
    """Probability + categorical band + cited profile."""

    asset: str
    spot: float
    profile: InterventionProfile
    probability_pct: float
    """Probability in [0, 100] of intervention in the next 8h."""
    band: str  # "low" / "elevated" / "high" / "imminent"
    rationale: str


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def _band(p_pct: float) -> str:
    if p_pct >= 60:
        return "imminent"
    if p_pct >= 30:
        return "high"
    if p_pct >= 10:
        return "elevated"
    return "low"


def assess(asset: str, spot: float) -> InterventionRisk | None:
    """Return InterventionRisk for the given pair if a profile exists.

    Returns None for pairs without an intervention history (most G10
    crosses fall here — the EUR/USD has no intervention precedent on
    either side).
    """
    p = _PROFILES.get(asset.upper())
    if p is None:
        return None
    delta = (spot - p.threshold) / p.scale
    raw = _sigmoid(delta if p.direction > 0 else -delta)
    pct = round(raw * 100.0, 1)
    band = _band(pct)
    rationale = (
        f"Spot {spot:.4f} vs {p.central_bank} threshold {p.threshold:.4f} "
        f"(scale {p.scale:.4f}, direction {p.direction:+d}) → "
        f"{pct:.1f}% intervention probability ({band})"
    )
    return InterventionRisk(
        asset=asset.upper(),
        spot=spot,
        profile=p,
        probability_pct=pct,
        band=band,
        rationale=rationale,
    )


def render_intervention_block(risk: InterventionRisk) -> tuple[str, list[str]]:
    """Markdown block + sources list. Sources cite the empirical model."""
    lines = [f"## CB intervention risk ({risk.asset})"]
    lines.append(
        f"- Spot {risk.spot:.4f} · "
        f"{risk.profile.central_bank} threshold {risk.profile.threshold:.4f} "
        f"({risk.profile.direction:+d})"
    )
    lines.append(
        f"- **{risk.probability_pct:.1f}%** intervention probability next 8h "
        f"→ band: **{risk.band}**"
    )
    lines.append(f"- Note: {risk.profile.note}")
    sources = [f"empirical_model:cb_intervention:{risk.asset}"]
    return "\n".join(lines), sources


def supported_pairs() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES.keys()))
