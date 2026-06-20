"""sentiment_vote.py — Chantier C · the retail-positioning ``DimensionVote`` producer.

WHY THIS MODULE EXISTS
----------------------
``dimension_vote.py`` (slice-0 / ADR-120) defined the *contract*; ``conviction_fusion``
(C-2a) opened the seam; ``cot_vote`` / ``volume_vote`` / ``geopolitics_vote`` /
``positioning_tff_vote`` are the producers shipped so far. This is the **sentiment** layer
the S04 prompt lists ("sentiment du marché"): it maps the **MyFXBook Community Outlook**
retail FX positioning Ichor already collects (``MyfxbookOutlook`` /
``data_pool._section_myfxbook_outlook``) into one bounded, honest ``DimensionVote``.

DIRECTIONAL — CONTRARIAN (fade the crowd), the OPPOSITE sign convention to ``cot_vote``
-------------------------------------------------------------------------------------
Managed money (COT) = smart money → FOLLOW it (momentum). Retail crowd (MyFXBook) = exit
liquidity → FADE it (contrarian). So a retail **long** extreme votes the asset **down**, a
retail **short** extreme votes it **up**. The pair is the Ichor asset directly (MyFXBook
``EURUSD`` long_pct IS ``EUR_USD``), so — unlike COT's foreign-leg reversal — there is NO
polarity flip: crowd-long ⇒ down for every covered asset. This is the single biggest trap
in this module (a copy-paste of COT's momentum sign would invert every vote), so the sign
is set explicitly and locked by a per-asset unit test.

ADR-017 holds: the vote moves conviction MAGNITUDE/agreement (signed_contribution × the
bucket direction_num in the fuser), it NEVER sets the verdict direction — the buckets do.

DORMANT-BY-DEFAULT IS A FEATURE (honest absence)
------------------------------------------------
The MyFXBook collector only runs when ``ICHOR_API_MYFXBOOK_EMAIL`` / ``_PASSWORD`` are set
(``collectors/myfxbook_outlook.py:84-85,218``); otherwise it is dormant and the table is
empty. The builder then yields an honest-absence vote (contributes EXACTLY 0 — ADR-103),
which is correct: with no retail-positioning data there is no sentiment edge to fabricate.
Set the two env vars (owner action) to activate the live signal; the producer needs no
change.

NON-INDEX BY CONSTRUCTION
-------------------------
MyFXBook only covers FX + gold (``ICHOR_PAIRS`` = EURUSD/GBPUSD/USDJPY/AUDUSD/USDCAD/XAUUSD,
``myfxbook_outlook.py:54-56``). Of Ichor's 5 assets, that is EUR_USD / GBP_USD / XAU_USD;
SPX500 / NAS100 have no retail-FX-positioning source → they abstain honestly. (AAII for the
indices is a GLOBAL, weekly, modest-effect number — deferred to S05 Brier-fitting.)

NOT WIRED (gated). Pure, I/O-free primitive mapper (ADR-120: imports nothing but
``dimension_vote`` + stdlib). The live wiring (fetch the latest ``MyfxbookOutlook`` row in
the builder + fuse behind a flag) is the gated slice, golden-card-guarded so the migration
is byte-identical when the flag is OFF.

VERIFIED TRADING DOCTRINE (web-checked 2026-06-20, reputable sources)
--------------------------------------------------------------------
* **Retail FX positioning is CONTRARIAN — retail = exit liquidity.** The crowd is
  historically offside at turning points; the operative band is 70-85 % one-side
  (< ~65 % = noise, sweet spot 75-85 %, > 85 % = maximum/rare). It CONFIRMS a thesis, it
  does not time one alone. — propfirmscan.com/research/retail-positioning ·
  fxleaders.com/news/the-great-contrarian-indicator-retail-sentiment
* **Fade extremes, not the marginal tilt.** A 55 % skew is noise; the edge lives in the
  tail — hence the high full-strength bar (85 %) and the 60 % floor below which strength is
  0 (mirror ``cot``'s 10 %-OI and ``volume``'s 3.0× conservative anchors).

INVARIANTS (mirror ``dimension_vote`` / ``cot_vote``)
-----------------------------------------------------
* ADR-017 — moves conviction *magnitude*, never *direction*; CONTRARIAN per-asset sign.
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0 (asset off
  the MyFXBook whitelist, non-fresh source, missing age, missing / corrupted percentages,
  or a sub-extreme crowd skew → present-strength-0).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped before construction).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

import math

from .dimension_vote import DimensionVote, VoteDirection

# --------------------------------------------------------------------------- #
# Constants (principled priors — documented; S05 fits these from Brier).        #
# --------------------------------------------------------------------------- #

PROVENANCE = "sentiment"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

SENTIMENT_DIMENSION_VOTE_FLAG = "sentiment_dimension_vote_enabled"
"""Feature-flag key gating the live wiring. SINGLE source of truth so the write site and
the read site can never typo-diverge. Absent flag ⇒ ``is_enabled`` False ⇒ both sides no-op
⇒ byte-identical to the legacy path (``votes=()``). Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

