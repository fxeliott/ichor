"""Cross-asset USD coherence — the "tout interconnecté" reconciliation.

WHY THIS EXISTS
---------------
Each session card is produced independently, one asset at a time
(``run_session_cards_batch`` → ``run_session_card._run``), and
``card_coherence.reconcile_coherence`` only reconciles each card against
*its own* scenario distribution + drivers. Nothing checks that the five
cards tell a **coherent story about the US dollar**.

That is exactly the defect the 2026-05-29 NY-session post-mortem traced two
of three misses to: Ichor shipped *bearish EUR* + *bearish gold* (both =
strong-dollar bets) while also *bullish equities* (= risk-on / soft-dollar)
— three readings that cannot all be right at once. The macro principle is
blunt (and is the one Eliot keeps repeating): **« l'argent ne sort pas du
ciel — si le dollar explose, c'est qu'on a vendu autre chose »**. The five
assets are not five independent coin-flips; they are five windows onto the
same dollar/risk regime.

WHAT THIS DOES
--------------
1. Maps each card's directional bias to its **implied USD stance**
   (``usd_up`` / ``usd_down`` / ``neutral``), respecting the quote
   convention (EUR/GBP/XAU/indices are quoted so *long the asset* ⇒ *softer
   USD*; USD/CAD & USD/JPY have USD as the **base** ⇒ the sign flips).
2. Weights each vote by (a) how tightly the asset tracks the dollar and
   (b) the card's own conviction, then computes the **dollar consensus**.
3. Flags the assets whose bias **contradicts** that consensus with real
   conviction — the incoherent outliers — and produces a plain-French coach
   explanation of the tension.
4. Offers a *demote-only* recommendation a caller MAY apply (never an
   auto-flip): an outlier's directional conviction can be shaved so the
   honest weak-coherence read is what gets scored — mirroring
   ``card_coherence``'s demote-only philosophy.

ADR-017 boundary
----------------
Output is descriptive geometry only — ``usd_up`` / ``usd_down`` /
``incoherent`` + a French explanation in the existing probabilistic
vocabulary (dollar fort/faible, biais haussier/baissier, prudence). It NEVER
emits BUY/SELL/TP/SL/entry/stop. Guarded by
``test_cross_asset_dollar_coherence.py`` asserting
``adr017_filter.find_violations(explanation) == ()``.

The weighting rationale is grounded in the macro literature already cited
across the Ichor data-pool (Engel-West 2005 random-walk-dominance ⇒ FX pairs
are the cleanest dollar read; the dollar-smile / risk-on-off channel ⇒
equities are a loose proxy; gold's real-rate channel is primary but the
safe-haven channel can break the sign ⇒ medium weight + caveat).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

UsdStance = Literal["usd_up", "usd_down", "neutral"]
DollarConsensus = Literal["usd_up", "usd_down", "mixed", "neutral"]

# ── Asset → weight in the dollar consensus ──────────────────────────────
# How cleanly does the asset read the DOLLAR specifically?
#   EUR/USD, GBP/USD : ARE dollar pairs → highest weight (GBP slightly lower:
#     more idiosyncratic BoE/fiscal drivers per the methodology transcript).
#   USD/CAD, USD/JPY : also dollar pairs (USD is the BASE → sign flips below).
#   XAU/USD          : inverse-dollar via the real-rate channel (primary), but
#     the safe-haven channel can co-move gold WITH the dollar in a panic →
#     medium weight + caveat.
#   SPX500, NAS100   : risk-on/off proxy for the dollar (loose link — equities
#     can rally on a strong economy *and* a strong dollar) → low weight.
_ASSET_USD_WEIGHT: dict[str, float] = {
    "EUR_USD": 1.0,
    "GBP_USD": 0.9,
    "USD_CAD": 0.9,
    "USD_JPY": 0.9,
    "XAU_USD": 0.6,
    "SPX500_USD": 0.4,
    "NAS100_USD": 0.4,
}

# Assets quoted as USD/XXX — USD is the BASE, so *long the asset* ⇒ *stronger
# USD* (the opposite of the XXX/USD pairs and of gold/indices).
_USD_IS_BASE: frozenset[str] = frozenset({"USD_CAD", "USD_JPY"})

# Default weight for an asset not in the table (treated as a loose dollar read).
_DEFAULT_WEIGHT = 0.4

_ASSET_DISPLAY: dict[str, str] = {
    "EUR_USD": "EUR/USD",
    "GBP_USD": "GBP/USD",
    "USD_CAD": "USD/CAD",
    "USD_JPY": "USD/JPY",
    "XAU_USD": "l'or (XAU/USD)",
    "SPX500_USD": "le S&P 500",
    "NAS100_USD": "le Nasdaq",
}

# A signed vote below this (after weight × conviction-fraction) is treated as
# directionless — a near-neutral card should not tip the consensus.
_NEUTRAL_VOTE_EPS = 0.05
# Consensus is "mixed" when |net| is below this share of the total weight cast
# (the dollar story is genuinely split, not a clean lean).
_CONSENSUS_MIXED_FRACTION = 0.20
# An asset is an incoherent OUTLIER only if its own conviction clears this
# floor — a 12 %-conviction contrarian card is noise, not a real contradiction.
_OUTLIER_MIN_CONVICTION = 25.0
# Demote-only: how hard to shave an incoherent outlier's conviction (a caller
# MAY apply this; this module never mutates persisted cards itself).
_OUTLIER_DEMOTION_SCALE = 0.70


def _display(asset: str) -> str:
    return _ASSET_DISPLAY.get(asset, asset)


def implied_usd_stance(asset: str, bias: str) -> UsdStance:
    """Map a card's directional bias to its implied stance on the US dollar.

    ``long``/``short`` are the canonical ``bias_direction`` values
    (``card_coherence`` uses the same). For every XXX/USD pair plus gold and
    the equity indices, *long the asset* implies a *softer dollar*; for the
    USD/XXX pairs (USD is the base) the sign flips.
    """
    if bias == "neutral":
        return "neutral"
    if bias not in ("long", "short"):
        return "neutral"
    long_means_usd_up = asset in _USD_IS_BASE
    if bias == "long":
        return "usd_up" if long_means_usd_up else "usd_down"
    # bias == "short"
    return "usd_down" if long_means_usd_up else "usd_up"


@dataclass(frozen=True)
class AssetUsdView:
    """One asset's contribution to the cross-asset dollar read."""

    asset: str
    bias: str
    conviction: float
    stance: UsdStance
    weight: float
    # signed vote : +weight*conv_frac when usd_up, −… when usd_down, 0 neutral.
    signed_vote: float


