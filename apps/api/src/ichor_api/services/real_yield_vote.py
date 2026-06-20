"""real_yield_vote.py — Chantier C · the real-yield→gold FUNDAMENTAL ``DimensionVote`` producer.

WHY THIS MODULE EXISTS (the S04 macro/fundamental dimension, finally voting)
---------------------------------------------------------------------------
The S04 task (prompt line 223) requires covering **analyse fondamentale, macroéconomique**.
That dimension was represented in PROSE (``data_pool._section_xau_specific`` reads DFII10 as
"primary gold driver", data_pool.py:1118-1150) and indirectly via ``theme``/``dollar``/
``confluence`` — but it had no dedicated apex vote. The clean, NON-REDUNDANT macro signal is
the **real-yield → gold carry channel**: gold pays no yield, so when 10Y TIPS real yields
(FRED ``DFII10``) RISE, the opportunity cost of holding gold rises and XAU tends to FALL
(and vice-versa). This is distinct from the nominal dollar (``dollar_coherence`` /
``_ASSET_USD_SIGN["XAU_USD"]`` is nominal-USD only) — gold can fall on rising *real* yields
even with a flat dollar. So this is a genuinely independent directional fundamental vote.

NOTE ON THE S04/S05 BOUNDARY: this is FUNDAMENTAL/MACRO analysis (S04), NOT technical
chart-reading (the ICT liquidity-zone / TradingView reading that is S05). It belongs here.

XAU-ONLY (like positioning_tff is SPX500-only)
----------------------------------------------
The real-yield→gold relationship is asset-specific to gold. For FX/indices the macro driver
is the rate *differential*, which is already the dollar_coherence vote (a generic macro vote
there would double-count it — the TFF-on-EUR trap). So this votes for ``XAU_USD`` only; every
other asset abstains (honest-absence → contributes 0).

RELIABILITY-GATED ON THE EXISTING DIVERGENCE DETECTOR (elegant reuse)
--------------------------------------------------------------------
The carry relationship is not always intact: at a ``REAL_YIELD_GOLD_DIVERGENCE`` (gold driven
by a geopolitical premium / central-bank buying / debasement narrative instead of yields,
``real_yield_gold_check.py``), the directional read is UNRELIABLE. So the vote ABSTAINS when
the existing rolling-correlation divergence z-score is extreme (``|z| >= 2.0`` — the same
alert floor). When the relationship holds (or the z is unknown / not-yet-warm), it votes.

NOT WIRED (gated). Pure, I/O-free primitive mapper (ADR-120: imports nothing but
``dimension_vote`` + stdlib). The async builder computes the recent DFII10 change + reads the
divergence z; wiring is golden-card-guarded so flag-OFF is byte-identical.

VERIFIED DOCTRINE (web-checked 2026-06-20, primary + reputable)
--------------------------------------------------------------
* **Gold inversely tracks 10Y real (TIPS) yields via the carry/opportunity-cost channel**;
  the in-repo baseline rolling correlation is -0.5..-0.7 (real_yield_gold_check.py:1-7;
  data_pool.py:1118-1150). Rising real yields → gold down. The canonical macro gold driver.
  — federalreserve.gov (DFII10 / TIPS) · the in-repo XAU section + divergence service.
* **At a correlation breakdown the directional read fails** — gold decouples from yields when
  another driver dominates (the divergence alert's whole purpose). Hence the |z|>=2 abstain.
* **Anchors**: a ~40 bp real-yield move over the ~1-month window = full strength (a large
  monthly swing); below a 5 bp noise floor → abstain. Conservative; S05 Brier-fits the weight
  (like every other producer — conviction_fusion.py:53-58).

INVARIANTS (mirror ``dimension_vote`` / ``cot_vote``)
-----------------------------------------------------
* ADR-017 — moves conviction *magnitude*, never the verdict *direction*. XAU polarity: rising
  real yield → ``"down"`` (inverse law); the layer never sets direction, only corroborates.
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0 (asset != XAU,
  non-fresh source, missing age / delta, sub-noise move, OR a detected carry-divergence).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote, VoteDirection

PROVENANCE = "real_yield"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

REAL_YIELD_DIMENSION_VOTE_FLAG = "real_yield_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (SINGLE source of truth, write + read). Absent flag
⇒ both sides no-op ⇒ byte-identical. Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

REAL_YIELD_MAX_AGE_DAYS = 14
"""Freshness window. DFII10 is a daily FRED series; mirrors the section's S04 liveness gate
(data_pool.py:1119 "max-age default 14d"). No publication lag (same-day daily)."""

REAL_YIELD_NOISE_FLOOR_PP = 0.05
"""Below a 5 bp (0.05 percentage-point) real-yield move over the window the change is noise →
abstain (no usable directional signal). Avoids voting on quantisation-level wobble."""

REAL_YIELD_FULL_STRENGTH_PP = 0.40
"""A 40 bp (0.40 pp) real-yield move over the ~1-month window maps to full ``strength`` (1.0);
smaller moves scale linearly. A deliberately HIGH bar (a 40 bp monthly TIPS move is large) so
typical months yield a modest vote (mirror cot's 10 %-OI / volume's 3.0× anchors)."""

REAL_YIELD_DIVERGENCE_ABSTAIN_Z = 2.0
"""When the rolling XAU↔DFII10 correlation z-score is at/above this (the in-repo
``real_yield_gold_check.ALERT_Z_ABS_FLOOR``), the carry relationship has broken down → the
directional read is unreliable → abstain. ``None`` z (not-yet-warm / unavailable) does NOT
gate (fail-open on an unknown reliability signal; the directional move still stands)."""

# Gold only — the real-yield carry channel is asset-specific to gold. FX/indices' macro driver
# is the rate differential, already captured by dollar_coherence (a generic macro vote there
# would double-count it).
_REAL_YIELD_ASSETS: frozenset[str] = frozenset({"XAU_USD"})


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _absent_vote() -> DimensionVote:
    """An honest non-vote (ADR-103): present in the layer list, contributes 0."""
    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=0.0,
        freshness=0.0,
        honest_absence=True,
        directional=True,
    )


def build_real_yield_vote(
    *,
    asset: str,
    status: str,
    real_yield_delta_pp: float | None,
    divergence_z: float | None,
    age_days: int | None,
    max_age_days: int = REAL_YIELD_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map the recent real-yield (DFII10) move to one directional ``DimensionVote`` (pure, no I/O).

    XAU only. Rising real yields → gold down (inverse carry law); the vote moves conviction
    MAGNITUDE in the bucket direction, never sets direction (ADR-017).

    Parameters
    ----------
    asset:
        Ichor asset id. Anything other than ``"XAU_USD"`` abstains.
    status:
        S04 liveness status of the DFII10 source (``classify_liveness``). Fail-closed: only
        ``"fresh"`` votes.
    real_yield_delta_pp:
        Change in DFII10 over the ~1-month window, in PERCENTAGE POINTS (e.g. +0.40 = +40 bp).
        ``None`` (no prior obs in window) → abstain. Non-finite → abstain. ``|delta|`` below the
        5 bp noise floor → abstain.
    divergence_z:
        OPTIONAL rolling XAU↔DFII10 correlation z-score (``real_yield_gold_check``). When
        present and ``|z| >= 2`` (carry relationship broken) → abstain. ``None`` → no gate.
    age_days:
        Age of the latest DFII10 obs in days. ``None`` → abstain.
    max_age_days:
        Freshness window (defaults to 14).

    Returns
    -------
    DimensionVote
        ``provenance="real_yield"``, ``directional=True``. ``honest_absence=True`` (→ 0) when no
        usable read. Otherwise ``"down"`` when real yields rose (gold headwind) / ``"up"`` when
        they fell, ``strength`` the move magnitude vs the 40 bp full-strength bar, ``freshness``
        decaying over the window.
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    if asset not in _REAL_YIELD_ASSETS:
        return _absent_vote()  # carry channel is gold-specific; others covered by dollar/theme
    if status != "fresh":
        return _absent_vote()  # fail-closed: absent / stale / unknown source → abstain
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain
    if real_yield_delta_pp is None or not math.isfinite(real_yield_delta_pp):
        return _absent_vote()  # no readable move / corrupted → abstain
    # Carry-divergence reliability gate: only gate on a KNOWN extreme (fail-open on unknown z).
    if (
        divergence_z is not None
        and math.isfinite(divergence_z)
        and abs(divergence_z) >= REAL_YIELD_DIVERGENCE_ABSTAIN_Z
    ):
        return _absent_vote()  # gold decoupled from real yields → directional read unreliable
    if abs(real_yield_delta_pp) < REAL_YIELD_NOISE_FLOOR_PP:
        return _absent_vote()  # sub-noise real-yield wobble → no directional signal

    # --- Direction: inverse carry law (rising real yield → gold DOWN). -----------------
    direction_hint: VoteDirection = "down" if real_yield_delta_pp > 0 else "up"

    # --- Strength: move magnitude vs the 40 bp full-strength bar. -----------------------
    strength = _clamp(abs(real_yield_delta_pp) / REAL_YIELD_FULL_STRENGTH_PP, 0.0, 1.0)

    # --- Freshness: linear decay over the window (daily FRED, no publication lag). ------
    effective_window = float(max_age_days)
    if effective_window <= 0.0:
        freshness = 1.0 if age_days <= max_age_days else 0.0
    else:
        freshness = _clamp(1.0 - float(age_days) / effective_window, 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint=direction_hint,
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=True,
    )
