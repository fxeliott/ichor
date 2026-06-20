"""positioning_tff_vote.py — Chantier C · the CFTC-TFF positioning ``DimensionVote`` producer.

WHY THIS MODULE EXISTS
----------------------
``cot_vote.py`` mapped CFTC **COT** "managed money" positioning into a directional vote,
but the COT collector does NOT cover the S&P 500 E-mini (``data_pool._COT_MARKET_BY_ASSET``
has no SPX500 entry — ``cot_vote._COT_ASSET_SIGN`` abstains on it). The CFTC **TFF**
(Traders in Financial Futures) report DOES cover it (``_TFF_MARKET_BY_ASSET["SPX500_USD"]
= "13874A"``, ``data_pool.py:228``). This module rides TFF's **Leveraged Funds** net
positioning to give SPX500 the directional positioning vote it currently lacks — a
GENUINELY new, non-redundant signal (it is the one Ichor asset with TFF coverage but no
COT vote).

DELIBERATELY SPX500-ONLY (anti-double-count — ADR-017 / over-confidence guard)
-----------------------------------------------------------------------------
TFF and COT share the SAME CFTC market codes for EUR/GBP/XAU/NAS
(``data_pool.py:204-210`` vs ``221-227``), and Leveraged-Funds ≈ the managed-money cohort
COT already votes on. So a directional TFF vote on those four would DOUBLE-COUNT
``cot_vote`` — one underlying signal counted twice, inflating conviction into exactly the
over-confidence the calibration (ADR-116/118) must then shrink. To stay honest this vote
is restricted to **SPX500_USD only** (where COT has no vote); every other asset abstains
(honest-absence → contributes EXACTLY 0). The LevFunds-vs-AssetMgr "divergence" signal the
TFF section also surfaces is NOT voted here: institutional disagreement is an *uncertainty*
read, and the ``DimensionVote`` non-directional credit can only ever RAISE conviction —
it cannot express "be less sure", so a positive divergence credit would be backwards. That
is deferred (it needs a dampening term the contract does not have yet).

DOCTRINE = COT's (same instrument class, same report) — momentum, not contrarian
-------------------------------------------------------------------------------
Leveraged Funds = hedge funds / CTAs / CPOs, the active trend-following speculator voice
(the TFF analogue of COT managed money). So the read is identical to ``cot_vote``:
``sign(Δ4w lev_money_net)`` is trend-confirmation, OI-normalised, dampened on a 1-week
inflection, abstaining at the noise floor; full contrarian inversion at a 3-year extreme is
deferred (no 3-year history carried yet). Because it is the same cohort/cadence as COT, the
magnitude / band / freshness constants are initialised to ``cot_vote``'s values; S05 may
Brier-fit them separately.
  — financialresearch.gov/hedge-fund-monitor/datasets/tff (TFF 4-class buy/sell-side) ·
    cmegroup.com/articles/2026/the-cftc-cot-report-trade-fx-futures-more-effectively.html
    (LevFunds net = the directional momentum signal; flips mark conviction changes) ·
    cftc.gov/MarketReports/CommitmentsofTraders (Tuesday-close, Friday release ~3-day lag).

NOT WIRED (gated).  Pure, I/O-free primitive mapper only (ADR-120: imports nothing but
``dimension_vote`` + stdlib). The live wiring — fetching the recent ``CftcTffObservation``
rows in the write-side builder + fusing behind a feature flag — is the gated slice,
golden-card-guarded so the migration is byte-identical when the flag is OFF.

INVARIANTS (mirror ``dimension_vote`` / ``cot_vote``)
-----------------------------------------------------
* ADR-017 — moves conviction *magnitude*, never the verdict *direction*. SPX500 polarity
  is +1 (the E-mini is the index directly, no FX reversal).
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0 (asset != SPX500,
  non-fresh source, missing OI, missing age, empty history, no readable ~4-week trend,
  sub-noise-floor flow).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped before construction).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from .dimension_vote import DimensionVote, VoteDirection

# --------------------------------------------------------------------------- #
# Constants (initialised to cot_vote's — same CFTC report; S05 may fit apart). #
# --------------------------------------------------------------------------- #

PROVENANCE = "positioning_tff"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

POSITIONING_TFF_DIMENSION_VOTE_FLAG = "positioning_tff_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (write-side capture in ``run_session_card`` +
read-side fuse in ``build_session_verdict``). Defined here — the dimension's home — as the
SINGLE source of truth so the write site and the read site can never typo-diverge. Absent
flag ⇒ ``is_enabled`` returns False ⇒ both sides no-op ⇒ byte-identical to the legacy path
(``votes=()`` — C-2a). Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

TFF_MAX_AGE_DAYS = 14
"""Freshness window. Mirrors ``data_pool._TFF_MAX_AGE_DAYS`` (data_pool.py:3544) so the
vote's freshness window matches the section's S04 liveness gate exactly."""

TFF_PUBLICATION_LAG_DAYS = 3
"""CFTC TFF is Tuesday-close, released Friday (~3-day lag) — identical cadence to COT
(cot_vote.py:110-113). Freshness subtracts this lag so a just-released report scores 1.0,
then decays over the remaining window. Must be < max age."""

TFF_FULL_STRENGTH_OI_FRACTION = 0.10
"""A 4-week leveraged-funds repositioning equal to 10 % of open interest maps to full
``strength`` (1.0); smaller flows scale linearly. A deliberately HIGH bar (mirror
``cot_vote.COT_FULL_STRENGTH_OI_FRACTION``) so typical weeks yield a modest vote."""

TFF_MIN_OI_FRACTION = 0.01
"""Below a 4-week flow of 1 % of open interest the move is noise → abstain (mirror
``cot_vote.COT_MIN_OI_FRACTION``)."""

TFF_REVERSAL_DAMP = 0.5
"""When the latest 1-week flow sign-contradicts the 4-week trend (a positioning
inflection), conviction is HALVED — fading conviction, never a reversal on one week
(mirror ``cot_vote.COT_REVERSAL_DAMP``)."""

# Report-spacing windows (calendar days) — align the deltas on the real ``report_date``
# gaps rather than positional indices (holiday-skip safe). Mirror cot_vote.py:138-143.
TFF_TREND_TARGET_DAYS = 28
TFF_TREND_MIN_SPAN_DAYS = 21
TFF_TREND_MAX_SPAN_DAYS = 42
TFF_WEEK_TARGET_DAYS = 7
TFF_WEEK_MIN_SPAN_DAYS = 4
TFF_WEEK_MAX_SPAN_DAYS = 11

# Per-asset polarity: a leveraged-funds NET-LONG in the TFF contract implies the Ichor
# asset goes UP (+1) or DOWN (-1)?  ONLY SPX500_USD is mapped — the E-mini S&P is the index
# directly (+1, no FX reversal). Every other asset is intentionally absent so this vote can
# never double-count cot_vote on the shared market codes (see module docstring).
_TFF_ASSET_SIGN: dict[str, int] = {
    "SPX500_USD": +1,  # E-MINI S&P 500 future long → SPX500 up (COT does not cover this)
}


# --------------------------------------------------------------------------- #
# Helpers (self-contained — mirror cot_vote; behaviour locked by tests)        #
# --------------------------------------------------------------------------- #


def _as_date(value: date) -> date:
    """Normalize a ``datetime`` to a plain ``date`` (mirror cot_vote._as_date)."""
    return value.date() if isinstance(value, datetime) else value


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


def _select_net_in_band(
    ordered: Sequence[tuple[date, int]],
    current_date: date,
    *,
    target: int,
    lo: int,
    hi: int,
    prefer_larger_on_tie: bool,
) -> int | None:
    """Pick the lev_money_net of the report whose calendar gap to ``current_date`` is closest
    to ``target`` days while inside ``[lo, hi]``. ``None`` if no report falls in the band (a
    holiday-skipped week is never silently read as the intended lookback). Skips index 0 (the
    current report). Behaviour mirrors ``cot_vote._select_net_in_band`` — locked by tests."""
    best_net: int | None = None
    best_key: tuple[int, int] | None = None
    for rdate, net in ordered[1:]:
        span = (current_date - rdate).days
        if span < lo or span > hi:
            continue
        tie = -span if prefer_larger_on_tie else span
        key = (abs(span - target), tie)
        if best_key is None or key < best_key:
            best_key = key
            best_net = net
    return best_net


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def build_positioning_tff_vote(
    *,
    asset: str,
    status: str,
    history: Sequence[tuple[date, int]],
    open_interest: int | None,
    age_days: int | None,
    max_age_days: int = TFF_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map CFTC-TFF leveraged-funds positioning to one ``DimensionVote`` (pure, no I/O).

    Only ``SPX500_USD`` votes (the asset COT does not cover); every other asset abstains so
    this never double-counts ``cot_vote`` on the shared CFTC market codes.

    Parameters
    ----------
    asset:
        Ichor asset id. Anything other than ``"SPX500_USD"`` abstains (honest-absence).
    status:
        S04 liveness status of the TFF source (``classify_liveness``). **Fail-closed: only
        ``"fresh"`` votes.**
    history:
        Recent weekly reports as ``(report_date, lev_money_net)`` tuples (the builder fetches
        ~13 rows), in ANY order — the mapper sorts by date and dedupes. The 4-week trend and
        1-week inflection are read from the reports whose calendar gaps fall in the documented
        bands (holiday-safe).
    open_interest:
        Latest total open interest — the cross-contract normaliser. ``None`` / ``0`` → abstain.
    age_days:
        Age of the latest report in days (``classify_liveness``). Drives the lag-aware decay.
    max_age_days:
        Freshness window (defaults to the section's 14-day TFF gate).

    Returns
    -------
    DimensionVote
        ``provenance="positioning_tff"``, ``directional=True``. ``honest_absence=True`` (→ 0)
        whenever there is no usable directional signal. Otherwise an ``"up"``/``"down"`` vote
        whose ``strength`` is the OI-normalised 4-week lev-funds flow (dampened on a 1-week
        inflection) and whose ``freshness`` decays over the post-lag window.
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    sign_for_asset = _TFF_ASSET_SIGN.get(asset, 0)
    if sign_for_asset == 0:
        return _absent_vote()  # not SPX500 → COT already covers it / no TFF-only edge
    if status != "fresh":
        return _absent_vote()  # fail-closed: absent / stale / unknown source → abstain
    if open_interest is None or open_interest <= 0:
        return _absent_vote()  # cannot normalise the flow → refuse to fabricate strength
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain rather than assume
    if not history:
        return _absent_vote()  # no reports at all

    # Normalise the history: dedupe by report_date (latest tuple wins) and sort newest first.
    by_date: dict[date, int] = {}
    for rdate, net in history:
        by_date[_as_date(rdate)] = net
    ordered = sorted(by_date.items(), key=lambda kv: kv[0], reverse=True)
    current_date, current_net = ordered[0]

    # --- Directional read: 4-week lev-funds flow, gap-aligned, asset-polarised. --------
    net_4w = _select_net_in_band(
        ordered,
        current_date,
        target=TFF_TREND_TARGET_DAYS,
        lo=TFF_TREND_MIN_SPAN_DAYS,
        hi=TFF_TREND_MAX_SPAN_DAYS,
        prefer_larger_on_tie=True,
    )
    if net_4w is None:
        return _absent_vote()  # no report ~4 weeks back → no readable trend (gap/short)

    delta_4w = float(current_net - net_4w)
    oi_fraction = abs(delta_4w) / float(open_interest)
    if oi_fraction < TFF_MIN_OI_FRACTION:
        return _absent_vote()  # flow below the noise floor → no directional signal

    flow_sign = _sign(delta_4w)
    asset_dir = flow_sign * sign_for_asset
    if asset_dir == 0:
        return _absent_vote()  # defensive: unreachable past the noise floor (sign != 0)
    direction_hint: VoteDirection = "up" if asset_dir > 0 else "down"

    # --- Strength: OI-normalised flow magnitude, dampened on a 1-week inflection. -------
    strength = _clamp(oi_fraction / TFF_FULL_STRENGTH_OI_FRACTION, 0.0, 1.0)
    net_1w = _select_net_in_band(
        ordered,
        current_date,
        target=TFF_WEEK_TARGET_DAYS,
        lo=TFF_WEEK_MIN_SPAN_DAYS,
        hi=TFF_WEEK_MAX_SPAN_DAYS,
        prefer_larger_on_tie=False,
    )
    if net_1w is not None:
        delta_1w = float(current_net - net_1w)
        if delta_1w * delta_4w < 0.0:  # latest week contradicts the 4-week trend
            strength *= TFF_REVERSAL_DAMP

    # --- Freshness: lag-aware decay (a just-released ~3-day-old report scores 1.0). -----
    effective_window = float(max_age_days - TFF_PUBLICATION_LAG_DAYS)
    if effective_window <= 0.0:
        freshness = 1.0 if age_days <= max_age_days else 0.0
    else:
        staleness = max(0.0, float(age_days) - TFF_PUBLICATION_LAG_DAYS)
        freshness = _clamp(1.0 - staleness / effective_window, 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint=direction_hint,
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=True,
    )