@dataclass(frozen=True)
class DollarCoherenceVerdict:
    """Cross-asset USD reconciliation result (read-time, descriptive)."""

    consensus: DollarConsensus
    consensus_strength: float  # 0..1 — |net| / total weight cast
    coherent: bool
    views: tuple[AssetUsdView, ...]
    outliers: tuple[str, ...]  # asset codes whose bias fights the consensus
    # Per-outlier demote-only suggestion {asset: shaved_conviction}. A caller
    # MAY apply it; this module never mutates persisted cards.
    recommended_demotions: Mapping[str, float] = field(default_factory=dict)
    coach_explanation: str = ""
    n_directional: int = 0  # how many cards cast a non-neutral vote


def _coerce_conviction(value: Any) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    if c < 0.0:
        return 0.0
    # Conviction is a 0..95 percentage (ADR-022 cap). Tolerate a 0..1 fraction
    # by scaling up so callers can pass either convention.
    if c <= 1.0:
        c *= 100.0
    return min(c, 95.0)


def _build_view(asset: str, bias: str, conviction: float) -> AssetUsdView:
    weight = _ASSET_USD_WEIGHT.get(asset, _DEFAULT_WEIGHT)
    stance = implied_usd_stance(asset, bias)
    conv_frac = conviction / 100.0
    if stance == "usd_up":
        vote = weight * conv_frac
    elif stance == "usd_down":
        vote = -weight * conv_frac
    else:
        vote = 0.0
    if abs(vote) < _NEUTRAL_VOTE_EPS:
        vote = 0.0
        stance = "neutral"
    return AssetUsdView(
        asset=asset,
        bias=bias,
        conviction=conviction,
        stance=stance,
        weight=weight,
        signed_vote=vote,
    )


