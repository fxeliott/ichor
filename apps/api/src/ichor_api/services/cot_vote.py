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
fuser refuses heavier deps — ADR-120). The live wiring — fetching the recent
``CotPosition`` rows inside ``build_session_verdict`` and passing the vote into
``fuse_conviction`` behind a feature flag — is the next GATED slice (C-3b: DB read on
the async path + flag + deploy + witness). Keeping the producer pure means C-3b is a
thin, golden-card-guarded wiring step with no logic of its own.

ROBUSTNESS BY CONSTRUCTION (2nd fresh-verifier pass, re-fire #11)
----------------------------------------------------------------
The mapper takes the recent reports as a **date-stamped history** (not 3 fixed
"N-weeks-ago" scalars), and aligns the 1-week / 4-week deltas on the actual
``report_date`` gaps. This closes a latent trap: CFTC skips reports on US federal
holidays, so a purely positional ``rows[4]`` can be 5 calendar weeks back — the
mapper would then mislabel a 5-week move as "Δ4w" and mis-time the 1-week
inflection. Here the 4-week trend is read only from a report **~28 days back
(21-42d band)**; outside that band the trend is unreadable → abstain. The 1-week
inflection is read only from a report **~7 days back (4-11d band)**; otherwise the
reversal check is skipped (never misfired). Liveness is **fail-closed**: only a
``status == "fresh"`` source votes, so the mapper never depends on the caller
passing a coherent ``(status, age_days)`` pair.

VERIFIED TRADING DOCTRINE (web-checked 2026-06-14, primary + reputable sources)
-------------------------------------------------------------------------------
* **Flow = momentum, NOT contrarian.** A *building* managed-money net position
  (4-week change in ``managed_money_net``) is read as trend-confirmation: managed
  money = CTAs / hedge funds, the quintessential momentum players. The contrarian
  read only applies at **statistical extremes** (see below). So the directional
  signal is ``sign(Δ4w managed_money_net)``, mapped to the asset.
  — cftc.gov (data definitions) · metalcharts.org/cot · luna3.ai/how-to-read-cot-report
* **Extremes = abstain (not auto-flip).** At a 3-year **COT-Index** extreme
  (>= 90th / <= 10th percentile) the momentum sign is unreliable and the contrarian
  regime begins — but every source stresses an extreme is a *risk condition*, not a
  *timing trigger*. The conservative first-slice behaviour is to **suppress** the
  vote at a detected extreme, not invert it (full contrarian logic needs technical
  confirmation → deferred). Extreme detection needs a 3-year history we don't carry
  yet, so ``cot_index_pct`` is an OPTIONAL input (``None`` = unknown → cannot abstain
  on extreme; the conservative magnitude cap below bounds the damage).
  — wallstreetcourier.com · hiddenmetrix.com/guide/cot-reports · tradealgo.com
* **1-week contradiction = inflection → dampen.** If the latest 1-week flow sign
  -contradicts the 4-week trend, conviction is *reduced* (early-warning inflection),
  never reversed on one week. — luna3.ai · forexfundamentals.com/learn/cot-data-reversals
* **Normalise to open interest.** ``Δnet / open_interest`` ("% of open interest" is
  an official CFTC report category) makes the flow comparable across contracts of
  very different size. NB (low-OI caveat): on a *thin* contract a trivially small
  absolute flow can still saturate the strength — bounded to a single layer's gain
  (≈ +6pp via ``VOTE_GAIN_K``, never manufacturing certainty, ADR-022). All
  whitelisted COT contracts are deep in practice; an absolute-OI floor would be a
  per-contract magic number → left to S05 Brier-fitting.
* **Publication lag.** Data = Tuesday close, released Friday 3:30 pm ET (~3-day lag),
  ageing to ~7-10 days before the next report. Freshness therefore subtracts the
  unavoidable lag so a *just-released* (~3-day-old) report scores freshness 1.0, then
  decays over the remaining window. — cftc.gov (Release Schedule)

INVARIANTS (mirror ``dimension_vote`` / ``conviction_fusion``)
--------------------------------------------------------------
* ADR-017 — this vote moves conviction *magnitude*, never the verdict *direction*.
  Polarity is per-asset (the COT contract is the *foreign* leg for USD-base pairs
  → reverse sign).
* ADR-103 — no usable data → ``honest_absence=True`` → contributes EXACTLY 0
  (asset off-whitelist, non-fresh source, missing open interest, missing age, empty
  history, no readable ~4-week trend, sub-noise-floor flow, or a detected extreme).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped before construction).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from .dimension_vote import DimensionVote, VoteDirection

# --------------------------------------------------------------------------- #
# Constants (principled priors — documented; S05 fits these from Brier).       #
# --------------------------------------------------------------------------- #

