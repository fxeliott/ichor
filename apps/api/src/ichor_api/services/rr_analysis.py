"""Risk/Reward analysis — concrete entry / stop / target suggestions.

Eliot's strategy : aim RR ≥ 3, BE at RR=1, close 90% at RR=3, leave
10% with trailing stop. This service translates Ichor's bias +
magnitude into a concrete trade plan : where to stop, where to TP,
position-sizing implications.

Pure functions, mirrors his playbook 1:1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BiasDirection = Literal["long", "short", "neutral"]


@dataclass(frozen=True)
class RRPlan:
    """One concrete trade plan derived from a session card."""

    asset: str
    bias: BiasDirection
    entry_zone_low: float | None
    """Lower bound of the suggested entry zone."""
    entry_zone_high: float | None
    """Upper bound of the suggested entry zone."""
    stop_loss: float | None
    """Hard SL — beyond it, the thesis is invalidated."""
    tp1: float | None
    """First take-profit (RR ≈ 1, where to BE the rest)."""
    tp3: float | None
    """Main take-profit (RR ≈ 3, where to close 90%)."""
    tp_extended: float | None
    """Trail target (RR ≈ 5+) — the 10% runner."""
    risk_pips: float | None
    """Distance entry-mid → stop (in pips/points). Sizes the trade."""
    reward_pips_tp3: float | None
    rr_target: float
    """Target RR — Eliot's standard is 3."""
    notes: str = ""


def _pip_size(asset: str) -> float:
    a = asset.upper()
    if a.endswith("JPY"):
        return 0.01
    if a == "XAU_USD":
        return 0.10
    if a in ("NAS100_USD", "SPX500_USD", "US100", "US30"):
        return 1.0
    return 0.0001


def _to_pips(price_diff: float, asset: str) -> float:
    return abs(price_diff) / _pip_size(asset)


def _from_pips(pips: float, asset: str) -> float:
    return pips * _pip_size(asset)


def assess_rr_plan(
    *,
    asset: str,
    spot: float | None,
    bias: BiasDirection,
    conviction_pct: float,
    magnitude_pips_low: float | None,
    magnitude_pips_high: float | None,
    pdh: float | None = None,
    pdl: float | None = None,
    asian_high: float | None = None,
    asian_low: float | None = None,
    rr_target: float = 3.0,
) -> RRPlan:
    """Compute a concrete RR plan that respects the magnitude band.

    Logic :
      - Entry zone : ±5 pips around spot (Eliot enters on retracement
        in that zone).
      - Risk = magnitude_pips_low / 2 (a tight stop ; if the move
        doesn't go your way within half-magnitude, you were wrong).
      - TP1 = entry + 1 × risk (BE point).
      - TP3 = entry + 3 × risk (close 90%).
      - TP_extended = max(magnitude_pips_high, 5 × risk) (trail 10%).
    """
    if spot is None or bias == "neutral" or magnitude_pips_low is None:
        return RRPlan(
            asset=asset,
            bias=bias,
            entry_zone_low=None,
            entry_zone_high=None,
            stop_loss=None,
            tp1=None,
            tp3=None,
            tp_extended=None,
            risk_pips=None,
            reward_pips_tp3=None,
            rr_target=rr_target,
            notes="Bias neutral or missing magnitude — pas de plan RR.",
        )

    pip = _pip_size(asset)
    entry_pad = 5.0 * pip  # ±5 pips around spot
    entry_low = spot - entry_pad
    entry_high = spot + entry_pad
    entry_mid = spot

    # Risk : half the lower-bound magnitude
    risk_pips = max(5.0, magnitude_pips_low / 2.0)
    risk_price = _from_pips(risk_pips, asset)

    direction = 1 if bias == "long" else -1

    stop_loss = entry_mid - direction * risk_price
    tp1 = entry_mid + direction * risk_price  # RR = 1
    tp3 = entry_mid + direction * risk_price * rr_target  # RR = 3
    target_high_pips = magnitude_pips_high or magnitude_pips_low * 2.0
    tp_extended_pips = max(target_high_pips, risk_pips * 5.0)
    tp_extended = entry_mid + direction * _from_pips(tp_extended_pips, asset)

    # Sanity check vs daily levels — warn if SL is on the wrong side
    notes_parts: list[str] = []
    if bias == "long" and pdl is not None and stop_loss > pdl:
        notes_parts.append(
            f"SL {stop_loss:.5f} above PDL {pdl:.5f} — consider "
            f"lowering SL behind PDL for HTF protection."
        )
    if bias == "short" and pdh is not None and stop_loss < pdh:
        notes_parts.append(
            f"SL {stop_loss:.5f} below PDH {pdh:.5f} — consider "
            f"raising SL above PDH for HTF protection."
        )

    if conviction_pct < 30:
        notes_parts.append(
            f"Conviction {conviction_pct:.0f}% < 30 — réduire le size ou "
            "attendre plus de confluence avant l'entry."
        )

    return RRPlan(
        asset=asset,
        bias=bias,
        entry_zone_low=round(entry_low, 5),
        entry_zone_high=round(entry_high, 5),
        stop_loss=round(stop_loss, 5),
        tp1=round(tp1, 5),
        tp3=round(tp3, 5),
        tp_extended=round(tp_extended, 5),
        risk_pips=round(risk_pips, 1),
        reward_pips_tp3=round(risk_pips * rr_target, 1),
        rr_target=rr_target,
        notes=" ".join(notes_parts),
    )


def render_rr_block(p: RRPlan) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    if p.bias == "neutral" or p.entry_zone_low is None:
        return (
            f"## RR plan ({p.asset})\n- bias neutral ou magnitude n/c — pas de plan",
            [],
        )

    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.5f}".rstrip("0").rstrip(".")

    lines = [f"## RR plan ({p.asset}, target RR={p.rr_target:.0f})"]
    lines.append(f"- Bias               = **{p.bias.upper()}**")
    lines.append(f"- Entry zone         = {fmt(p.entry_zone_low)} → {fmt(p.entry_zone_high)}")
    lines.append(f"- Stop loss          = {fmt(p.stop_loss)} ({p.risk_pips:.0f} pips)")
    lines.append(f"- TP1 (BE)           = {fmt(p.tp1)} (RR=1)")
    lines.append(
        f"- TP3 (close 90%)    = {fmt(p.tp3)} (RR={p.rr_target:.0f}, {p.reward_pips_tp3:.0f} pips)"
    )
    lines.append(f"- TP extended (10%)  = {fmt(p.tp_extended)} (trail)")
    if p.notes:
        lines.append(f"- ⚠ {p.notes}")
    sources = [f"empirical_model:rr_plan:{p.asset}"]
    return "\n".join(lines), sources
