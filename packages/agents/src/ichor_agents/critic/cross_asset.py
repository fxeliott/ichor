"""Cross-asset coherence reviewer.

Phase-1 extension to the per-card Critic : given the latest set of
session cards (one per asset), flag pairs whose biases are macro-
inconsistent. Examples :

  - EUR/USD long + DXY long ............ contradictory (EUR is a DXY component)
  - XAU/USD long + DXY long + real yields up ......... rare regime, flag for review
  - SPX500 long + VIX up ............... cross-check needed (rally despite stress)

The reviewer is rule-based and intentionally conservative — it returns
warnings, not blocks. Calibration of these rules will tighten over Phase 2
once we have N=100+ realized session outcomes to backtest against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

CoherenceSeverity = Literal["info", "warning", "critical"]


@dataclass(frozen=True)
class CoherenceFinding:
    """One cross-asset incoherence."""

    rule: str
    description: str
    assets: tuple[str, ...]
    severity: CoherenceSeverity


@dataclass
class CrossAssetVerdict:
    findings: list[CoherenceFinding] = field(default_factory=list)
    n_cards_reviewed: int = 0
    reviewed_at: datetime | None = None

    @property
    def is_coherent(self) -> bool:
        return not self.findings


# ──────────────────────── input shape ────────────────────────


@dataclass(frozen=True)
class CardSnapshot:
    """Subset of `SessionCard` fields needed for cross-asset checks.

    Decoupled from the brain package so this module can be imported
    without pulling in `ichor_brain` (avoid a dependency cycle).
    """

    asset: str
    bias_direction: Literal["long", "short", "neutral"]
    conviction_pct: float
    regime_quadrant: str | None = None


# ──────────────────────── rules ──────────────────────────────


# DXY components — when both legs are long the dollar-side direction
# becomes incoherent. Pair format : (asset, expected_dxy_sign_when_long).
# +1 means "long this asset implies USD weakness".
_DXY_LEG_SIGN: dict[str, int] = {
    "EUR_USD": +1,  # EUR up = DXY down
    "GBP_USD": +1,
    "AUD_USD": +1,
    "USD_JPY": -1,  # USD up = DXY up
    "USD_CAD": -1,
}


def _dollar_index_score(cards: dict[str, CardSnapshot]) -> float | None:
    """Average implied DXY direction across the available DXY legs.

    Each leg contributes `(-sign × polarity × conviction)` so the score
    reads naturally :
      Positive ⇒ implicit "long DXY" stance.
      Negative ⇒ implicit "short DXY" stance.
      None    ⇒ insufficient data.

    See `_check_dxy_legs_consistency` — it uses the same `-sign × polarity`
    convention; keeping the two helpers in lockstep prevents sign drift.
    """
    contributions: list[float] = []
    for code, sign in _DXY_LEG_SIGN.items():
        snap = cards.get(code)
        if snap is None or snap.bias_direction == "neutral":
            continue
        polarity = 1 if snap.bias_direction == "long" else -1
        contributions.append(-sign * polarity * snap.conviction_pct / 100.0)
    if not contributions:
        return None
    return sum(contributions) / len(contributions)


def _check_dxy_legs_consistency(cards: dict[str, CardSnapshot]) -> CoherenceFinding | None:
    """If two DXY legs imply opposite USD directions with high conviction,
    something is off."""
    long_usd: list[str] = []
    short_usd: list[str] = []
    for code, sign in _DXY_LEG_SIGN.items():
        snap = cards.get(code)
        if snap is None or snap.bias_direction == "neutral":
            continue
        polarity = 1 if snap.bias_direction == "long" else -1
        # USD direction implied : -sign * polarity
        usd_dir = -sign * polarity
        if snap.conviction_pct < 40:
            continue  # ignore weak convictions
        (long_usd if usd_dir > 0 else short_usd).append(code)

    if long_usd and short_usd:
        return CoherenceFinding(
            rule="dxy_legs_disagree",
            description=(
                f"USD direction is contradictory : {', '.join(long_usd)} imply "
                f"USD↑ while {', '.join(short_usd)} imply USD↓. Re-examine the "
                f"DXY thesis."
            ),
            assets=tuple(sorted(long_usd + short_usd)),
            severity="warning",
        )
    return None


def _check_xau_dxy_double_long(cards: dict[str, CardSnapshot]) -> CoherenceFinding | None:
    """XAU and DXY both long is the canonical "haven_bid extreme" — rare
    enough that it deserves a sanity check. Implicit DXY = average of legs."""
    xau = cards.get("XAU_USD")
    if xau is None or xau.bias_direction != "long" or xau.conviction_pct < 50:
        return None
    dxy_score = _dollar_index_score(cards)
    if dxy_score is None or dxy_score <= 0.2:
        return None
    return CoherenceFinding(
        rule="xau_and_dxy_both_long",
        description=(
            "XAU and the implicit DXY stance are both meaningfully long. This "
            "happens but is rare outside a haven_bid régime — confirm both "
            "trades reference the same régime quadrant."
        ),
        assets=("XAU_USD", *sorted(_DXY_LEG_SIGN.keys())),
        severity="info",
    )


def _check_spx_long_with_funding_stress(
    cards: dict[str, CardSnapshot],
) -> CoherenceFinding | None:
    """A long SPX call inside a `funding_stress` régime is a high-conviction
    contrarian view. Flag it so the Critic prompt can ask for explicit
    justification."""
    spx = cards.get("SPX500_USD") or cards.get("NAS100_USD")
    if spx is None or spx.bias_direction != "long" or spx.conviction_pct < 50:
        return None
    if spx.regime_quadrant != "funding_stress":
        return None
    return CoherenceFinding(
        rule="risk_long_in_funding_stress",
        description=(
            f"{spx.asset} long ({spx.conviction_pct:.0f}%) inside régime "
            f"funding_stress. Confirm the contrarian premise has explicit "
            f"sources (e.g. credit-spread tightening that contradicts the régime)."
        ),
        assets=(spx.asset,),
        severity="warning",
    )


def review_cards(cards: list[CardSnapshot]) -> CrossAssetVerdict:
    """Run the cross-asset rule set over a list of fresh session cards."""
    by_asset = {c.asset: c for c in cards}

    findings: list[CoherenceFinding] = []
    for rule_fn in (
        _check_dxy_legs_consistency,
        _check_xau_dxy_double_long,
        _check_spx_long_with_funding_stress,
    ):
        f = rule_fn(by_asset)
        if f is not None:
            findings.append(f)

    return CrossAssetVerdict(
        findings=findings,
        n_cards_reviewed=len(cards),
        reviewed_at=datetime.now(timezone.utc),
    )