PROVENANCE = "cot"
"""Dimension id surfaced in the transparent ``agreeing`` / coach surface."""

COT_DIMENSION_VOTE_FLAG = "cot_dimension_vote_enabled"
"""Feature-flag key gating the C-3b live wiring (write-side capture in
``run_session_card`` + read-side fuse in ``build_session_verdict``). Defined
here — the dimension's home — as the SINGLE source of truth so the write site
and the read site can never typo-diverge (feature_flags has no central registry).
Absent flag ⇒ ``is_enabled`` returns False ⇒ both sides no-op ⇒ byte-identical
to the legacy path (``votes=()`` — C-2a)."""

COT_MAX_AGE_DAYS = 14
"""Freshness window. Mirrors ``data_pool._COT_MAX_AGE_DAYS`` (data_pool.py:3512) so
the vote's freshness window matches the section's S04 liveness gate exactly."""

COT_PUBLICATION_LAG_DAYS = 3
"""CFTC COT is Tuesday-close, released Friday (~3-day lag): a *just-released* report
is already ~3 days old. Freshness subtracts this unavoidable lag so a fresh release
scores 1.0 (not ~0.79), then decays over the remaining window. Must be < max age."""

COT_FULL_STRENGTH_OI_FRACTION = 0.10
"""A 4-week managed-money repositioning equal to **10 % of open interest** maps to
full ``strength`` (1.0); smaller flows scale linearly. A deliberately HIGH bar — a
10 % OI swing in a month is a large positioning move — so typical weeks yield a
*modest* vote. Conservative prior; S05 fits it from realised Brier outcomes."""

COT_MIN_OI_FRACTION = 0.01
"""Below a 4-week flow of **1 % of open interest** the move is treated as noise → no
usable directional signal → abstain. Avoids voting on quantisation-level wobble."""

COT_REVERSAL_DAMP = 0.5
"""When the latest 1-week flow sign-contradicts the 4-week trend (a positioning
inflection), conviction is HALVED — the doctrine read is "fading conviction", never a
reversal on one week. Dampen, do not flip."""

COT_INDEX_EXTREME_HIGH = 90.0
COT_INDEX_EXTREME_LOW = 10.0
"""3-year COT-Index percentile band. At/above HIGH or at/below LOW the momentum sign
is unreliable (contrarian regime) → abstain. Only applied when ``cot_index_pct`` is
supplied (it needs a 3-year history not yet carried in the primitives → optional)."""

# Report-spacing windows (calendar days) used to align the deltas on the real
# ``report_date`` gaps rather than on positional row indices (holiday-week safe).
COT_TREND_TARGET_DAYS = 28  # 4 weekly reports
COT_TREND_MIN_SPAN_DAYS = 21  # accept a 3-week..6-week lookback as "the 4-week trend"
COT_TREND_MAX_SPAN_DAYS = 42
COT_WEEK_TARGET_DAYS = 7
COT_WEEK_MIN_SPAN_DAYS = 4  # accept a ~1-week lookback for the inflection check
COT_WEEK_MAX_SPAN_DAYS = 11

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


