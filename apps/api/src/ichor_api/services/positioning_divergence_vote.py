"""positioning_divergence_vote.py — Chantier C · the institutional-divergence DOUBT producer.

WHY THIS MODULE EXISTS
----------------------
The CFTC-TFF report splits speculators into **Leveraged Funds** (hedge funds / CTAs — fast
momentum money) and **Asset Managers** (pension / real money — slow structural money). When
they sit on OPPOSITE sides of a contract, the institutional read is *contested*: the directional
picture is genuinely less certain. ``_section_tff_positioning`` already surfaces this as a
"smart-money divergence" flag (``data_pool.py:4519``) but it never fed the verdict. Last session
it was DEFERRED because divergence is an *uncertainty* signal and the old contract could only
RAISE conviction. The doubt term (``increases_uncertainty``) now lets it lower conviction —
honestly.

DOUBT, NON-DIRECTIONAL, PER-ASSET (ADR-017)
-------------------------------------------
Divergence widens the outcome distribution; it does NOT point a direction (which cohort is
"right" is exactly what is uncertain). The vote is ``directional=False`` /
``increases_uncertainty=True`` → it contributes only ``doubt_penalty()``. Unlike ``vol_regime``
(global), this is PER-ASSET: each asset's own TFF report drives its own divergence doubt.

Distinct from ``positioning_tff`` (the directional LevFunds momentum vote, SPX500-only): that
reads the *direction* of leveraged-fund flow; this reads the *disagreement* between the two
cohorts. They are orthogonal and both can be active.

NOT WIRED (gated). Pure, I/O-free primitive mapper (ADR-120). The async builder reads the
latest TFF row per asset; wiring is golden-card-guarded (flag-OFF byte-identical).

VERIFIED DOCTRINE (web-checked 2026-06-20, primary + reputable)
--------------------------------------------------------------
* **LevFunds = fast momentum speculators; AssetMgr = slow structural real money** (CFTC TFF
  4-class buy/sell-side). When they oppose, neither cohort's positioning is a clean read →
  elevated uncertainty, not a direction. — financialresearch.gov/hedge-fund-monitor/datasets/tff
  · cmegroup.com/articles/2026/the-cftc-cot-report-trade-fx-futures-more-effectively.html.
* **Magnitude = the SMALLER opposing net normalised by open interest** (both sides committed,
  not a token gap), full doubt at 10 % of OI (mirror cot's 10 %-OI bar — a deliberately HIGH
  bar). ~3-day publication lag (Tue close / Fri release), 14-day window — same as COT/TFF.

INVARIANTS (mirror ``dimension_vote`` / ``vol_regime_vote``)
----------------------------------------------------------
* ADR-017 — non-directional DOUBT: never a tilt; lowers conviction via ``doubt_penalty``.
* ADR-103 — no usable data → ``honest_absence=True`` → 0 (asset off the TFF whitelist,
  non-fresh source, missing OI / age, same-sided cohorts = present strength-0 doubt).
* ADR-022 — ``strength`` ∈ [0, 1] (clamped).
* ADR-009 (Voie D) — pure arithmetic; zero I/O / LLM / spend.
"""

from __future__ import annotations

from .dimension_vote import DimensionVote

PROVENANCE = "positioning_divergence"
"""Dimension id surfaced in the transparent ``doubts`` / coach surface."""

POSITIONING_DIVERGENCE_DIMENSION_VOTE_FLAG = "positioning_divergence_dimension_vote_enabled"
"""Feature-flag key gating the live wiring (SINGLE source of truth, write + read). Absent flag
⇒ both sides no-op ⇒ byte-identical. Mirrors ``cot_vote.COT_DIMENSION_VOTE_FLAG``."""

DIVERGENCE_MAX_AGE_DAYS = 14
"""Freshness window. Mirrors ``data_pool._TFF_MAX_AGE_DAYS`` (data_pool.py:3544)."""

DIVERGENCE_PUBLICATION_LAG_DAYS = 3
"""CFTC TFF Tuesday-close / Friday release (~3-day lag), identical to COT/TFF. Freshness
subtracts the lag so a just-released report scores 1.0."""