SENTIMENT_MAX_AGE_DAYS = 3
"""Freshness window. Retail positioning is real-time-ish but a snapshot ages across a
weekend; 3 days keeps a Friday read usable into Monday. No publication lag (unlike COT)."""

SENTIMENT_EXTREME_FLOOR = 60.0
"""One-side % at/below which the crowd skew adds NO conviction (strength 0). Below ~65 % the
retail tilt is noise (propfirmscan / fxleaders); 60 is a slightly conservative floor."""

SENTIMENT_FULL_STRENGTH = 85.0
"""One-side % mapping to full ``strength`` (1.0) — the "maximum contrarian / extremely rare"
band. A deliberately HIGH bar so typical weeks yield a modest vote and only a genuine crowd
extreme earns the full single-layer credit (≤ +0.10 agreement, ADR-022). A 75 % read (the
in-repo ``_section_myfxbook_outlook`` extreme flag, data_pool.py:4173) → ~0.60 strength."""

# Ichor assets MyFXBook covers (FX + gold). The pair IS the asset directly, so the
# contrarian sign needs no foreign-leg reversal. SPX500 / NAS100 have no retail-FX source.
_SENTIMENT_ASSETS: frozenset[str] = frozenset({"EUR_USD", "GBP_USD", "XAU_USD"})


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def build_sentiment_vote(
    *,
    asset: str,
    status: str,
    long_pct: float | None,
    short_pct: float | None,
    age_days: int | None,
    max_age_days: int = SENTIMENT_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map MyFXBook retail positioning to one CONTRARIAN ``DimensionVote`` (pure, no I/O).

    Parameters
    ----------
    asset:
        Ichor asset id. Only ``EUR_USD`` / ``GBP_USD`` / ``XAU_USD`` vote; others abstain.
    status:
        S04 liveness status of the MyFXBook source (``classify_liveness``). **Fail-closed:
        only ``"fresh"`` votes** (a dormant collector → empty table → absent → abstain).
    long_pct / short_pct:
        Latest community-outlook percentages (0-100, complementary). ``None`` / non-finite /
        out-of-range / not summing to ~100 → abstain (corrupted snapshot).
    age_days:
        Age of the latest snapshot in days (``classify_liveness`` on ``fetched_at``).
    max_age_days:
        Freshness window (defaults to 3 days).

    Returns
    -------
    DimensionVote
        ``provenance="sentiment"``, ``directional=True``. CONTRARIAN: crowd-long ⇒ ``"down"``,
        crowd-short ⇒ ``"up"``. ``honest_absence=True`` (→ 0) when there is no usable read.
        A sub-60 % crowd skew is a present, strength-0 vote (contributes 0 — honest "no crowd
        extreme", not an absence). ``strength`` scales the one-side % from 60 (→0) to 85 (→1);
        ``freshness`` decays linearly over the window.
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    if asset not in _SENTIMENT_ASSETS:
        return _absent_vote()  # index / unsupported asset → no retail-positioning source
    if status != "fresh":
        return _absent_vote()  # fail-closed: dormant / stale / unknown source → abstain
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain rather than assume
    if long_pct is None or short_pct is None:
        return _absent_vote()  # missing percentages
    if not (math.isfinite(long_pct) and math.isfinite(short_pct)):
        return _absent_vote()  # corrupted
    if not (0.0 <= long_pct <= 100.0 and 0.0 <= short_pct <= 100.0):
        return _absent_vote()  # out of range → corrupted
    if not (95.0 <= long_pct + short_pct <= 105.0):
        return _absent_vote()  # not complementary (~100) → corrupted snapshot

    # --- Direction: CONTRARIAN (fade the crowd). Pair == asset → no reversal. ----------
    # Tie (50/50) resolves to "down" but skew == 50 < floor → strength 0 → inert anyway.
    crowd_is_long = long_pct >= short_pct
    direction_hint: VoteDirection = "down" if crowd_is_long else "up"

    # --- Strength: above-floor one-side %, anchored on the contrarian band. ------------
    skew = max(long_pct, short_pct)
    span = SENTIMENT_FULL_STRENGTH - SENTIMENT_EXTREME_FLOOR
    strength = _clamp((skew - SENTIMENT_EXTREME_FLOOR) / span, 0.0, 1.0) if span > 0.0 else 0.0

    # --- Freshness: linear decay over the window (no publication lag). -----------------
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
