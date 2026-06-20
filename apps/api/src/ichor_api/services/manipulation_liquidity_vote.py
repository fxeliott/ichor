"""manipulation_liquidity_vote.py — Chantier C · the funding-liquidity DOUBT producer.

WHY THIS MODULE EXISTS
----------------------
The S04 prompt lists "manipulations & zones de liquidité" as a dimension. Its per-asset
price-action half (ICT liquidity zones / stop-hunt levels) is the Session-05 TECHNICAL read
(``liquidity_proxy.py`` docstring is explicit). What S04 CAN express today is the MACRO
funding-liquidity regime Ichor already collects: RRP + TGA (``assess_liquidity_proxy``). A
funding-liquidity DRAIN is a market-wide AMPLIFICATION mechanism (Brunnermeier-Pedersen
liquidity spirals): when funding tightens, positions are cut regardless of fundamentals →
the outcome distribution WIDENS. That is a DOUBT, not a direction.

DOUBT, NON-DIRECTIONAL, GLOBAL (ADR-017)
----------------------------------------
``directional=False`` / ``increases_uncertainty=True``: a drain lowers conviction, never
tilts. The "TGA drain ⇒ risk-off" directional thesis is heavily caveated ("not one-
directional or clean", offsetting Fed flows) and is already covered by the directional
dollar / funding_stress reads — so a directional version would be a fake edge. GLOBAL: RRP+TGA
is one market-wide scalar (no per-asset funding liquidity), so the same doubt attaches to all
5 assets (honest, surfaced). The genuinely per-asset liquidity-zone vote is deferred to S05
when that technical data lands.

NOT WIRED (gated). Pure, I/O-free primitive mapper (ADR-120). The async builder reads
``assess_liquidity_proxy``; wiring is golden-card-guarded (flag-OFF byte-identical).

VERIFIED DOCTRINE (web-checked 2026-06-20, primary + reputable)
--------------------------------------------------------------
* **Funding ↔ market liquidity spirals** (Brunnermeier & Pedersen 2009, RFS 22(6)): when
  funding tightens, traders cut positions regardless of fundamental value — an amplification /
  conditioning mechanism, structurally NON-directional (it sets propensity, not direction).
  — princeton.edu/~markus/research/papers/liquidity.pdf · academic.oup.com/rfs/.../1592184.
* **TGA refill + depleted RRP drains bank reserves ~1:1**, a headwind for risk assets — but
  sources stress it "isn't always one-directional or clean" (offsetting Fed-repo/QT flows).
  Supports a NON-directional propensity read, not a per-asset directional vote.
  — wolfstreet.com/2025/09/03/... (RRP near zero, TGA refill drains liquidity).
* **Anchor**: full doubt at the in-repo ``LIQ_TIGHTENING_THRESHOLD_BN = -200`` $bn / 5-business-
  day drain (the same value the ``LIQUIDITY_TIGHTENING`` alert fires on — single source of
  truth). A drain below that is a genuine tightening regime; a rising / stable proxy = 0 doubt.

INVARIANTS (mirror ``dimension_vote`` / ``vol_regime_vote``)
----------------------------------------------------------
* ADR-017 — non-directional DOUBT: never a tilt; lowers conviction via ``doubt_penalty``.
* ADR-103 — no usable data → ``honest_absence=True`` → 0 (non-fresh source, missing delta i.e.
  insufficient history, missing as_of/age, non-finite delta).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote

PROVENANCE = "manipulation_liquidity"
"""Dimension id surfaced in the transparent ``doubts`` / coach surface."""

MANIPULATION_LIQUIDITY_DIMENSION_VOTE_FLAG = "manipulation_liquidity_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (SINGLE source of truth, write + read). Absent flag
⇒ both sides no-op ⇒ byte-identical. Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

LIQUIDITY_MAX_AGE_DAYS = 8
"""Freshness window. The TGA leg is at best WEEKLY (WTREGEN week-ending Wednesday; DTS daily
ideal but often empty), so the proxy can never be same-day-fresh — 8 days covers a weekly TGA
+ slack. No separate publication lag (the weekly cadence IS the ceiling)."""

LIQUIDITY_FULL_STRENGTH_DRAIN_BN = 200.0
"""A 5-business-day drain of 200 $bn maps to full doubt (strength 1.0). Smaller drains scale
linearly; a rising / stable proxy (delta >= 0) = 0 doubt (deeper liquidity does not widen
outcomes). Mirrors ``liquidity_proxy.LIQ_TIGHTENING_THRESHOLD_BN = -200`` (the value the
``LIQUIDITY_TIGHTENING`` alert fires on); kept as a local literal so this producer stays a
stdlib-only pure unit (ADR-120 — it must not import the I/O-heavy ``liquidity_proxy`` module).
The builder's test asserts the two stay in lock-step."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _absent_vote() -> DimensionVote:
    """An honest non-vote (ADR-103): present, contributes 0. Non-directional DOUBT layer."""
    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=0.0,
        freshness=0.0,
        honest_absence=True,
        directional=False,
        increases_uncertainty=True,
    )


def build_manipulation_liquidity_vote(
    *,
    status: str,
    delta_bn: float | None,
    age_days: int | None,
    max_age_days: int = LIQUIDITY_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map the RRP+TGA funding-liquidity delta to one DOUBT ``DimensionVote`` (pure, no I/O).

    Always non-directional + ``increases_uncertainty=True``: a funding drain widens the outcome
    distribution → it LOWERS conviction, never tilts (ADR-017). GLOBAL (no ``asset`` param).

    Parameters
    ----------
    status:
        S04 liveness status (``classify_liveness`` on the proxy's ``as_of``). Fail-closed: only
        ``"fresh"`` votes.
    delta_bn:
        ``LiquidityProxyReading.delta_bn`` (proxy now − proxy 5 business days ago, $bn).
        NEGATIVE = liquidity drained. ``None`` (insufficient history) → abstain. Non-finite →
        abstain.
    age_days:
        Age of the proxy snapshot in days. ``None`` → abstain.
    max_age_days:
        Freshness window (defaults to 8 days — weekly TGA ceiling).

    Returns
    -------
    DimensionVote
        ``provenance="manipulation_liquidity"``, ``directional=False``,
        ``increases_uncertainty=True``. ``honest_absence=True`` (→ 0) when no usable read. A
        drain scales doubt from 0 (delta >= 0, stable/rising liquidity) to 1 at a 200 $bn drain;
        ``freshness`` decays over the window. A non-draining proxy is a present strength-0 doubt.
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    if status != "fresh":
        return _absent_vote()  # fail-closed
    if age_days is None:
        return _absent_vote()  # cannot verify freshness
    if delta_bn is None:
        return _absent_vote()  # insufficient history → no readable drain
    if not math.isfinite(delta_bn):
        return _absent_vote()  # corrupted

    # --- Strength: a DRAIN (delta < 0) widens outcomes; injection (delta >= 0) = 0 doubt. -
    drain_bn = max(0.0, -float(delta_bn))  # positive magnitude of the drain, 0 if rising
    strength = _clamp(drain_bn / LIQUIDITY_FULL_STRENGTH_DRAIN_BN, 0.0, 1.0)

    # --- Freshness: linear decay over the (weekly-bounded) window. ----------------------
    effective_window = float(max_age_days)
    if effective_window <= 0.0:
        freshness = 1.0 if age_days <= max_age_days else 0.0
    else:
        freshness = _clamp(1.0 - float(age_days) / effective_window, 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=False,
        increases_uncertainty=True,
    )
