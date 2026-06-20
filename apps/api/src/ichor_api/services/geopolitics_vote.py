"""geopolitics_vote.py — Chantier C · the geopolitics (AI-GPR) ``DimensionVote`` producer.

WHY THIS MODULE EXISTS
----------------------
``dimension_vote.py`` (slice-0 / ADR-120) defined the *contract* of one analysis
layer's vote; ``conviction_fusion.fuse_conviction(votes=...)`` (C-2a) opened the
*seam* that fuses ``>= 9`` such votes (today the fuser hard-codes 3 — confluence /
dollar / theme — plus the ``cot`` and ``volume`` producers). This module is the next
one: it maps the **geopolitical-risk regime** Ichor already collects (the AI-GPR index
of Caldara & Iacoviello, ``GprObservation`` / ``data_pool._section_geopolitics``,
z-scored by ``geopol_flash_check.evaluate_geopol_flash``) into a single, bounded,
honest ``DimensionVote``.

It is the "verdict plus intelligent" half of S06 (PLAN_DIRECTEUR §4bis), and the
first-step the prior session scoped (auto_session_resume "First-step (reco PLAN:457)"):
a geopolitics layer that attests "a real geopolitical-risk driver is active right now"
so a directional bucket read is marginally less likely to be noise — making a high
conviction *earned* (grounded in the live risk regime), not an over-confident number
the calibration (ADR-116/118 witness) must shrink to ~50 %.

NON-DIRECTIONAL BY CONSTRUCTION (ADR-017) — THIS IS A DELIBERATE DESIGN CHOICE
-----------------------------------------------------------------------------
An elevated GPR has a *reliable* sign for SOME assets (gold bid, equities depressed)
but a **regime-conditional** sign for others: the USD is a safe haven only in funding
stress, NOT pure geopolitical shocks, and on US-driven instability the dollar-smile
flips (the in-repo flash check states this verbatim — ``geopol_flash_check.py:62-65``:
"Direction is regime-dependent (USD up vs. risk-off, but can flip on US-driven
instability per ADR-037 dollar-smile switch)"). A fixed per-asset long/short polarity
would therefore **fabricate** direction on the FX legs a large fraction of the time —
exactly the ADR-017 fake-edge. So this vote is built ``directional=False`` /
``direction_hint="neutral"`` (structurally identical to ``volume_vote``): in the fuser
it contributes **only** an anti-uncertainty credit (``uncertainty_credit()`` ≥ 0, like
the ``theme`` presence layer) and can NEVER carry a tilt — making the layer structurally
incapable of violating the ADR-017 direction invariant. The directional gold/equity
overlay (which the doctrine *does* support, at confirmed spikes, behind a regime
classifier) is deferred to S05 with Brier calibration.

GLOBAL, NOT PER-ASSET (honest limitation, surfaced not hidden)
-------------------------------------------------------------
AI-GPR is a single GLOBAL scalar (identical for every asset by construction —
``data_pool.py:5017``). So this vote attaches the SAME anti-uncertainty credit to all 5
assets. That is a real limitation (no per-asset differentiation), but an honest one: it
says "the market-wide geopolitical-risk backdrop is elevated", which legitimately makes
*every* asset's directional read a little less likely to be pure noise.

NOT WIRED (gated).  This file is a **pure, I/O-free primitive mapper** only. It is
unit-testable in isolation and imports nothing but ``dimension_vote`` + stdlib (the
fuser refuses heavier deps — ADR-120). The live wiring — calling
``evaluate_geopol_flash`` inside ``run_session_card`` / ``build_session_verdict`` and
passing the vote into ``fuse_conviction`` behind a feature flag — is the gated wiring
slice (write-side capture + read-side fuse, golden-card-guarded so the migration is
byte-identical when the flag is OFF). Keeping the producer pure means that wiring is a
thin step with no logic of its own (mirror ``cot_vote`` / ``volume_vote``).

VERIFIED TRADING DOCTRINE (web-checked 2026-06-20, primary + reputable sources)
------------------------------------------------------------------------------
* **GPR is the Caldara-Iacoviello newspaper-based geopolitical-risk index** (a global
  scalar normalised to ~100 over the benchmark period); the AI-GPR variant scores ~5M
  articles. It is a *risk-level*, not a directional forecast in itself.
  — policyuncertainty.com/gpr.html · federalreserve.gov/econres/ifdp/files/ifdp1222r1.pdf
* **Rising GPR depresses equities and bids gold** (the reliable legs); IMF GFSR Apr-2025
  ch.2: major geopolitical events trigger significant stock-price declines. This is real
  but is captured here as anti-uncertainty MAGNITUDE, not a tilt (see below).
  — imf.org/-/media/files/publications/gfsr/2025/april/english/ch2.pdf ·
    sciencedirect.com/science/article/abs/pii/S030142072030903X (gold safe haven)
* **The FX / USD sign is REGIME-CONDITIONAL.** A global risk shock bids USD/JPY/CHF and
  weakens EUR/GBP *only* during funding stress, not pure geopolitical shocks — so the FX
  leg cannot carry a fixed directional sign. This is the core reason the vote is
  non-directional. — newyorkfed.org/.../global-risk-dollar.pdf · geopol_flash_check.py:62-65
* **The effect is REGIME-DEPENDENT, strongest at spikes — noise in calm times.** The
  in-repo GEOPOL_FLASH alert fires only at ``|z| >= 2.0`` against the trailing 30-day
  baseline (``geopol_flash_check.py:55``). The vote rides the SAME 30-day z-score and
  reserves full strength for that documented spike bar; below a 0.5 σ floor a near-mean
  reading attests no elevated driver → strength 0.
* **Publication lag.** The AI-GPR feed publishes with ~8-day lag (measured in prod
  2026-06-08, ``data_pool.py:3542``). Freshness subtracts the unavoidable lag so a
  just-published reading scores 1.0, then decays over the remaining window.

INVARIANTS (mirror ``dimension_vote`` / ``volume_vote`` / ``cot_vote``)
----------------------------------------------------------------------
* ADR-017 — non-directional: ``directional=False``, ``direction_hint="neutral"``;
  contributes magnitude (anti-uncertainty) only, never a direction.
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0
  (non-fresh source, missing age, z-score below warmup / degenerate / non-finite).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped before construction); one full-strength geo
  vote lifts the agreement factor by at most ``VOTE_GAIN_K`` (≤ +0.10), bounded by
  ``AGREEMENT_CEIL`` — corroboration, never manufactured certainty.
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote

# --------------------------------------------------------------------------- #
# Constants (principled priors — doubly anchored: in-repo flash + web doctrine). #
# --------------------------------------------------------------------------- #

PROVENANCE = "geopolitics"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

GEOPOLITICS_DIMENSION_VOTE_FLAG = "geopolitics_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (write-side capture in ``run_session_card`` +
read-side fuse in ``build_session_verdict``). Defined here — the dimension's home — as the
SINGLE source of truth so the write site and the read site can never typo-diverge
(feature_flags has no central registry). Absent flag ⇒ ``is_enabled`` returns False ⇒ both
sides no-op ⇒ byte-identical to the legacy path (``votes=()`` — C-2a). Mirrors
``cot_vote.COT_DIMENSION_VOTE_FLAG`` / ``volume_vote.VOLUME_DIMENSION_VOTE_FLAG``."""

