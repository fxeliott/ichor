"""correlations_vote.py — Chantier C · the cross-asset-correlation DOUBT producer.

WHY THIS MODULE EXISTS
----------------------
When cross-asset correlations spike toward +1 (systemic de-risking / risk-off cascade),
diversification fails and the whole complex moves together — the outcome distribution WIDENS.
``assess_correlations`` already computes the rolling cross-asset correlation matrix (incl. DXY).
Last session it was DEFERRED: the only DIRECTIONAL content of a correlation matrix is an asset's
sign vs the dollar, which ``dollar_coherence`` already votes — so a directional correlation vote
would double-count, and the contract could not express the honest NON-directional read. The
doubt term gives it one: a high-average-|correlation| regime is a DOUBT, not a direction.

DOUBT, NON-DIRECTIONAL, GLOBAL (ADR-017)
----------------------------------------
A Pearson matrix is symmetric — it carries NO up/down content (Engel-West 2005, cited in
``correlations.py``, forbids treating co-movement as a directional predictor). The vote is
``directional=False`` / ``increases_uncertainty=True``: rising systemic correlation lowers
conviction, never tilts. GLOBAL: one market-wide regime read shared by all 5 assets.

HONEST LIMITATIONS (surfaced, not hidden)
-----------------------------------------
* Average pairwise correlation is a COINCIDENT / weak-predictive systemic indicator — so the
  bar is HIGH (full doubt only at avg |corr| ~0.80) and the magnitude is conservative.
* It needs enough OVERLAPPING intraday history; freshness scales with the overlap (a thin
  matrix counts little), and an under-covered / cold-start (DXY) matrix abstains.

NOT WIRED (gated). Pure, I/O-free primitive mapper (ADR-120). The async builder reads
``assess_correlations`` and computes the average off-diagonal |corr|; wiring is
golden-card-guarded (flag-OFF byte-identical).

VERIFIED DOCTRINE (web-checked 2026-06-20, reputable)
-----------------------------------------------------
* **Rising average pairwise correlation = de-risking / elevated systemic uncertainty** — a
  robust COINCIDENT indicator (spikes around crises) but a WEAK predictive early-warning tool →
  supports a conservative NON-directional doubt, not a strong or directional signal.
  — link.springer.com/article/10.1007/s11135-023-01746-0 · nature.com/articles/srep00888.
* **"Correlation breakdown" = correlations converging toward +1 in stress** (diversification
  fails); diagnose a spike as regime vs noise before acting. — bloomberg.com (MAC3 regime
  detection) · lseg.com (higher correlation multi-asset returns).
* **Anchors**: baseline avg |corr| 0.40 (typical cross-asset) = 0 doubt; full doubt at 0.80
  (systemic convergence). Conservative; S05 Brier-fits, and may swap avg-|corr| for an
  absorption-ratio / PC1 construction (stronger per the literature).

INVARIANTS (mirror ``dimension_vote`` / ``vol_regime_vote``)
----------------------------------------------------------
* ADR-017 — non-directional DOUBT: never a tilt; lowers conviction via ``doubt_penalty``.
* ADR-103 — no usable data → ``honest_absence=True`` → 0 (non-fresh / under-covered matrix,
  missing average, non-finite / out-of-range average).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote

PROVENANCE = "correlations"
"""Dimension id surfaced in the transparent ``doubts`` / coach surface."""

CORRELATIONS_DIMENSION_VOTE_FLAG = "correlations_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (SINGLE source of truth, write + read). Absent flag
⇒ both sides no-op ⇒ byte-identical. Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

CORR_MIN_RETURNS = 30
"""Minimum overlapping hourly returns for a usable matrix (mirrors the section's own n>=30
guard, ``correlations.py``). Below it the matrix is too thin / cold-start → abstain."""

CORR_FULL_CONFIDENCE_RETURNS = 120
"""Overlap (~5 trading days of hourly bars) at/above which the correlation estimate is at full
confidence (freshness 1.0). Between CORR_MIN_RETURNS and this, freshness scales linearly — a
thin-overlap estimate is less reliable, so it counts less (honest)."""

CORR_BASELINE_ABS = 0.40
"""Average off-diagonal |corr| at/below which there is NO doubt (strength 0) — a typical
cross-asset correlation level (normal diversification)."""

CORR_FULL_STRENGTH_ABS = 0.80
"""Average |corr| mapping to full doubt (strength 1.0) — systemic convergence toward +1
(diversification failing). A deliberately HIGH bar (avg-|corr| is a weak predictor)."""


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


def build_correlations_vote(
    *,
    status: str,
    avg_abs_corr: float | None,
    n_returns_used: int | None,
    min_returns: int = CORR_MIN_RETURNS,
) -> DimensionVote:
    """Map the average cross-asset |correlation| to one DOUBT ``DimensionVote`` (pure, no I/O).

    Always non-directional + ``increases_uncertainty=True``: rising systemic correlation widens
    outcomes → it LOWERS conviction, never tilts (ADR-017). GLOBAL (no ``asset`` param).

    Parameters
    ----------
    status:
        Liveness status (``"fresh"`` iff the matrix has sufficient overlap, derived by the
        builder). Fail-closed: only ``"fresh"`` votes.
    avg_abs_corr:
        Average of the off-diagonal |corr| cells (computed by the builder). ``None`` → abstain.
        Non-finite / out of ``[0, 1]`` → abstain (corrupted).
    n_returns_used:
        Max overlapping returns the matrix was built from (``CorrelationMatrix.n_returns_used``).
        ``None`` or ``< min_returns`` → abstain (matrix too thin / cold-start). Drives freshness.
    min_returns:
        Minimum overlap for a usable matrix (defaults to 30).

    Returns
    -------
    DimensionVote
        ``provenance="correlations"``, ``directional=False``, ``increases_uncertainty=True``.
        ``honest_absence=True`` (→ 0) when no usable read. Doubt scales from 0 (avg |corr| <= 0.40)
        to 1 (>= 0.80); ``freshness`` scales with overlap (CORR_MIN_RETURNS → weak, full at
        CORR_FULL_CONFIDENCE_RETURNS). A normal-correlation regime is a present strength-0 doubt.
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    if status != "fresh":
        return _absent_vote()  # fail-closed
    if n_returns_used is None or n_returns_used < min_returns:
        return _absent_vote()  # matrix too thin / cold-start → abstain
    if avg_abs_corr is None:
        return _absent_vote()
    if not math.isfinite(avg_abs_corr) or not (0.0 <= avg_abs_corr <= 1.0):
        return _absent_vote()  # corrupted average

    # --- Strength: average |corr| above the normal baseline = systemic-regime doubt. ----
    span = CORR_FULL_STRENGTH_ABS - CORR_BASELINE_ABS
    strength = _clamp((avg_abs_corr - CORR_BASELINE_ABS) / span, 0.0, 1.0) if span > 0.0 else 0.0

    # --- Freshness: overlap-based confidence (a thin matrix is a less reliable estimate). -
    freshness = _clamp(float(n_returns_used) / float(CORR_FULL_CONFIDENCE_RETURNS), 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=False,
        increases_uncertainty=True,
    )
