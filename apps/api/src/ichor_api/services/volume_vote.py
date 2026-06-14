"""volume_vote.py — Chantier C · C-3 slice : the relative-volume ``DimensionVote`` producer.

WHY THIS MODULE EXISTS
----------------------
``dimension_vote.py`` (slice-0 / ADR-120) defined the *contract* of one analysis
layer's vote; ``conviction_fusion.fuse_conviction(votes=...)`` (C-2a) opened the
*seam* that fuses ``>= 9`` such votes (today the fuser hard-codes only 3: confluence
/ dollar / theme; ``cot_vote`` added the first directional producer). This module is
the next one: it maps the **relative-volume / participation** read Ichor already
collects (``microstructure.RelativeVolumeReading`` via
``data_pool._section_volume_rvol``) into a single, bounded, honest ``DimensionVote``.

It is the "verdict plus intelligent" half of S06 (PLAN_DIRECTEUR §4bis), and it is the
dimension most directly tied to the owner's stated method — *"profiter du volume de la
session de New York"* (Session-06 prompt, « Mon style de trading »): a session move
backed by real participation is less likely to be noise, so a directional read earns a
little more conviction; a move on thin volume earns none.

NON-DIRECTIONAL BY CONSTRUCTION (ADR-017)
-----------------------------------------
Volume confirms the *strength / participation* of a move, **never its direction**
(up vs down). This is the technical-analysis canon (Dow theory: "volume must confirm
the trend") and is already asserted in ``microstructure._volume_bucket`` ("Descriptive
only (ADR-017): magnitude of participation, never a direction"). So this vote is built
with ``directional=False`` / ``direction_hint="neutral"``: in the fuser it contributes
**only** an anti-uncertainty credit (``uncertainty_credit()`` ≥ 0, exactly like the
``theme`` presence layer), and it can NEVER carry a long/short tilt. This makes the
layer structurally incapable of violating the ADR-017 direction invariant — the single
biggest risk class in the fuser — which is why it is the lowest-CI-risk next dimension.

NOT WIRED (gated).  This file is a **pure, I/O-free primitive mapper** only. It is
unit-testable in isolation and imports nothing but ``dimension_vote`` + stdlib (the
fuser refuses heavier deps — ADR-120). The live wiring — reading the
``RelativeVolumeReading`` inside ``build_session_verdict`` and passing the vote into
``fuse_conviction`` behind a feature flag — is the next GATED slice (write-side capture
in ``run_session_card`` + read-side fuse, golden-card-guarded so the migration is
byte-identical when the flag is OFF). Keeping the producer pure means that wiring is a
thin step with no logic of its own.

VERIFIED TRADING DOCTRINE (web-checked 2026-06-14, primary + reputable sources)
------------------------------------------------------------------------------
* **RVOL = current volume / trailing-average volume; 1.0 = exactly average.** The
  practitioner scale: ``>= 1.25`` starts "elevated participation" (the in-repo
  ``_volume_bucket`` cut), the ``3-5×`` band is "strong interest / ideal momentum", and
  ``> 4×`` is a true catalyst "volume spike". So full single-layer credit is reserved
  for genuinely strong participation (anchored at 3.0×), NOT a mere 1.5× tick-up.
  — chartschool.stockcharts.com/.../relative-volume-rvol (formula + ">4.0 spike") ·
  tradingsim.com/blog/relative-volume-rvol.
* **Volume is NON-directional (Dow theory).** It confirms the strength / validity of a
  move, not its up/down direction; "volume must confirm the trend". RVOL is a
  *confirming*, not predictive, indicator. — fidelity.com (Dow theory) · ebc.com Dow
  Theory tenets.
* **Below-average participation = NO confirmation, not anti-confirmation.** A thin-
  volume move is less reliable / more whipsaw-prone, but the honest read is "absence of
  validation", not a directional signal — so light participation contributes 0, never a
  fabricated penalty. — navia.co.in (volume in reversal patterns) · financestrategists
  (low-volume pullback).
* **FX has no consolidated venue volume.** Spot FX is decentralised/OTC; any "volume" is
  one broker's tick count, not transacted size → unreliable. Index futures (CME E-mini)
  and exchange-listed instruments publish true consolidated volume → the clean case;
  gold via futures/ETF, not spot. Validates restricting this vote to ``SPX500`` /
  ``NAS100`` / ``XAU``. — hw.online (FX volume transparency) · cmegroup.com.

DEFERRED REFINEMENTS (documented scope — NOT a silent gap)
----------------------------------------------------------
The conservative full-strength bar (3.0×) + the non-directional nature bound the damage
of the two effects below; modelling them needs context this pure mapper does not carry,
so they are explicit NEXT slices (mirror ``cot_vote``'s deferred 3-year-index extreme):
* **Calendar-mechanical volume** (quad-witching ≈ +40-53 %, index rebalancing, the
  futures-roll window, holiday half-days ≈ −30-60 %) inflates/deflates RVOL without
  conviction. A quad-witching ~1.45× already maps to only ~0.11 strength here, so the
  high bar absorbs most of it; a date-aware mask is the robust follow-up.
  — cmegroup.com (SOQ / roll dates) · nyse.com (calendar).
* **Exhaustion tail.** A > 4× spike at an overbought/oversold extreme can foreshadow
  reversal, not continuation (non-monotonic) — but as a *non-directional* credit this
  only adds general anti-uncertainty, never a tilt, so the risk is limited.

INVARIANTS (mirror ``dimension_vote`` / ``cot_vote``)
-----------------------------------------------------
* ADR-017 — non-directional: ``directional=False``, ``direction_hint="neutral"``;
  contributes magnitude (anti-uncertainty) only, never a direction.
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0
  (asset off-whitelist / FX, non-fresh source, missing age, no RVOL ratio i.e.
  insufficient history, non-finite / non-positive ratio).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped before construction); one full-strength
  volume vote lifts the agreement factor by at most ``VOTE_GAIN_K`` (≤ +0.10), bounded
  by ``AGREEMENT_CEIL`` — corroboration, never manufactured certainty.
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote

# --------------------------------------------------------------------------- #
# Constants (principled priors — doubly anchored: in-repo section + web doctrine). #
# --------------------------------------------------------------------------- #

PROVENANCE = "volume"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

VOLUME_DIMENSION_VOTE_FLAG = "volume_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (write-side capture in ``run_session_card``
+ read-side fuse in ``build_session_verdict``). Defined here — the dimension's home —
as the SINGLE source of truth so the write site and the read site can never typo-
diverge (feature_flags has no central registry). Absent flag ⇒ ``is_enabled`` returns
False ⇒ both sides no-op ⇒ byte-identical to the legacy path (``votes=()`` — C-2a).
Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

VOLUME_MAX_AGE_DAYS = 5
"""Freshness window. Mirrors ``data_pool._VOLUME_RVOL_MAX_AGE_DAYS`` (data_pool.py:3515)
so the vote's freshness window matches the section's S04 liveness gate exactly (daily
market_data volume; 5 days covers long weekends / holidays)."""

VOLUME_BASELINE_RVOL = 1.25
"""RVOL at/below which participation adds NO conviction credit (strength 0). Anchored on
``microstructure._volume_bucket``'s "elevated participation" cut (rvol_ratio >= 1.25,
microstructure.py:399): average and merely modestly-above-average participation (the web
"~1.1 may not be worth acting on" band) corroborate nothing. Only genuinely elevated
participation begins to count."""

VOLUME_FULL_STRENGTH_RVOL = 3.0
"""RVOL mapping to full ``strength`` (1.0). Anchored on the web "strong interest / ideal
momentum" band (3-5×) rather than the section's display "spike" label (2.0) — a
deliberately HIGH bar (mirror ``cot_vote``'s 10 %-OI bar) so typical sessions yield a
*modest* vote and only strong participation earns the full single-layer credit
(≤ +0.10 agreement factor — never manufacturing certainty, ADR-022). Between baseline
and full the strength scales linearly (2.0× "elevated floor" → ~0.43)."""


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _absent_vote() -> DimensionVote:
    """An honest non-vote (ADR-103): present in the layer list, contributes 0.

    Non-directional (``directional=False``) like every volume vote — a volume layer
    never carries a tilt, even when absent (ADR-017)."""
    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=0.0,
        freshness=0.0,
        honest_absence=True,
        directional=False,
    )


# Volume-bearing assets: mirror of ``data_pool._VOLUME_ASSETS`` (data_pool.py:3521).
# Decoupled on purpose (the fuser-importable producer must not import the heavy
# ``data_pool`` module — ADR-120 purity); the section's own honest-N/A path covers FX,
# this guard covers the whitelist on the producer side.
_VOLUME_VOTE_ASSETS: frozenset[str] = frozenset({"SPX500_USD", "NAS100_USD", "XAU_USD"})


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def build_volume_vote(
    *,
    asset: str,
    status: str,
    volume_available: bool,
    rvol_ratio: float | None,
    age_days: int | None,
    volume_zscore: float | None = None,
    max_age_days: int = VOLUME_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map a relative-volume / participation read to one ``DimensionVote`` (pure, no I/O).

    The vote is ALWAYS non-directional (``directional=False`` / ``direction_hint="neutral"``):
    volume confirms a move's *participation*, never its *direction* (ADR-017). In the fuser
    it contributes only an anti-uncertainty credit (``uncertainty_credit()`` ≥ 0).

    Parameters
    ----------
    asset:
        Ichor asset id (e.g. ``"SPX500_USD"``). Only the volume-bearing assets
        (``SPX500_USD`` / ``NAS100_USD`` / ``XAU_USD``) can vote; FX abstains (no
        consolidated venue volume).
    status:
        S04 liveness status of the volume source (``"fresh"`` / ``"stale"`` /
        ``"absent"``, from ``classify_liveness``). **Fail-closed: only ``"fresh"``
        votes** — any other status abstains, so the mapper never relies on the caller
        passing an internally-consistent ``(status, age_days)`` pair.
    volume_available:
        ``RelativeVolumeReading.volume_available``. ``False`` (FX, no venue volume) →
        abstain. Belt-and-suspenders with the asset whitelist below.
    rvol_ratio:
        ``RelativeVolumeReading.rvol_ratio`` = current / trailing-average daily volume.
        ``None`` (insufficient history / no positive current volume) → abstain. A non-
        finite or non-positive ratio → abstain (corrupted) rather than mis-mapped.
    age_days:
        Age of the latest volume bar in days (from ``classify_liveness``). ``None`` →
        abstain (cannot verify freshness). Drives the freshness decay.
    volume_zscore:
        OPTIONAL daily-volume z-score (``RelativeVolumeReading.volume_zscore``). Reserved
        for an S05 Brier-fit refinement (mirror ``cot_vote.cot_index_pct``); today the
        smooth ``rvol_ratio`` is the sole magnitude driver — accepted but not yet
        consumed, to keep the first slice deterministic and free of extra magic numbers.
    max_age_days:
        Freshness window (defaults to the section's 5-day volume gate).

    Returns
    -------
    DimensionVote
        ``provenance="volume"``, ``directional=False``, ``direction_hint="neutral"``.
        ``honest_absence=True`` (→ exactly 0) whenever there is no usable participation
        read. Otherwise a neutral vote whose ``strength`` is the above-baseline RVOL
        magnitude (0 at/below the "elevated" cut, 1 at a 3× strong-participation read) and
        whose ``freshness`` decays over the volume window. A read at/below baseline is a
        present, strength-0 vote (also contributes 0 — honest "no extra confirmation",
        not an absence).
    """
    # --- Honest-absence gates (ADR-103): each is a reason there is no usable read. --
    if asset not in _VOLUME_VOTE_ASSETS:
        return _absent_vote()  # FX / unknown asset → no consolidated venue volume
    if not volume_available:
        return _absent_vote()  # reading itself reports no venue volume
    if status != "fresh":
        return _absent_vote()  # fail-closed: absent / stale / unknown source → abstain
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain rather than assume
    if rvol_ratio is None:
        return _absent_vote()  # insufficient history / no positive current volume
    if not math.isfinite(rvol_ratio) or rvol_ratio <= 0.0:
        return _absent_vote()  # corrupted ratio → refuse to map rather than mis-bucket

    # --- Strength: above-baseline participation magnitude, anchored on the section. --
    # Only participation above the "elevated" cut (1.25×) adds anti-uncertainty credit;
    # at or below it the strength clamps to 0 (a thin / average move corroborates nothing).
    span = VOLUME_FULL_STRENGTH_RVOL - VOLUME_BASELINE_RVOL
    strength = _clamp((rvol_ratio - VOLUME_BASELINE_RVOL) / span, 0.0, 1.0)

    # --- Freshness: linear decay over the volume window (daily data, no publication
    # lag — unlike COT's Tue→Fri release lag). A same-day bar scores 1.0. ---
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
    )