GPR_MAX_AGE_DAYS = 14
"""Freshness window. Mirrors ``data_pool._GPR_MAX_AGE_DAYS`` (data_pool.py:3542) so the
vote's freshness window matches the geopolitics section's S04 liveness gate exactly
(AI-GPR is daily but publishes with ~8-day lag)."""

GPR_PUBLICATION_LAG_DAYS = 8
"""The AI-GPR feed publishes with ~8-day lag (measured in prod 2026-06-08,
``data_pool.py:3542``). Freshness subtracts this unavoidable lag so a just-published
reading scores 1.0 (not ~0.43), then decays over the remaining window. Must be < max age."""

GPR_BASELINE_Z = 0.5
"""30-day z-score at/below which an elevated-GPR reading adds NO anti-uncertainty credit
(strength 0). Below ~0.5 σ above its trailing baseline the AI-GPR is near its mean — no
*new* geopolitical pressure, nothing to corroborate. Two-sided note: a NEGATIVE z (an
unusually CALM GPR) is also strength 0 — calm is the absence of a driver, never a
credit (so the producer uses the SIGNED z, positive side only, NOT ``|z|``: this differs
on purpose from the GEOPOL_FLASH alert which fires on ``|z|`` because a collapse in risk
is newsworthy, but it is not an *active driver* for the verdict)."""

