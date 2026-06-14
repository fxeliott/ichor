"""cot_vote.py — Chantier C · C-3 slice-0 : the first real ``DimensionVote`` producer.

WHY THIS MODULE EXISTS
----------------------
``dimension_vote.py`` (slice-0 / ADR-120) defined the *contract* of one analysis
layer's vote; ``conviction_fusion.fuse_conviction(votes=...)`` (C-2a) opened the
*seam* that fuses ``>= 9`` such votes (today the fuser hard-codes only 3:
confluence / dollar / theme). Neither shipped a real *producer*. This module is
the first one: it maps the **CFTC COT (Commitments of Traders) "managed money"
positioning** that Ichor already collects (``CotPosition`` / ``data_pool._section_cot``)
into a single, bounded, honest ``DimensionVote``.

It is the "verdict plus intelligent" half of S06 (PLAN_DIRECTEUR §4bis): a fourth,
independent dimension that can *corroborate or contradict* the bucket-derived
direction, so a high conviction is *earned* (grounded in real positioning), not an
over-confident number the calibration (ADR-116/118 witness) must shrink to ~50 %.

NOT WIRED (gated).  This file is a **pure, I/O-free primitive mapper** only. It is
unit-testable in isolation and imports nothing but ``dimension_vote`` + stdlib (the
fuser refuses heavier deps — ADR-120). The live wiring — extracting these primitives
from ``CotPosition`` rows inside ``build_session_verdict`` and passing the vote into
``fuse_conviction`` behind a feature flag — is the next GATED slice (C-3b: DB read on
the async path + flag + deploy + witness). Keeping the producer pure means C-3b is a
thin, golden-card-guarded wiring step with no logic of its own.

VERIFIED TRADING DOCTRINE (web-checked 2026-06-14, primary + reputable sources)
-------------------------------------------------------------------------------
* **Flow = momentum, NOT contrarian.** A *building* managed-money net position
  (4-week change in ``managed_money_net``) is read as trend-confirmation: managed
  money = CTAs / hedge funds, the quintessential momentum players. The contrarian
  read only applies at **statistical extremes** (see below). So the directional
  signal here is ``sign(Δ4w managed_money_net)``, mapped to the asset.
  — cftc.gov (data definitions) · metalcharts.org/cot · luna3.ai/how-to-read-cot-report
* **Extremes = abstain (not auto-flip).** At a 3-year **COT-Index** extreme
  (> 90th / < 10th percentile) the momentum sign is unreliable and the contrarian
  regime begins — but every source stresses an extreme is a *risk condition*, not a
  *timing trigger*. The conservative first-slice behaviour is to **suppress** the
  vote at a detected extreme, not to invert it (full contrarian logic needs
  technical confirmation → deferred). Extreme detection needs a 3-year history we
  don't carry yet, so ``cot_index_pct`` is an OPTIONAL input (``None`` = unknown →
  cannot abstain on extreme; the conservative magnitude cap below bounds the damage).
  — wallstreetcourier.com · hiddenmetrix.com/guide/cot-reports · tradealgo.com
* **1-week contradiction = inflection → dampen.** If the latest 1-week flow sign
  -contradicts the 4-week trend, conviction is *reduced* (early-warning inflection),
  never reversed on one week. — luna3.ai · forexfundamentals.com/learn/cot-data-reversals
* **Normalise to open interest.** ``Δnet / open_interest`` ("% of open interest" is
  an official CFTC report category) makes the flow comparable across contracts of
  very different size. — cftc.gov (About the COT Reports)
* **Publication lag.** Data = Tuesday close, released Friday 3:30 pm ET (~3-day lag),
  ageing to ~7-10 days before the next report → freshness uses a 14-day window that
  matches ``data_pool._COT_MAX_AGE_DAYS``. — cftc.gov (Release Schedule)

INVARIANTS (mirror ``dimension_vote`` / ``conviction_fusion``)
--------------------------------------------------------------
* ADR-017 — this vote moves conviction *magnitude*, never the verdict *direction*
  (the fuser fixes direction from the buckets; a ``DimensionVote`` only tilts the
  agreement factor). Polarity is per-asset (the COT contract is the *foreign* leg
  for USD-base pairs → reverse sign).
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0
  (asset outside the COT whitelist, empty/absent table, stale report, missing
  open interest, insufficient history, negligible flow, or a detected extreme).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped before construction), so a single
  positioning layer can never manufacture certainty.
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

from .dimension_vote import DimensionVote, VoteDirection

# --------------------------------------------------------------------------- #
# Constants (principled priors — documented; S05 fits these from Brier).       #
# --------------------------------------------------------------------------- #

PROVENANCE = "cot"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

COT_MAX_AGE_DAYS = 14
"""Freshness window. Mirrors ``data_pool._COT_MAX_AGE_DAYS`` (data_pool.py:3512) so
the vote's freshness decay matches the section's S04 liveness gate exactly. CFTC COT
is weekly; a report ~3 days old on release ages toward this bound before the next."""

COT_FULL_STRENGTH_OI_FRACTION = 0.10
"""A 4-week managed-money repositioning equal to **10 % of open interest** maps to
full ``strength`` (1.0); smaller flows scale linearly. A deliberately HIGH bar — a
10 % OI swing in a month is a large positioning move — so typical weeks yield a
*modest* vote. Conservative prior; S05 fits it from realised Brier outcomes."""

COT_MIN_OI_FRACTION = 0.01
"""Below a 4-week flow of **1 % of open interest** the positioning move is treated as
noise → no usable directional signal → abstain (``honest_absence``). Avoids voting on
quantisation-level wobble."""

COT_REVERSAL_DAMP = 0.5
"""When the latest 1-week flow sign-contradicts the 4-week trend (a positioning
inflection), conviction is HALVED — the doctrine read is "fading conviction", never a
reversal on one week (verified Q3). Dampen, do not flip."""

COT_INDEX_EXTREME_HIGH = 90.0
COT_INDEX_EXTREME_LOW = 10.0
"""3-year COT-Index percentile band. At/above HIGH or at/below LOW the momentum sign
is unreliable (contrarian regime) → abstain. Only applied when ``cot_index_pct`` is
supplied (it needs a 3-year history not yet carried in the primitives → optional)."""

# Per-asset polarity: does a managed-money NET-LONG in the COT contract imply the
# Ichor asset goes UP (+1) or DOWN (-1)?  For USD-base pairs the COT contract is the
# *foreign* currency future, so a long there is short USD → the pair falls (reverse
# polarity, exactly as flagged in data_pool._COT_MARKET_BY_ASSET:196,198). Decoupled
# from ``conviction_fusion._ASSET_USD_SIGN`` on purpose: gold/index COT relate to the
# asset directly, not via the dollar.
_COT_ASSET_SIGN: dict[str, int] = {
    "EUR_USD": +1,  # EURO FX future long → EUR up → EUR_USD up
    "GBP_USD": +1,  # BRITISH POUND future long → GBP_USD up
    "AUD_USD": +1,  # AUSTRALIAN DOLLAR future long → AUD_USD up
    "XAU_USD": +1,  # GOLD future long → XAU_USD up
    "NAS100_USD": +1,  # E-MINI NASDAQ-100 future long → NAS100 up
    "USD_JPY": -1,  # JAPANESE YEN future long → JPY up → USD_JPY DOWN (reverse)
    "USD_CAD": -1,  # CANADIAN DOLLAR future long → CAD up → USD_CAD DOWN (reverse)
    # SPX500_USD: E-mini code not collected yet (data_pool.py:201) → no COT → absent.
}


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


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


def build_cot_vote(
    *,
    asset: str,
    status: str,
    managed_money_net: int | None,
    managed_money_net_1w_ago: int | None,
    managed_money_net_4w_ago: int | None,
    open_interest: int | None,
    age_days: int | None,
    max_age_days: int = COT_MAX_AGE_DAYS,
    cot_index_pct: float | None = None,
) -> DimensionVote:
    """Map COT managed-money positioning primitives to one ``DimensionVote``.

    All inputs are PRIMITIVES the caller (the future C-3b wiring) extracts from the
    latest ``CotPosition`` rows for ``asset`` — this function does NO I/O so it stays
    a pure, unit-testable unit (ADR-009).

    Parameters
    ----------
    asset:
        Ichor asset id (e.g. ``"EUR_USD"``). Drives the per-asset COT polarity; an
        asset outside the COT whitelist abstains.
    status:
        S04 liveness status of the COT source (``"fresh"`` / ``"stale"`` /
        ``"absent"`` …, from ``classify_liveness``). ``"absent"`` → abstain.
    managed_money_net:
        Latest weekly managed-money net contracts (``rows[0].managed_money_net``).
    managed_money_net_1w_ago / managed_money_net_4w_ago:
        The same field one / four reports earlier (``rows[1]`` / ``rows[4]``), or
        ``None`` when the history is too short. ``Δ4w`` is the directional signal;
        ``Δ1w`` is used only to detect a one-week inflection.
    open_interest:
        Latest total open interest (``rows[0].open_interest``) — the cross-contract
        normaliser. ``None`` / ``0`` → cannot normalise → abstain.
    age_days:
        Age of the latest report in days (from ``classify_liveness``). Drives
        ``freshness = clamp(1 - age_days / max_age_days, 0, 1)``.
    max_age_days:
        Freshness window (defaults to the section's 14-day COT gate).
    cot_index_pct:
        OPTIONAL 3-year COT-Index percentile (0-100). When supplied and at an extreme
        (>= HIGH or <= LOW) the momentum sign is unreliable → abstain. ``None``
        (today's default — no 3-year history carried yet) → extreme check skipped.

    Returns
    -------
    DimensionVote
        ``provenance="cot"``, ``directional=True``. ``honest_absence=True`` (→ exactly
        0) whenever there is no usable directional signal. Otherwise a ``"up"``/``"down"``
        vote whose ``strength`` is the OI-normalised 4-week flow (dampened on a 1-week
        inflection) and whose ``freshness`` decays over ``max_age_days``.
    """
    # --- Honest-absence gates (ADR-103): each is a reason there is no usable read. --
    sign_for_asset = _COT_ASSET_SIGN.get(asset, 0)
    if sign_for_asset == 0:
        return _absent_vote()  # asset outside the COT whitelist (incl. SPX500 today)
    if status == "absent" or managed_money_net is None:
        return _absent_vote()  # COT table empty for this market
    if managed_money_net_4w_ago is None:
        return _absent_vote()  # < 5 weekly reports → no 4-week trend to read
    if open_interest is None or open_interest <= 0:
        return _absent_vote()  # cannot normalise the flow → refuse to fabricate strength
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain rather than assume
    if cot_index_pct is not None and (
        cot_index_pct >= COT_INDEX_EXTREME_HIGH or cot_index_pct <= COT_INDEX_EXTREME_LOW
    ):
        return _absent_vote()  # positioning extreme → momentum sign unreliable → abstain

    # --- Directional read: sign of the 4-week managed-money flow, asset-polarised. --
    delta_4w = float(managed_money_net - managed_money_net_4w_ago)
    oi_fraction = abs(delta_4w) / float(open_interest)
    if oi_fraction < COT_MIN_OI_FRACTION:
        return _absent_vote()  # flow below the noise floor → no directional signal

    flow_sign = _sign(delta_4w)  # +1 = funds adding longs, -1 = adding shorts
    asset_dir = flow_sign * sign_for_asset
    if asset_dir == 0:
        # Fail-closed hardening: the noise-floor gate above already guarantees
        # flow_sign != 0 (and sign_for_asset != 0 from the whitelist), so this is
        # unreachable today. The explicit guard makes the "asset_dir != 0" invariant
        # enforced rather than implicit, so a future lowering of COT_MIN_OI_FRACTION
        # can never silently emit a phantom "down" vote on a zero 4-week flow.
        return _absent_vote()
    direction_hint: VoteDirection = "up" if asset_dir > 0 else "down"

    # --- Strength: OI-normalised flow magnitude, dampened on a 1-week inflection. ---
    strength = _clamp(oi_fraction / COT_FULL_STRENGTH_OI_FRACTION, 0.0, 1.0)
    if managed_money_net_1w_ago is not None:
        delta_1w = float(managed_money_net - managed_money_net_1w_ago)
        if delta_1w * delta_4w < 0.0:  # latest week contradicts the 4-week trend
            strength *= COT_REVERSAL_DAMP

    freshness = _clamp(1.0 - (float(age_days) / float(max_age_days)), 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint=direction_hint,
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=True,
    )
