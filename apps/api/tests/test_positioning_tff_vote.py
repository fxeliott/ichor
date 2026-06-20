"""S06 Chantier C — ``positioning_tff_vote.build_positioning_tff_vote`` producer tests.

Pure unit tests (no DB, no LLM): the mapper is a deterministic primitive
(``positioning_tff_vote.py``). Coverage:

  1. the mapper in isolation — SPX500-only directional read (the asset COT does not
     cover), OI-normalised strength, 1-week-inflection dampening, gap-aligned deltas
     (holiday-skip safe), lag-aware freshness, fail-closed liveness, the
     anti-double-count abstain on every COT-covered asset, and the honest-absence gates;
  2. the mapper *integrated* into ``conviction_fusion.fuse_conviction(votes=...)`` —
     promotes/demotes via agreement, never flips direction (ADR-017), absent == no vote.

Doctrine = COT's (TFF Leveraged Funds is the same hedge-fund momentum cohort, same
weekly CFTC report). The single genuinely-new signal vs ``cot_vote`` is SPX500_USD
(13874A), which the COT collector does not carry. See ``positioning_tff_vote.py``
module docstring for sources.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

import pytest
from ichor_api.services import positioning_tff_vote as tff_mod
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.positioning_tff_vote import (
    PROVENANCE,
    TFF_FULL_STRENGTH_OI_FRACTION,
    TFF_MAX_AGE_DAYS,
    TFF_PUBLICATION_LAG_DAYS,
    TFF_REVERSAL_DAMP,
    build_positioning_tff_vote,
)

_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

_OI = 100_000  # full strength at 10 % of OI → |Δ4w| = 10_000 ; noise floor 1 % → 1_000.
_REF = date(2026, 6, 9)  # a Tuesday CFTC data date (mapper is date-relative)


def _hist(
    net: int,
    *,
    net_1w: int | None = None,
    net_4w: int | None = None,
    days_1w: int = 7,
    days_4w: int = 28,
) -> list[tuple[date, int]]:
    h: list[tuple[date, int]] = [(_REF, net)]
    if net_1w is not None:
        h.append((_REF - timedelta(days=days_1w), net_1w))
    if net_4w is not None:
        h.append((_REF - timedelta(days=days_4w), net_4w))
    return h


def _vote(
    *,
    asset: str = "SPX500_USD",
    status: str = "fresh",
    net: int = 15_000,
    net_1w: int | None = None,
    net_4w: int | None = 5_000,
    days_1w: int = 7,
    days_4w: int = 28,
    oi: int | None = _OI,
    age_days: int | None = TFF_PUBLICATION_LAG_DAYS,  # just-released → freshness 1.0
    history: list[tuple[date, int]] | None = None,
):
    """Default = a clean +10_000 4-week lev-funds flow on SPX500_USD, fresh just-released."""
    h = (
        history
        if history is not None
        else _hist(net, net_1w=net_1w, net_4w=net_4w, days_1w=days_1w, days_4w=days_4w)
    )
    return build_positioning_tff_vote(
        asset=asset, status=status, history=h, open_interest=oi, age_days=age_days
    )


# --------------------------------------------------------------------------- #
# Directional read (SPX500 only, +1 polarity)                                  #
# --------------------------------------------------------------------------- #


def test_rising_lev_net_is_up_on_spx500() -> None:
    v = _vote(net=15_000, net_4w=5_000)  # Δ4w +10_000 = full strength
    assert v.provenance == PROVENANCE == "positioning_tff"
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)
    assert v.freshness == pytest.approx(1.0)  # just-released (age == lag)
    assert v.directional is True
    assert v.honest_absence is False
    assert v.is_effective is True


def test_falling_lev_net_is_down_on_spx500() -> None:
    v = _vote(net=5_000, net_4w=15_000)  # Δ4w -10_000
    assert v.direction_hint == "down"
    assert v.strength == pytest.approx(1.0)


def test_covering_shorts_is_up_flow_even_while_net_short() -> None:
    v = _vote(net=-5_000, net_4w=-15_000)  # Δ4w +10_000 (funds covering)
    assert v.direction_hint == "up"


# --------------------------------------------------------------------------- #
# Anti-double-count: ONLY SPX500 votes (COT covers the rest)                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("asset", ["EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD"])
def test_cot_covered_assets_abstain_no_double_count(asset: str) -> None:
    """EUR/GBP/XAU/NAS are covered by cot_vote on the SAME market codes → a directional
    TFF vote would double-count → the producer abstains (honest-absence, contributes 0)."""
    v = _vote(asset=asset, net=15_000, net_4w=5_000)  # strong flow, but must abstain
    assert v.honest_absence is True
    assert v.direction_hint == "neutral"
    assert v.strength == 0.0
    assert v.signed_contribution() == 0.0


def test_unknown_asset_abstains() -> None:
    v = _vote(asset="ZZZ_ZZZ")
    assert v.honest_absence is True


def test_only_spx500_is_in_the_sign_map() -> None:
    assert set(tff_mod._TFF_ASSET_SIGN) == {"SPX500_USD"}
    assert tff_mod._TFF_ASSET_SIGN["SPX500_USD"] == 1


# --------------------------------------------------------------------------- #
# Strength normalisation + clamp                                              #
# --------------------------------------------------------------------------- #


def test_strength_is_oi_normalised_half() -> None:
    v = _vote(net=10_000, net_4w=5_000)  # Δ4w +5_000 = 5 % of OI → 0.5
    assert v.strength == pytest.approx(0.5)


def test_strength_clamps_at_one() -> None:
    v = _vote(net=35_000, net_4w=5_000)  # Δ4w +30_000 = 30 % of OI → clamp 1.0
    assert v.strength == pytest.approx(1.0)


def test_full_strength_at_documented_oi_fraction() -> None:
    delta = int(TFF_FULL_STRENGTH_OI_FRACTION * _OI)  # 10_000
    v = _vote(net=delta, net_4w=0)
    assert v.strength == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 1-week inflection dampening                                                  #
# --------------------------------------------------------------------------- #


def test_one_week_contradiction_dampens_strength() -> None:
    v = _vote(net=15_000, net_1w=18_000, net_4w=5_000)  # Δ4w +10k up, Δ1w -3k
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0 * TFF_REVERSAL_DAMP)


def test_one_week_aligned_does_not_dampen() -> None:
    v = _vote(net=15_000, net_1w=12_000, net_4w=5_000)
    assert v.strength == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Gap alignment (holiday-skip safe)                                           #
# --------------------------------------------------------------------------- #


def test_holiday_skipped_4w_report_still_read_within_band() -> None:
    v = _vote(net=15_000, net_4w=5_000, days_4w=35)  # 35 ∈ [21,42]
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)


def test_too_large_gap_abstains() -> None:
    hist = [(_REF, 15_000), (_REF - timedelta(days=50), 5_000)]  # 50 > 42
    v = _vote(history=hist)
    assert v.honest_absence is True


def test_gapped_one_week_report_skips_reversal() -> None:
    hist = [
        (_REF, 15_000),
        (_REF - timedelta(days=14), 18_000),  # 14 > 11 → not "1 week"
        (_REF - timedelta(days=28), 5_000),  # Δ4w +10_000
    ]
    v = _vote(history=hist)
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)  # not dampened


def test_single_report_history_abstains() -> None:
    v = _vote(history=[(_REF, 15_000)])
    assert v.honest_absence is True


def test_mixed_datetime_and_date_history_does_not_raise() -> None:
    hist: list[tuple[date, int]] = [
        (datetime(2026, 6, 9, 13, 30, tzinfo=UTC), 15_000),
        (date(2026, 5, 12), 5_000),  # 28 days before → Δ4w +10_000
    ]
    v = _vote(history=hist)
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Fail-closed liveness + lag-aware freshness                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", "", "FRESH"])
def test_only_fresh_status_votes(status: str) -> None:
    v = _vote(status=status, age_days=3)
    assert v.honest_absence is True
    assert v.signed_contribution() == 0.0


def test_just_released_report_is_full_freshness() -> None:
    v = _vote(age_days=TFF_PUBLICATION_LAG_DAYS)
    assert v.freshness == pytest.approx(1.0)


def test_freshness_decays_after_lag() -> None:
    v = _vote(age_days=8)
    expected = 1.0 - (8 - TFF_PUBLICATION_LAG_DAYS) / (TFF_MAX_AGE_DAYS - TFF_PUBLICATION_LAG_DAYS)
    assert v.freshness == pytest.approx(expected)  # 1 - 5/11


def test_max_age_report_is_zero_freshness_and_inert() -> None:
    v = _vote(age_days=TFF_MAX_AGE_DAYS)  # staleness 11 / window 11 → 0
    assert v.freshness == pytest.approx(0.0)
    assert v.is_effective is False
    assert v.honest_absence is False  # data exists, just too old to weigh


# --------------------------------------------------------------------------- #
# Honest-absence gates (ADR-103)                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs",
    [
        {"asset": "EUR_USD"},  # COT-covered → abstain (no double-count)
        {"asset": "ZZZ_ZZZ"},  # unknown asset
        {"oi": None},  # cannot normalise
        {"oi": 0},  # zero OI
        {"age_days": None},  # cannot verify freshness
        {"history": []},  # no reports
        {"net": 15_300, "net_4w": 15_000},  # Δ4w +300 = 0.3 % < 1 % noise floor
    ],
)
def test_honest_absence_gates_contribute_zero(kwargs: dict[str, object]) -> None:
    v = _vote(**kwargs)  # type: ignore[arg-type]
    assert v.honest_absence is True
    assert v.is_effective is False
    assert v.signed_contribution() == 0.0
    assert v.uncertainty_credit() == 0.0
    assert v.provenance == "positioning_tff"


def test_extreme_inputs_never_raise_and_stay_in_bounds() -> None:
    v = _vote(net=10_000_000, net_4w=0, oi=1, age_days=3)
    assert 0.0 <= v.strength <= 1.0
    assert 0.0 <= v.freshness <= 1.0


def test_zero_flow_guard_abstains_even_if_noise_floor_lowered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tff_mod, "TFF_MIN_OI_FRACTION", 0.0)
    v = _vote(net=15_000, net_4w=15_000)  # Δ4w == 0
    assert v.honest_absence is True
    assert v.signed_contribution() == 0.0


# --------------------------------------------------------------------------- #
# Fuser integration                                                          #
# --------------------------------------------------------------------------- #


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    base = max(0.0, 1.0 - bull - bear)
    return [
        {"label": "crash_flush", "p": 0.0},
        {"label": "strong_bear", "p": bear},
        {"label": "mild_bear", "p": 0.0},
        {"label": "base", "p": base},
        {"label": "mild_bull", "p": 0.0},
        {"label": "strong_bull", "p": bull},
        {"label": "melt_up", "p": 0.0},
    ]


def test_aligned_tff_vote_promotes_conviction() -> None:
    vote = _vote(net=15_000, net_4w=5_000)  # up, strength 1.0
    g = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"
    assert "positioning_tff" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))


def test_opposed_tff_vote_demotes_but_keeps_direction() -> None:
    vote = _vote(net=5_000, net_4w=15_000)  # down, strength 1.0
    g = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"  # bucket-derived; the vote did NOT flip it (ADR-017)
    assert "positioning_tff" in g.disagreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))


def test_absent_tff_vote_is_byte_identical_to_no_vote() -> None:
    absent = _vote(asset="EUR_USD")  # honest_absence (COT-covered)
    with_absent = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=[absent])
    no_votes = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40))
    assert with_absent == no_votes


def test_tff_vote_emits_no_trade_tokens_in_rationale() -> None:
    for vote in (_vote(net=15_000, net_4w=5_000), _vote(net=5_000, net_4w=15_000)):
        g = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
        assert _FORBIDDEN_RE.search(g.rationale_fr) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
