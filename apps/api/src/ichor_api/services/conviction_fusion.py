"""Evidence-weighted conviction fusion — Session 04 (« kill the 50/50 »).

Why this module exists
----------------------
Today the apex ``SessionVerdict`` conviction is computed by
``session_verdict_builder._derive_direction_and_conviction`` as

    raw_conviction = max(bullish_mass, bearish_mass) * 100      # buckets only

over the 7 Pass-6 bucket masses **alone** (``session_verdict_builder.py:135``),
gated by a hard dead-zone ``spread < 0.15 -> ("neutral", 0.0)`` (``:61,:131``).
The rich synthesis layers Ichor already computes — the 12-factor
``confluence_engine`` directional score, the ``theme_classifier`` dominant
driver, and the cross-asset ``dollar_coherence`` consensus — never feed that
number (they inform narrative / endpoints only, and the demote-only
``card_coherence`` reconciliation is persisted to a *different* column the
apex re-read ignores). That disconnect is the documented « 50/50 » gap
(``tests/test_architecture_invariants.py:43-46``).

This module is the **pure, deterministic fusion core** that closes it:
direction stays bucket-derived (ADR-017 — bias + probability, never an order;
evidence may scale *magnitude*, never *sign*), but conviction becomes an
**evidence-agreement-weighted** quantity with a **graded dead-zone** and an
**explicit French grounding** ("conviction X % parce que A et B confirment,
D s'oppose").

Design contract (deliberately pure)
-----------------------------------
``fuse_conviction`` operates on **primitives** that the caller extracts from
the heavy service dataclasses, so the core is unit-testable in isolation and
carries **no** I/O, no LLM call, no pydantic / brain import — Voie-D clean
(ADR-009). The only intra-package import is ``dimension_vote`` (itself stdlib-only,
designed to be fuser-importable without breaking that purity — ADR-120). The verdict
builder ``session_verdict_builder._derive_direction_and_conviction`` **already**
delegates to this function and surfaces ``rationale_fr`` in the coach text — this
is LIVE (the 50/50 is killed in production), not a future gated step. The dormant
piece on top is the C-5 calibrator (ADR-120, flag-OFF), not this base fusion.

Invariants honoured
-------------------
* ADR-017 — ``direction`` comes from the buckets only. ``theme`` is
  structurally non-directional here (a plain ``bool`` presence flag — it
  *cannot* carry a long/short vote). ``rationale_fr`` is plain French and
  contains zero trade-signal tokens (canonical SSOT
  ``ichor_brain.adr017.contains_trade_signal``).
* ADR-022 (cap-95) — ``conviction_pct`` is clamped to ``[0.0, 95.0]``.
  Promotion is bounded (``AGREEMENT_CEIL``) so corroboration can *strengthen*
  a real edge but never *manufacture* certainty.
* Doctrine #11 (calibrated honesty) — a true coin-flip (spread below the
  hard dead-zone) returns ``direction="neutral", conviction_pct=0.0`` with an
  honest rationale. Ichor refuses to fabricate a 50/50 read.

Scope boundary (see ``PLAN_DIRECTEUR.md`` §5)
--------------------------------------------
S04 ships **fixed, principled priors** (the constants below). Fitting the
fusion weights from realised Brier outcomes is **S05** (the Vovk/Brier
machinery exists as a producer but its reader->conviction loop stays
flag-gated OFF). This module intentionally takes **no** learned weight.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .dimension_vote import (
    DimensionVote,
    net_dimension_vote,
    total_doubt_penalty,
    total_uncertainty_credit,
)

# --------------------------------------------------------------------------- #
# Types                                                                       #
# --------------------------------------------------------------------------- #

# Local direction type — kept standalone (no import of the pydantic
# ``VerdictDirection`` from ``.session_verdict``) so this core stays a pure,
# dependency-free unit. The builder maps it onto ``VerdictDirection`` (the
# string values are identical) at the integration seam.
Direction = Literal["up", "down", "neutral"]

ConfluenceLean = Literal["long", "short", "neutral"]
DollarConsensus = Literal["usd_up", "usd_down", "mixed", "neutral"]


# --------------------------------------------------------------------------- #
# Calibration constants (principled priors — rationale per PLAN_DIRECTEUR §)   #
# Every value is documented; no magic number. S05 will fit these from Brier.   #
# --------------------------------------------------------------------------- #

DEAD_ZONE_HARD = 0.05
"""bullish-vs-bearish mass spread at or below which the read is a true
coin-flip -> ``neutral, 0.0``. A 5 pp spread is within Pass-6 quantisation noise for 7
buckets each capped at 0.95; calling a direction below it is dishonest.
Tighter than the legacy hard 0.15 — the graded soft-zone below handles the
0.05–0.15 band instead of cliff-dropping it to neutral."""

DEAD_ZONE_SOFT = 0.15
"""Spread at/above which the bucket edge is taken at full strength. Equal to
the legacy ``_DIRECTIONAL_DEAD_ZONE`` (``session_verdict_builder.py:61``):
above it, behaviour with no evidence is unchanged from today
(backward-compatible). Between HARD and SOFT the conviction is linearly
attenuated — a weak edge survives *iff* corroborated, dies if contradicted."""

VOTE_GAIN_K = 0.10
"""Maps the net evidence vote to the agreement factor: one fully-aligned
layer (vote +1) lifts conviction ~10 %; one opposed shaves ~10 %. Same order
of magnitude as the proven demote-only ``card_coherence`` scalars
(×0.70/0.85/0.90) so the new promotion side is symmetric in strength to the
existing demotion side."""

AGREEMENT_FLOOR = 0.60
"""Worst-case full disagreement cannot zero out a strong bucket edge — mirrors
the spirit of ``card_coherence`` ``WEAK_DRIVER_DISAGREE_SCALE=0.70``, slightly
more aggressive because S04 fuses several layers at once."""

AGREEMENT_CEIL = 1.25
"""Promotion is bounded: a 70 % base edge × 1.25 = 87.5 < 95. Corroboration
strengthens, never manufactures certainty (ADR-022, « 100 % n'existe pas »)."""

THEME_PRESENCE_VOTE = 0.5
"""Non-directional anti-uncertainty credit added to the net vote when a
*dominant* market theme exists (strength ≥ classifier threshold). A clear
session driver makes a directional read marginally less likely to be noise.
It is **always ≥ 0** and **never** tilts long/short (ADR-017: theme « n'est
jamais un signal de direction »)."""

CONVICTION_CEIL_PCT = 95.0
"""ADR-022 cap-95. The persisted Pydantic field also enforces ``le=95.0``;
we clamp here defensively to avoid a 422 cascade (mirrors the legacy
``min(raw, 95.0)`` at ``session_verdict_builder.py:138``)."""

CONFLUENCE_WEIGHT = 1.0
"""Layer-level fusion weight for the confluence directional score. Equal-weight
prior (the Brier-optimised weights inside the score weight the *factors*, not
the *layer*). S05 fits the layer weight."""

_BULL_LABELS = ("mild_bull", "strong_bull", "melt_up")
_BEAR_LABELS = ("mild_bear", "strong_bear", "crash_flush")

# Sign of an asset's price correlation to the US dollar: ``+1`` if the asset
# rises when USD rises, ``-1`` if it falls. Used to translate a cross-asset
# USD consensus into a per-asset directional implication. Covers the 5 verdict
# priority assets (all USD-quote / USD-priced -> -1) plus the USD-base pairs so
# the function is general and future-proof.
_ASSET_USD_SIGN: dict[str, int] = {
    "EUR_USD": -1,  # USD up -> EUR_USD down
    "GBP_USD": -1,
    "XAU_USD": -1,  # gold inversely tracks USD
    "SPX500_USD": -1,  # equities loosely inverse to USD strength
    "NAS100_USD": -1,
    "USD_CAD": +1,  # USD up -> USD_CAD up
    "USD_JPY": +1,
    "AUD_USD": -1,
}


# --------------------------------------------------------------------------- #
# Result                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ConvictionGrounding:
    """Verdict conviction + the transparent reason it reads as it does.

    ``direction`` is bucket-derived (ADR-017). ``conviction_pct`` is the fused,
    clamped [0, 95] value. ``agreeing`` / ``disagreeing`` are the canonical
    synthesis-layer keys that corroborated / contradicted the direction.
    ``rationale_fr`` is the plain-French coach sentence (no trade tokens).
    """

    direction: Direction
    conviction_pct: float
    base_conviction_pct: float
    agreement_factor: float
    soft_zone_scale: float
    agreeing: tuple[str, ...] = field(default_factory=tuple)
    disagreeing: tuple[str, ...] = field(default_factory=tuple)
    rationale_fr: str = ""
    doubts: tuple[str, ...] = field(default_factory=tuple)
    """Non-directional DOUBT layers that LOWERED conviction (wide-distribution regime:
    vol stress, funding drain, systemic correlation, institutional divergence). Distinct
    from ``disagreeing`` (which points the opposite *direction*) — a doubt does not contest
    the direction, it widens the outcome. Empty ⇒ byte-identical to the pre-doubt output."""


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _directional_masses(scenarios: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    """Return ``(bullish_mass, bearish_mass)`` from the 7 Pass-6 buckets.

    Mirrors ``session_verdict_builder._derive_direction_and_conviction``
    (``:118-128``) so the directional read is byte-identical to the legacy
    path before fusion.
    """
    by_label = {str(s["label"]): float(s["p"]) for s in scenarios}
    bullish = sum(by_label.get(lbl, 0.0) for lbl in _BULL_LABELS)
    bearish = sum(by_label.get(lbl, 0.0) for lbl in _BEAR_LABELS)
    return bullish, bearish


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


_FR_LAYER_NAMES = {
    "confluence": "confluence des facteurs",
    "dollar_coherence": "cohérence dollar",
    "theme": "thème dominant",
    # Chantier C dimension votes (coach-FR surface, vision §D « expliquer »).
    "cot": "positionnement COT (smart money)",
    "positioning_tff": "positionnement institutionnel (TFF)",
    "volume": "volume / participation",
    "geopolitics": "risque géopolitique",
    "sentiment": "sentiment retail (contrarian)",
    # Doubt layers (lower conviction).
    "vol_regime": "régime de volatilité (VIX)",
    "manipulation_liquidity": "liquidité de financement",
    "correlations": "régime de corrélations",
    "positioning_divergence": "divergence institutionnelle",
}


def _fr_join(keys: Sequence[str]) -> str:
    labels = [_FR_LAYER_NAMES.get(k, k) for k in keys]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " et " + labels[-1]


def _direction_fr(direction: Direction) -> str:
    return {"up": "biais haussier", "down": "biais baissier", "neutral": "biais neutre"}[direction]


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def fuse_conviction(
    *,
    asset: str,
    scenarios: Sequence[Mapping[str, Any]],
    confluence_lean: ConfluenceLean | None = None,
    theme_present: bool = False,
    dollar_consensus: DollarConsensus | None = None,
    dollar_strength: float = 0.0,
    votes: Sequence[DimensionVote] = (),
) -> ConvictionGrounding:
    """Fuse the bucket-derived edge with the synthesis evidence.

    Parameters are PRIMITIVES the caller extracts from the heavy dataclasses:

    * ``scenarios`` — the 7 Pass-6 buckets ``[{"label", "p"}, ...]`` (sole
      source of ``direction``).
    * ``confluence_lean`` — ``ConfluenceReport.dominant_direction`` mapped to
      ``"long" | "short" | "neutral"`` (``confluence_engine.py:868``).
    * ``theme_present`` — whether ``theme_classifier`` returned a dominant
      theme (strength ≥ its threshold). **Non-directional** by ADR-017.
    * ``dollar_consensus`` / ``dollar_strength`` —
      ``DollarCoherenceVerdict.consensus`` + ``.consensus_strength``
      (``cross_asset_dollar_coherence.py:148-161``).
    * ``votes`` — Chantier C ``DimensionVote`` layers (rates, positioning,
      geopolitics, …). Default ``()`` ⇒ byte-identical to the legacy 3-layer path.
      When populated, each layer feeds the SAME agreement-factor math
      (``net_dimension_vote`` directional, ``total_uncertainty_credit``
      non-directional). The real layers are wired in a later slice (C-3); this
      parameter is the additive seam they plug into.

    Returns a :class:`ConvictionGrounding`. With **no** evidence supplied the
    direction matches the legacy path exactly; only the dead-zone becomes
    graded (the intended S04 change).
    """
    dollar_strength = _clamp(float(dollar_strength), 0.0, 1.0)
    bullish, bearish = _directional_masses(scenarios)
    base_conviction_pct = max(bullish, bearish) * 100.0
    spread = abs(bullish - bearish)

    # --- Hard dead-zone: an honest coin-flip. Evidence cannot save it. ----- #
    # ``<=`` (not ``<``) so the exact boundary spread == DEAD_ZONE_HARD resolves
    # to neutral/0 rather than a directional label at 0 % conviction (the
    # soft-zone scale would be 0 there) — doctrine #11: no "biais haussier à
    # 0 %".
    if spread <= DEAD_ZONE_HARD:
        spread_pp = round(spread * 100, 1)
        rationale = (
            f"Conviction nulle : la décomposition des scénarios est trop "
            f"équilibrée (écart {spread_pp} pts < {round(DEAD_ZONE_HARD * 100)} "
            f"pts) — aucune direction tranchée. Honnêteté calibrée : Ichor ne "
            f"force pas un pile ou face."
        )
        return ConvictionGrounding(
            direction="neutral",
            conviction_pct=0.0,
            base_conviction_pct=base_conviction_pct,
            agreement_factor=1.0,
            soft_zone_scale=0.0,
            agreeing=(),
            disagreeing=(),
            rationale_fr=rationale,
        )

    direction: Direction = "up" if bullish > bearish else "down"
    direction_num = 1 if direction == "up" else -1

    # --- Graded soft-zone: attenuate a weak edge linearly. ----------------- #
    if spread >= DEAD_ZONE_SOFT:
        soft_zone_scale = 1.0
    else:
        soft_zone_scale = (spread - DEAD_ZONE_HARD) / (DEAD_ZONE_SOFT - DEAD_ZONE_HARD)

    # --- Evidence votes (magnitude only — direction is already fixed). ----- #
    agreeing: list[str] = []
    disagreeing: list[str] = []
    doubts: list[str] = []
    net_vote = 0.0

    # confluence: aligned -> +, opposed -> -, neutral/None -> 0.
    lean_num = {"long": 1, "short": -1, "neutral": 0}.get(confluence_lean or "neutral", 0)
    confluence_vote = CONFLUENCE_WEIGHT * lean_num * direction_num
    if confluence_vote > 0:
        agreeing.append("confluence")
    elif confluence_vote < 0:
        disagreeing.append("confluence")
    net_vote += confluence_vote

    # dollar coherence: translate USD consensus -> this asset's direction.
    usd_dir_num = {"usd_up": 1, "usd_down": -1, "mixed": 0, "neutral": 0}.get(
        dollar_consensus or "neutral", 0
    )
    asset_usd_sign = _ASSET_USD_SIGN.get(asset, 0)
    implied_asset_num = usd_dir_num * asset_usd_sign  # +1 asset-up, -1 asset-down, 0 none
    dollar_vote = implied_asset_num * direction_num * dollar_strength
    if dollar_vote > 0:
        agreeing.append("dollar_coherence")
    elif dollar_vote < 0:
        disagreeing.append("dollar_coherence")
    net_vote += dollar_vote

    # theme: non-directional anti-uncertainty presence credit (never negative,
    # never directional — ADR-017).
    if theme_present:
        net_vote += THEME_PRESENCE_VOTE
        agreeing.append("theme")

    # dimension votes (Chantier C): each extra analysis layer feeds the SAME
    # agreement-factor math additively. Direction stays bucket-derived (ADR-017):
    # ``signed_contribution()`` is absolute (+up / -down), so multiplying the net by
    # ``direction_num`` turns it into "agreement with the bucket edge"; a present
    # non-directional / neutral vote contributes only its ``uncertainty_credit()``
    # (>= 0), exactly like ``theme``. With ``votes == ()`` every term below is 0, so
    # the result is byte-identical to the legacy 3-layer path (proven by the golden
    # harness, ``tests/test_fuser_golden_harness.assert_fuser_golden``).
    net_vote += net_dimension_vote(votes) * direction_num
    net_vote += total_uncertainty_credit(votes)
    # Doubt layers (vol stress, funding drain, systemic correlation, institutional
    # divergence) SUBTRACT — they widen the outcome distribution, so a directional read
    # earns less conviction (calibrated humility, ADR-017: still never a direction).
    net_vote -= total_doubt_penalty(votes)
    for vote in votes:
        if not vote.is_effective:
            continue
        contribution = vote.signed_contribution() * direction_num
        if contribution > 0:
            agreeing.append(vote.provenance)
        elif contribution < 0:
            disagreeing.append(vote.provenance)
        elif vote.increases_uncertainty:  # non-directional DOUBT → lowered conviction
            doubts.append(vote.provenance)
        else:  # present but non-directional corroboration → anti-uncertainty credit (ADR-017)
            agreeing.append(vote.provenance)

    agreement_factor = _clamp(1.0 + VOTE_GAIN_K * net_vote, AGREEMENT_FLOOR, AGREEMENT_CEIL)

    # --- Fuse + clamp to cap-95. ------------------------------------------- #
    fused = base_conviction_pct * soft_zone_scale * agreement_factor
    conviction_pct = _clamp(fused, 0.0, CONVICTION_CEIL_PCT)

    rationale = _build_rationale_fr(
        direction=direction,
        conviction_pct=conviction_pct,
        agreeing=agreeing,
        disagreeing=disagreeing,
        soft_zone_scale=soft_zone_scale,
        doubts=doubts,
    )

    return ConvictionGrounding(
        direction=direction,
        conviction_pct=conviction_pct,
        base_conviction_pct=base_conviction_pct,
        agreement_factor=agreement_factor,
        soft_zone_scale=soft_zone_scale,
        agreeing=tuple(agreeing),
        disagreeing=tuple(disagreeing),
        rationale_fr=rationale,
        doubts=tuple(doubts),
    )


def _build_rationale_fr(
    *,
    direction: Direction,
    conviction_pct: float,
    agreeing: Sequence[str],
    disagreeing: Sequence[str],
    soft_zone_scale: float,
    doubts: Sequence[str] = (),
) -> str:
    """Plain-French coach grounding. Zero trade-signal tokens by construction
    (mirror of ``scenarios.py:50-53`` — no BUY/SELL/TP/SL/entry/exit)."""
    head = f"Conviction {conviction_pct:.0f} % ({_direction_fr(direction)})."

    if agreeing and disagreeing:
        body = (
            f" Preuves concordantes : {_fr_join(agreeing)} ; "
            f"en désaccord : {_fr_join(disagreeing)}."
        )
    elif agreeing:
        body = f" Preuves concordantes : {_fr_join(agreeing)} ; aucun désaccord."
    elif disagreeing:
        body = f" Aucune preuve concordante ; en désaccord : {_fr_join(disagreeing)}."
    else:
        body = " Aucune preuve de synthèse disponible (conviction issue des seuls scénarios)."

    # Doubt layers temper conviction WITHOUT contesting the direction (wide-distribution
    # regime) — surfaced distinctly so the coach explains the « pourquoi » (vision §D).
    doubt_clause = ""
    if doubts:
        doubt_clause = f" Incertitude élevée ({_fr_join(doubts)}) : conviction tempérée."

    tail = ""
    if soft_zone_scale < 1.0:
        tail = " Bord directionnel faible (zone tampon) : conviction atténuée."

    return head + body + doubt_clause + tail