def assess_dollar_coherence(
    cards: Sequence[Mapping[str, Any]] | None,
) -> DollarCoherenceVerdict:
    """Reconcile the directional biases of the day's cards into one dollar read.

    ``cards`` is a sequence of mappings with at least ``asset`` +
    ``bias`` (``long``/``short``/``neutral``) + ``conviction`` (0..95 percent
    or 0..1 fraction). Extra keys are ignored, so callers can pass the raw
    ``session_card_audit`` rows or lightweight projections interchangeably.

    Returns a :class:`DollarCoherenceVerdict`. When fewer than two cards cast
    a directional vote there is nothing to reconcile → ``coherent=True`` with
    a neutral/honest explanation (never fabricate a contradiction).
    """
    views: list[AssetUsdView] = []
    seen: set[str] = set()
    for entry in cards or []:
        if not isinstance(entry, Mapping):
            continue
        asset = entry.get("asset")
        if not isinstance(asset, str) or asset in seen:
            continue
        seen.add(asset)
        bias = entry.get("bias") or entry.get("bias_direction") or "neutral"
        conviction = _coerce_conviction(entry.get("conviction") or entry.get("conviction_pct"))
        views.append(_build_view(asset, str(bias), conviction))

    directional = [v for v in views if v.stance != "neutral"]
    net = sum(v.signed_vote for v in directional)
    total = sum(abs(v.signed_vote) for v in directional)

    # Determine consensus.
    if total <= 0.0 or len(directional) < 2:
        consensus: DollarConsensus = "neutral"
        strength = 0.0
    else:
        strength = abs(net) / total
        if strength < _CONSENSUS_MIXED_FRACTION:
            consensus = "mixed"
        elif net > 0:
            consensus = "usd_up"
        else:
            consensus = "usd_down"

    # Outliers : a directional card whose stance opposes a CLEAN consensus
    # (usd_up / usd_down) with conviction above the floor.
    outliers: list[str] = []
    demotions: dict[str, float] = {}
    if consensus in ("usd_up", "usd_down"):
        opposite: UsdStance = "usd_down" if consensus == "usd_up" else "usd_up"
        for v in directional:
            if v.stance == opposite and v.conviction >= _OUTLIER_MIN_CONVICTION:
                outliers.append(v.asset)
                demotions[v.asset] = round(v.conviction * _OUTLIER_DEMOTION_SCALE, 1)

    coherent = not outliers
    explanation = _explain(consensus, strength, views, directional, outliers)

    return DollarCoherenceVerdict(
        consensus=consensus,
        consensus_strength=round(strength, 3),
        coherent=coherent,
        views=tuple(views),
        outliers=tuple(outliers),
        recommended_demotions=demotions,
        coach_explanation=explanation,
        n_directional=len(directional),
    )


_CONSENSUS_FR: dict[DollarConsensus, str] = {
    "usd_up": "un dollar plutôt fort",
    "usd_down": "un dollar plutôt faible",
    "mixed": "un dollar sans direction nette",
    "neutral": "pas de lecture dollar d'ensemble",
}


def _explain(
    consensus: DollarConsensus,
    strength: float,
    views: Sequence[AssetUsdView],
    directional: Sequence[AssetUsdView],
    outliers: Sequence[str],
) -> str:
    """Build the plain-French coach paragraph (ADR-017-clean, beginner level)."""
    if len(directional) < 2:
        return (
            "Pas assez de biais directionnels aujourd'hui pour dégager une "
            "vue dollar d'ensemble — les actifs sont lus séparément."
        )

    up = [v.asset for v in directional if v.stance == "usd_up"]
    down = [v.asset for v in directional if v.stance == "usd_down"]
    head = (
        f"Vue dollar d'ensemble : {_CONSENSUS_FR[consensus]} "
        f"({len(up)} actif(s) pointent vers un dollar fort, "
        f"{len(down)} vers un dollar faible)."
    )

    if consensus == "mixed":
        return (
            head + " Les actifs ne racontent pas la même histoire sur le "
            "dollar : à prendre comme un marché tiraillé, sans conviction "
            "directionnelle d'ensemble."
        )
    if consensus == "neutral":
        return head

    if not outliers:
        return (
            head + " Les biais sont cohérents entre eux : ils décrivent tous "
            "le même régime dollar, ce qui renforce la lecture."
        )

    # Incoherent : name the outliers + why it's a red flag.
    names = ", ".join(_display(a) for a in outliers)
    sens = "haussier" if consensus == "usd_up" else "baissier"
    return (
        head + f" Incohérence : {names} va à contre-courant de cette vue "
        f"dollar {sens} — rappel : si le dollar se renforce, c'est qu'on vend "
        "autre chose, donc une lecture isolée qui contredit l'ensemble est "
        "fragile. Prudence accrue sur ce(s) actif(s)."
    )


__all__ = [
    "AssetUsdView",
    "DollarCoherenceVerdict",
    "DollarConsensus",
    "UsdStance",
    "assess_dollar_coherence",
    "implied_usd_stance",
]