def _as_date(value: date) -> date:
    """Normalize a ``datetime`` to a plain ``date`` (mirror of
    ``data_liveness._as_date``) so a caller passing mixed ``date`` / ``datetime``
    report stamps can never break the gap sort with a ``TypeError``."""
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
    """Pick the managed_money_net of the report whose calendar gap to ``current_date``
    is closest to ``target`` days while inside ``[lo, hi]``. Returns ``None`` if no
    report falls in the band — so a holiday-skipped week can never be silently read as
    if it were the intended lookback. Skips index 0 (the current report itself)."""
    best_net: int | None = None
    best_key: tuple[int, int] | None = None
    for rdate, net in ordered[1:]:
        span = (current_date - rdate).days
        if span < lo or span > hi:
            continue
        # primary: closest to target ; tie-break: larger span (more history) for the
        # trend, smaller span (most recent) for the weekly inflection.
        tie = -span if prefer_larger_on_tie else span
        key = (abs(span - target), tie)
        if best_key is None or key < best_key:
            best_key = key
            best_net = net
    return best_net


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def build_cot_vote(
    *,
    asset: str,
    status: str,
    history: Sequence[tuple[date, int]],
    open_interest: int | None,
    age_days: int | None,
    max_age_days: int = COT_MAX_AGE_DAYS,
    cot_index_pct: float | None = None,
) -> DimensionVote:
    """Map COT managed-money positioning to one ``DimensionVote`` (pure, no I/O).

    Parameters
    ----------
    asset:
        Ichor asset id (e.g. ``"EUR_USD"``). Drives the per-asset COT polarity; an
        asset outside the COT whitelist abstains.
    status:
        S04 liveness status of the COT source (``"fresh"`` / ``"stale"`` /
        ``"absent"``, from ``classify_liveness``). **Fail-closed: only ``"fresh"``
        votes** — any other status abstains, so the mapper never relies on the caller
        passing a ``(status, age_days)`` pair that is internally consistent.
    history:
        The recent weekly reports as ``(report_date, managed_money_net)`` tuples
        (typically the last ~13 ``CotPosition`` rows the caller already fetched), in
        ANY order — the mapper sorts by date and dedupes. The current report is the
        most recent date; the 4-week trend and 1-week inflection are read from the
        reports whose calendar gaps fall in the documented bands (holiday-safe).
    open_interest:
        Latest total open interest — the cross-contract normaliser. ``None`` / ``0``
        → cannot normalise → abstain.
    age_days:
        Age of the latest report in days (from ``classify_liveness``; measured from
        the data date). Drives the lag-aware freshness decay.
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
        inflection) and whose ``freshness`` decays over the post-lag window.
    """
    # --- Honest-absence gates (ADR-103): each is a reason there is no usable read. --
    sign_for_asset = _COT_ASSET_SIGN.get(asset, 0)
    if sign_for_asset == 0:
        return _absent_vote()  # asset outside the COT whitelist (incl. SPX500 today)
    if status != "fresh":
        return _absent_vote()  # fail-closed: absent / stale / unknown source → abstain
    if open_interest is None or open_interest <= 0:
        return _absent_vote()  # cannot normalise the flow → refuse to fabricate strength
    if age_days is None:
        return _absent_vote()  # cannot verify freshness → abstain rather than assume
    if not history:
        return _absent_vote()  # no reports at all
    if cot_index_pct is not None and (
        cot_index_pct >= COT_INDEX_EXTREME_HIGH or cot_index_pct <= COT_INDEX_EXTREME_LOW
    ):
        return _absent_vote()  # positioning extreme → momentum sign unreliable → abstain

    # Normalise the history: dedupe by report_date (latest tuple wins) and sort newest
    # first, so positional and calendar order agree before band selection.
    by_date: dict[date, int] = {}
    for rdate, net in history:
        by_date[_as_date(rdate)] = net
    ordered = sorted(by_date.items(), key=lambda kv: kv[0], reverse=True)
    current_date, current_net = ordered[0]

    # --- Directional read: 4-week managed-money flow, gap-aligned, asset-polarised. -
    net_4w = _select_net_in_band(
        ordered,
        current_date,
        target=COT_TREND_TARGET_DAYS,
        lo=COT_TREND_MIN_SPAN_DAYS,
        hi=COT_TREND_MAX_SPAN_DAYS,
        prefer_larger_on_tie=True,
    )
    if net_4w is None:
        return _absent_vote()  # no report ~4 weeks back → no readable trend (gap/short)

    delta_4w = float(current_net - net_4w)
    oi_fraction = abs(delta_4w) / float(open_interest)
    if oi_fraction < COT_MIN_OI_FRACTION:
        return _absent_vote()  # flow below the noise floor → no directional signal

    flow_sign = _sign(delta_4w)  # +1 = funds adding longs, -1 = adding shorts
    asset_dir = flow_sign * sign_for_asset
    if asset_dir == 0:
        # Fail-closed: flow_sign != 0 past the noise floor and sign_for_asset != 0 from
        # the whitelist, so this is unreachable today; the explicit guard keeps a future
        # lowering of COT_MIN_OI_FRACTION from ever emitting a phantom "down" on zero flow.
        return _absent_vote()
    direction_hint: VoteDirection = "up" if asset_dir > 0 else "down"

    # --- Strength: OI-normalised flow magnitude, dampened on a 1-week inflection. ---
    strength = _clamp(oi_fraction / COT_FULL_STRENGTH_OI_FRACTION, 0.0, 1.0)
    net_1w = _select_net_in_band(
        ordered,
        current_date,
        target=COT_WEEK_TARGET_DAYS,
        lo=COT_WEEK_MIN_SPAN_DAYS,
        hi=COT_WEEK_MAX_SPAN_DAYS,
        prefer_larger_on_tie=False,
    )
    if net_1w is not None:
        delta_1w = float(current_net - net_1w)
        if delta_1w * delta_4w < 0.0:  # latest week contradicts the 4-week trend
            strength *= COT_REVERSAL_DAMP

    # --- Freshness: lag-aware decay (a just-released ~3-day-old report scores 1.0). --
    effective_window = float(max_age_days - COT_PUBLICATION_LAG_DAYS)
    if effective_window <= 0.0:
        freshness = 1.0 if age_days <= max_age_days else 0.0
    else:
        staleness = max(0.0, float(age_days) - COT_PUBLICATION_LAG_DAYS)
        freshness = _clamp(1.0 - staleness / effective_window, 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint=direction_hint,
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=True,
    )
