"""Session scenarios — Continuation / Reversal / Sideways probabilities.

Built on the SMC/ICT framework Eliot uses :
  - **Continuation** : the prior session's directional move extends.
    Triggered by : early-hour displacement + retest of structure +
    new high/low formation.
  - **Reversal** : the prior session reaches a higher-timeframe
    liquidity zone (PDH/PDL/Asian-range extreme) → market structure
    shift (MSS) → price flips. Highest probability on the NY session
    after a strong London move that hits HTF supply/demand.
  - **Sideways** : prior session already completed its distribution ;
    no clear catalyst → consolidation. Often happens after a CPI/FOMC
    print that did NOT surprise.

This service produces **probabilities** for the 3 scenarios on the
upcoming session window, derived from :
  - Where current spot sits relative to PDH / PDL / Asian range
  - Range realized so far in the session vs typical session range
  - Pass 1 régime (haven_bid / funding_stress / etc.)
  - Conviction post-stress (high conviction → bias for continuation,
    low conviction → bias for sideways)

Pure functions. Probabilities sum to 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .daily_levels import DailyLevels

SessionType = Literal["pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"]
RegimeQuadrant = Literal["haven_bid", "funding_stress", "goldilocks", "usd_complacency"]


@dataclass(frozen=True)
class SessionScenarios:
    asset: str
    session_type: SessionType
    p_continuation: float
    """Probability of trend extension. [0, 1]."""
    p_reversal: float
    """Probability of MSS + flip. [0, 1]."""
    p_sideways: float
    """Probability of consolidation. [0, 1]."""
    rationale: str
    """1-2 line explanation."""
    triggers_continuation: list[str]
    triggers_reversal: list[str]


def _spot_position(spot: float, low: float, high: float) -> float:
    """Returns 0..1 where spot sits in the [low, high] range. Clamped."""
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (spot - low) / (high - low)))


def assess_session_scenarios(
    levels: DailyLevels,
    *,
    session_type: SessionType,
    regime: RegimeQuadrant | None,
    conviction_pct: float,
) -> SessionScenarios:
    """Compute the 3 scenario probabilities for the upcoming session.

    Heuristic — not a calibrated model. Goal : surface the trader's
    decision tree explicitly so Eliot doesn't have to compute it
    mentally each session.
    """
    spot = levels.spot
    if spot is None or levels.pdh is None or levels.pdl is None:
        # Insufficient data → neutral split
        return SessionScenarios(
            asset=levels.asset,
            session_type=session_type,
            p_continuation=0.34,
            p_reversal=0.33,
            p_sideways=0.33,
            rationale="Niveaux journaliers insuffisants pour évaluer.",
            triggers_continuation=[],
            triggers_reversal=[],
        )

    pdh = levels.pdh
    pdl = levels.pdl
    asian_h = levels.asian_high or pdh
    asian_l = levels.asian_low or pdl

    # 1. Spot position vs PDH/PDL — how stretched is the move?
    pos_pdh_pdl = _spot_position(spot, pdl, pdh)
    # 2. Spot position vs Asian range
    _spot_position(spot, asian_l, asian_h)

    # 3. Conviction signal — high conviction tilts toward continuation
    conviction_norm = max(0.0, min(95.0, conviction_pct)) / 95.0  # in [0, 1]

    # 4. Régime bias
    regime_bias = {
        "goldilocks": 0.10,  # trend-friendly
        "haven_bid": 0.05,
        "usd_complacency": 0.0,
        "funding_stress": -0.10,  # mean-revert friendly
        None: 0.0,
    }.get(regime, 0.0)

    # ── Continuation logic ─────────────────────────────────────────
    # Higher when : spot near PDH/PDL extremes AND high conviction.
    # Stretched-extreme positions actually favor reversal — so we
    # use a tent function maxing at extremes only when conviction
    # supports the direction.
    extreme_score = abs(pos_pdh_pdl - 0.5) * 2.0  # 0 mid, 1 extreme
    # If conviction says "long" (heuristically inferred from positive
    # post-stress bias) and spot is high → continuation. We only have
    # conviction magnitude here, not direction, so we proxy with
    # extreme + conviction product.
    p_cont_base = 0.35 + 0.20 * extreme_score * conviction_norm + regime_bias

    # ── Reversal logic ────────────────────────────────────────────
    # Higher when spot already swept PDH or PDL (broken outside) AND
    # we are in a session where reversal classically happens (NY).
    swept_pdh = pos_pdh_pdl > 1.0 or spot > pdh
    swept_pdl = pos_pdh_pdl < 0.0 or spot < pdl
    swept = swept_pdh or swept_pdl
    session_bias = 0.10 if session_type == "pre_ny" else 0.05
    p_rev_base = 0.20 + (0.25 if swept else 0.05) + session_bias - regime_bias * 0.5

    # ── Sideways logic ────────────────────────────────────────────
    # Higher when : low conviction OR spot stuck mid-range.
    midness = 1.0 - extreme_score  # 1 at mid, 0 at extreme
    p_side_base = 0.20 + 0.15 * (1.0 - conviction_norm) + 0.10 * midness

    # Normalize so they sum to 1
    raw = max(0.01, p_cont_base) + max(0.01, p_rev_base) + max(0.01, p_side_base)
    p_cont = round(max(0.01, p_cont_base) / raw, 3)
    p_rev = round(max(0.01, p_rev_base) / raw, 3)
    p_side = round(max(0.01, p_side_base) / raw, 3)

    # Triggers — the SMC-style "what to watch for"
    triggers_cont: list[str] = []
    triggers_rev: list[str] = []
    asset = levels.asset

    def fmt(v):
        return f"{v:.5f}".rstrip("0").rstrip(".")

    if pos_pdh_pdl > 0.7:
        triggers_cont.append(
            f"Hold above {fmt(pdh)} (PDH) → continuation long target {fmt(levels.r1)} (R1)"
            if levels.r1
            else f"Hold above {fmt(pdh)} → continuation long"
        )
        triggers_rev.append(
            f"Rejection candle at {fmt(pdh)} (PDH) → reversal short, stop {fmt(levels.r1)} (R1)"
            if levels.r1
            else f"Rejection at {fmt(pdh)} → reversal short"
        )
    elif pos_pdh_pdl < 0.3:
        triggers_cont.append(
            f"Hold below {fmt(pdl)} (PDL) → continuation short target {fmt(levels.s1)} (S1)"
            if levels.s1
            else f"Hold below {fmt(pdl)} → continuation short"
        )
        triggers_rev.append(
            f"Rejection candle at {fmt(pdl)} (PDL) → reversal long, stop {fmt(levels.s1)} (S1)"
            if levels.s1
            else f"Rejection at {fmt(pdl)} → reversal long"
        )
    else:
        triggers_cont.append(f"Break above asian-range high {fmt(asian_h)} → continuation long")
        triggers_cont.append(f"Break below asian-range low {fmt(asian_l)} → continuation short")
        triggers_rev.append(f"Sweep {fmt(asian_h)}/{fmt(asian_l)} then MSS → reversal candidate")

    rationale = (
        f"Spot {fmt(spot)} à {pos_pdh_pdl * 100:.0f}% de la range PDH-PDL ; "
        f"conviction {conviction_pct:.0f}% ; régime {regime or 'inconnu'} → "
        f"P(continuation)={p_cont * 100:.0f}% P(reversal)={p_rev * 100:.0f}% "
        f"P(sideways)={p_side * 100:.0f}%."
    )

    return SessionScenarios(
        asset=asset,
        session_type=session_type,
        p_continuation=p_cont,
        p_reversal=p_rev,
        p_sideways=p_side,
        rationale=rationale,
        triggers_continuation=triggers_cont,
        triggers_reversal=triggers_rev,
    )


def render_session_scenarios_block(s: SessionScenarios) -> tuple[str, list[str]]:
    lines = [f"## Session scenarios ({s.asset}, {s.session_type})"]
    lines.append(
        f"- Continuation : **{s.p_continuation * 100:.0f}%** · "
        f"Reversal : **{s.p_reversal * 100:.0f}%** · "
        f"Sideways : **{s.p_sideways * 100:.0f}%**"
    )
    lines.append(f"- Rationale : {s.rationale}")
    if s.triggers_continuation:
        lines.append("- Triggers continuation :")
        for t in s.triggers_continuation:
            lines.append(f"  · {t}")
    if s.triggers_reversal:
        lines.append("- Triggers reversal :")
        for t in s.triggers_reversal:
            lines.append(f"  · {t}")
    sources = [f"empirical_model:session_scenarios:{s.asset}"]
    return "\n".join(lines), sources