GPR_FULL_STRENGTH_Z = 2.0
"""30-day z-score mapping to full ``strength`` (1.0). Anchored on
``geopol_flash_check.ALERT_Z_ABS_FLOOR = 2.0`` — the in-repo "this is a real
geopolitical spike" threshold (the exact analogue of ``cot``'s 10 %-OI bar and
``volume``'s 3.0× bar). A deliberately HIGH bar so typical calm-geopolitics weeks yield
a *modest* vote and only a genuine spike earns the full single-layer anti-uncertainty
credit (≤ +0.10 agreement factor — never manufacturing certainty, ADR-022). Between the
0.5 σ baseline and the 2.0 σ spike the strength scales linearly (z = 1 → ~0.33)."""


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _absent_vote() -> DimensionVote:
    """An honest non-vote (ADR-103): present in the layer list, contributes 0.

    Non-directional (``directional=False``) like every geo vote — a geopolitics layer
    never carries a tilt, even when absent (ADR-017)."""
    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=0.0,
        freshness=0.0,
        honest_absence=True,
        directional=False,
    )


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def build_geopolitics_vote(
    *,
    status: str,
    z_score: float | None,
    age_days: int | None,
    max_age_days: int = GPR_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map the AI-GPR 30-day z-score to one ``DimensionVote`` (pure, no I/O).

    The vote is ALWAYS non-directional (``directional=False`` / ``direction_hint="neutral"``):
    geopolitical risk has a regime-conditional sign across assets, so the layer confirms
    that an elevated-risk driver is *active* (anti-uncertainty), never a long/short tilt
    (ADR-017). In the fuser it contributes only ``uncertainty_credit()`` ≥ 0.

    The vote is GLOBAL (no ``asset`` parameter): AI-GPR is one market-wide scalar, so the
    same credit attaches to every asset. The caller still invokes it per asset (the
    write-side loops per asset), each receiving the identical global vote.

    Parameters
    ----------
    status:
        S04 liveness status of the AI-GPR source (``"fresh"`` / ``"stale"`` / ``"absent"``,
        from ``classify_liveness``). **Fail-closed: only ``"fresh"`` votes** — any other
        status abstains, so the mapper never relies on the caller passing an internally
        consistent ``(status, age_days)`` pair.
    z_score:
        The trailing-30-day AI-GPR z-score (``geopol_flash_check.GeopolFlashResult.z_score``).
        ``None`` (insufficient history < 20 obs, or a degenerate zero-std baseline) →
        abstain. A non-finite z → abstain (corrupted). Only the POSITIVE tail above the
        0.5 σ baseline adds credit (an unusually calm GPR is no driver → strength 0).
    age_days:
        Age of the latest AI-GPR reading in days (from ``classify_liveness``). ``None`` →
        abstain (cannot verify freshness). Drives the lag-aware freshness decay.
    max_age_days:
        Freshness window (defaults to the section's 14-day AI-GPR gate).

    Returns
    -------
    DimensionVote
        ``provenance="geopolitics"``, ``directional=False``, ``direction_hint="neutral"``.
        ``honest_absence=True`` (→ exactly 0) whenever there is no usable read (non-fresh
        source, missing age, z below warmup / degenerate / non-finite). Otherwise a neutral
        vote whose ``strength`` scales the above-baseline GPR z-score (0 at/below 0.5 σ, 1
        at a 2.0 σ spike) and whose ``freshness`` decays over the post-lag window. A reading
        at/below baseline is a present, strength-0 vote (also contributes 0 — honest "no
        elevated geopolitical driver", not an absence).
    """
    # --- Honest-absence gates (ADR-103): each is a reason there is no usable read. --
    if status != "fresh":
        return _absent_vote()  # fail-closed: absent / stale / unknown source → abstain
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain rather than assume
    if z_score is None:
        return _absent_vote()  # insufficient history / degenerate baseline → not warm
    if not math.isfinite(z_score):
        return _absent_vote()  # corrupted z → refuse to map rather than mis-bucket

    # --- Strength: above-baseline POSITIVE z (elevated risk). Signed, not |z|. --------
    # A z at/below the 0.5 σ baseline (incl. any negative z = unusually calm) → strength 0:
    # no *new* geopolitical pressure means nothing to corroborate.
    span = GPR_FULL_STRENGTH_Z - GPR_BASELINE_Z
    strength = _clamp((z_score - GPR_BASELINE_Z) / span, 0.0, 1.0) if span > 0.0 else 0.0

    # --- Freshness: lag-aware decay (a just-published ~8-day-old reading scores 1.0). --
    effective_window = float(max_age_days - GPR_PUBLICATION_LAG_DAYS)
    if effective_window <= 0.0:
        freshness = 1.0 if age_days <= max_age_days else 0.0
    else:
        staleness = max(0.0, float(age_days) - GPR_PUBLICATION_LAG_DAYS)
        freshness = _clamp(1.0 - staleness / effective_window, 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=False,
    )
