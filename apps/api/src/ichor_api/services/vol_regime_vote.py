"""vol_regime_vote.py — Chantier C · the volatility-regime DOUBT ``DimensionVote`` producer.

WHY THIS MODULE EXISTS
----------------------
The VIX term structure (VIX 1M vs VIX 3M, ``vix_term_structure.assess_vix_term``) measures
forward risk pricing. Last session it was DEFERRED: it is a textbook *uncertainty-magnitude*
read, and the old ``DimensionVote`` contract could only RAISE conviction — a high-VIX regime
mapped to a positive credit would have been BACKWARDS (a stressed market deserves LESS
conviction, not more). The new doubt term (``increases_uncertainty``) gives it an honest home:
this is the first **DOUBT** producer.

DOUBT, NON-DIRECTIONAL (ADR-017)
--------------------------------
A backwardated VIX term structure (1M > 3M, ratio > 1) signals near-term stress → the outcome
distribution is *wider* → a directional bucket read earns LESS conviction. The vote is
``directional=False`` / ``increases_uncertainty=True``: it contributes only ``doubt_penalty()``
(lowers conviction), never a tilt. It can NEVER set direction (the contrarian "buy
backwardation" timing read is empirically a multi-week regime that blows up when traded as a
signal — deferred to S05 with technical confirmation, exactly as the blueprint concluded).

GLOBAL (honest limitation)
--------------------------
The VIX term structure is one market-wide read (no per-asset implied vol in the data), so the
same doubt attaches to all 5 assets. Honest and surfaced (a high-VIX session is broadly
harder to call).

NOT WIRED (gated). Pure, I/O-free primitive mapper (ADR-120: imports nothing but
``dimension_vote`` + stdlib). The async builder reads ``assess_vix_term`` then maps; wiring is
golden-card-guarded so flag-OFF is byte-identical.

VERIFIED DOCTRINE (web-checked 2026-06-20, primary + reputable)
--------------------------------------------------------------
* **VIX measures uncertainty MAGNITUDE, not direction** — suited to sizing / anti-conviction,
  not directional bets ("reduce exposure as vol rises"; "treat volatility as a regime"). This
  is exactly a DOUBT layer. — gomarkets.com (VIX explained) · internationaltradinginstitute.com
  (dynamic position sizing in volatile markets).
* **Backwardation (1M > 3M) = near-term stress regime** (2008 / Mar-2020 / Aug-2024); it is a
  REGIME/oversold gauge, NOT a timing tool — a naive contrarian long-on-backwardation strategy
  drew down ~-80 %. So it lowers conviction (doubt), it does not pick a side.
  — volatilitytradingstrategies.com (contango/backwardation timing) · the in-repo
  ``vix_term_structure`` docstring (backwardation regimes).
* **Anchors** mirror the in-repo classifier bands (``vix_term_structure._classify``): the
  "flat/normal" boundary ratio 0.95 = no doubt; the "extreme_backwardation" cut ratio 1.15 =
  full doubt (a deliberately HIGH bar like cot's 10 %-OI / volume's 3.0×). S05 Brier-fits these.

INVARIANTS (mirror ``dimension_vote`` / ``volume_vote``)
-------------------------------------------------------
* ADR-017 — non-directional DOUBT: never a tilt; lowers conviction via ``doubt_penalty``.
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0 (non-fresh
  source, missing ratio i.e. a VIX leg absent, missing age, non-finite / non-positive ratio).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped); one full doubt vote shaves ≤ ``VOTE_GAIN_K``
  (≤ -0.10) off the agreement factor, bounded by ``AGREEMENT_FLOOR``.
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote

PROVENANCE = "vol_regime"
"""Dimension id surfaced in the transparent ``doubts`` / coach surface."""

VOL_REGIME_DIMENSION_VOTE_FLAG = "vol_regime_dimension_vote_enabled"
"""Feature-flag key gating the live wiring. SINGLE source of truth (write + read). Absent flag
⇒ ``is_enabled`` False ⇒ both sides no-op ⇒ byte-identical to the legacy path. Mirrors
``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

VOL_REGIME_MAX_AGE_DAYS = 14
"""Freshness window. Mirrors the FRED 14-day staleness cut in ``vix_term_structure._latest``
(vix_term_structure.py:102). FRED VIX series are same-day daily closes → no publication lag."""

VOL_REGIME_BASELINE_RATIO = 0.95
"""VIX1M/VIX3M at/below which there is NO doubt (strength 0). The in-repo "flat" boundary
(``vix_term_structure._classify``: ratio < 0.95 = normal/contango = calm). Calm / contango
markets do not widen the distribution → no conviction penalty."""

VOL_REGIME_FULL_STRENGTH_RATIO = 1.15
"""VIX1M/VIX3M mapping to full doubt (strength 1.0) — the in-repo "extreme_backwardation" cut
(``vix_term_structure._classify``: ratio >= 1.15). A deliberately HIGH bar so a mild 1.02
backwardation yields only ~0.35 doubt (mirror cot's 10 %-OI and volume's 3.0× anchors)."""


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


def build_vol_regime_vote(
    *,
    status: str,
    vix_ratio: float | None,
    age_days: int | None,
    max_age_days: int = VOL_REGIME_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map the VIX term-structure ratio to one DOUBT ``DimensionVote`` (pure, no I/O).

    Always non-directional + ``increases_uncertainty=True``: a backwardated VIX widens the
    outcome distribution → it LOWERS conviction, never tilts long/short (ADR-017). GLOBAL (no
    ``asset`` param) — one VIX read for the whole market.

    Parameters
    ----------
    status:
        S04 liveness status of the VIX source (``classify_liveness``). Fail-closed: only
        ``"fresh"`` votes.
    vix_ratio:
        ``VixTermReading.ratio`` = VIX1M / VIX3M. ``None`` (a VIX leg missing) → abstain.
        Non-finite / non-positive → abstain (corrupted).
    age_days:
        Age of the latest VIX observation in days. ``None`` → abstain.
    max_age_days:
        Freshness window (defaults to the 14-day FRED VIX gate).

    Returns
    -------
    DimensionVote
        ``provenance="vol_regime"``, ``directional=False``, ``increases_uncertainty=True``.
        ``honest_absence=True`` (→ 0) when no usable read. Otherwise a doubt whose ``strength``
        scales the backwardation above the 0.95 flat boundary (0 at/below it, 1 at the 1.15
        extreme-backwardation cut) and whose ``freshness`` decays over the window. A calm /
        contango ratio is a present, strength-0 doubt (contributes 0 — honest "no stress").
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    if status != "fresh":
        return _absent_vote()  # fail-closed: absent / stale / unknown source → abstain
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain
    if vix_ratio is None:
        return _absent_vote()  # a VIX leg missing → no term structure → abstain
    if not math.isfinite(vix_ratio) or vix_ratio <= 0.0:
        return _absent_vote()  # corrupted ratio → refuse to map

    # --- Strength: backwardation above the flat boundary = doubt magnitude. ------------
    span = VOL_REGIME_FULL_STRENGTH_RATIO - VOL_REGIME_BASELINE_RATIO
    strength = (
        _clamp((vix_ratio - VOL_REGIME_BASELINE_RATIO) / span, 0.0, 1.0) if span > 0.0 else 0.0
    )

    # --- Freshness: linear decay over the window (daily FRED, no publication lag). ------
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