DIVERGENCE_FULL_STRENGTH_OI_FRACTION = 0.10
"""Full doubt (strength 1.0) when the SMALLER opposing cohort net reaches 10 % of open interest
(both sides genuinely committed on opposite sides). Mirror ``cot``'s 10 %-OI bar — a high bar so
a token gap yields little doubt. S05 Brier-fits this."""

# Assets the TFF report covers (mirror data_pool._TFF_MARKET_BY_ASSET keys for the 5 priority
# assets + the tracked-no-card pairs). Divergence is per-asset, so any TFF-covered asset votes.
_DIVERGENCE_ASSETS: frozenset[str] = frozenset(
    {"EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", "SPX500_USD", "USD_JPY", "USD_CAD", "AUD_USD"}
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


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


def build_positioning_divergence_vote(
    *,
    asset: str,
    status: str,
    lev_net: int | None,
    am_net: int | None,
    open_interest: int | None,
    age_days: int | None,
    max_age_days: int = DIVERGENCE_MAX_AGE_DAYS,
) -> DimensionVote:
    """Map LevFunds-vs-AssetMgr opposition to one DOUBT ``DimensionVote`` (pure, no I/O).

    Always non-directional + ``increases_uncertainty=True``: institutional disagreement widens
    the distribution → it LOWERS conviction, never tilts long/short (ADR-017).

    Parameters
    ----------
    asset:
        Ichor asset id. Off the TFF whitelist → abstain.
    status:
        S04 liveness status (``classify_liveness``). Fail-closed: only ``"fresh"`` votes.
    lev_net / am_net:
        Leveraged-Funds net (``lev_money_long - lev_money_short``) and Asset-Manager net
        (``asset_mgr_long - asset_mgr_short``) from the latest TFF report. ``None`` → abstain.
    open_interest:
        Latest total OI — the cross-contract normaliser. ``None`` / ``0`` → abstain.
    age_days:
        Age of the latest report in days. ``None`` → abstain.
    max_age_days:
        Freshness window (defaults to the 14-day TFF gate).

    Returns
    -------
    DimensionVote
        ``provenance="positioning_divergence"``, ``directional=False``,
        ``increases_uncertainty=True``. ``honest_absence=True`` (→ 0) when no usable read.
        Same-sided cohorts (or either flat) → present strength-0 doubt (no divergence). Opposite
        sides → doubt whose ``strength`` is the smaller opposing net / OI (full at 10 % of OI),
        ``freshness`` lag-aware over the window.
    """
    # --- Honest-absence gates (ADR-103). ----------------------------------------------
    if asset not in _DIVERGENCE_ASSETS:
        return _absent_vote()
    if status != "fresh":
        return _absent_vote()  # fail-closed
    if open_interest is None or open_interest <= 0:
        return _absent_vote()  # cannot normalise
    if age_days is None:
        return _absent_vote()
    if lev_net is None or am_net is None:
        return _absent_vote()

    # --- Strength: divergence magnitude (opposite sides, smaller net / OI). -------------
    if _sign(lev_net) * _sign(am_net) >= 0:
        # Same-sided (or either flat) → no divergence → present strength-0 doubt (no penalty).
        strength = 0.0
    else:
        smaller_opposing = float(min(abs(lev_net), abs(am_net)))
        oi_fraction = smaller_opposing / float(open_interest)
        strength = _clamp(oi_fraction / DIVERGENCE_FULL_STRENGTH_OI_FRACTION, 0.0, 1.0)

    # --- Freshness: lag-aware decay (just-released ~3-day report scores 1.0). -----------
    effective_window = float(max_age_days - DIVERGENCE_PUBLICATION_LAG_DAYS)
    if effective_window <= 0.0:
        freshness = 1.0 if age_days <= max_age_days else 0.0
    else:
        staleness = max(0.0, float(age_days) - DIVERGENCE_PUBLICATION_LAG_DAYS)
        freshness = _clamp(1.0 - staleness / effective_window, 0.0, 1.0)

    return DimensionVote(
        provenance=PROVENANCE,
        direction_hint="neutral",
        strength=strength,
        freshness=freshness,
        honest_absence=False,
        directional=False,
        increases_uncertainty=True,
    )
