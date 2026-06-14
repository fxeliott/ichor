"""S06 Chantier C · C-3 slice-0 — ``cot_vote.build_cot_vote`` producer tests.

Pure unit tests (no DB, no LLM): the mapper is a deterministic primitive
(``cot_vote.py``). Coverage:

  1. the mapper in isolation — directional read, per-asset polarity, OI-normalised
     strength, 1-week-inflection dampening, **gap-aligned** deltas (holiday-skip safe),
     lag-aware freshness, fail-closed liveness, and every honest-absence gate (ADR-103);
  2. the mapper *integrated* into ``conviction_fusion.fuse_conviction(votes=...)`` —
     proving a COT vote moves conviction the right way, never flips direction
     (ADR-017), and that an absent vote is byte-identical to no vote (ADR-103).

Doctrine anchors verified 2026-06-14 (cftc.gov + reputable aggregators): flow =
momentum (``sign(Δ4w)``), 1-week contradiction = dampen, extremes = abstain,
normalise to open interest, ~3-day publication lag. See ``cot_vote.py`` module
docstring for sources. Robustness fixes (gap alignment, fail-closed status,
lag-aware freshness) follow the 2nd fresh-verifier pass (re-fire #11).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

import pytest
from ichor_api.services import cot_vote as cot_vote_mod
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.cot_vote import (
    COT_FULL_STRENGTH_OI_FRACTION,
    COT_MAX_AGE_DAYS,
    COT_PUBLICATION_LAG_DAYS,
    COT_REVERSAL_DAMP,
    build_cot_vote,
)

# Same proven CI-clean trade-token regex as test_conviction_fusion.py:25-28 (ADR-017).
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

# A typical open interest so |Δ4w| / OI lands on clean fractions:
#   full strength at 10 % of OI → |Δ4w| = 10_000 ; noise floor 1 % → |Δ4w| = 1_000.
_OI = 100_000

# Fixed reference "current report" date (a Tuesday CFTC data date). The mapper is
# date-RELATIVE (it only uses gaps to current), so any fixed date works.
_REF = date(2026, 6, 9)


def _hist(
    net: int,
    *,
    net_1w: int | None = None,
    net_4w: int | None = None,
    days_1w: int = 7,
    days_4w: int = 28,
) -> list[tuple[date, int]]:
    """Build a weekly history: current report at _REF, optional prior reports at
    _REF-days_1w and _REF-days_4w (defaults = exact 7 / 28 day cadence)."""
    h: list[tuple[date, int]] = [(_REF, net)]
    if net_1w is not None:
        h.append((_REF - timedelta(days=days_1w), net_1w))
    if net_4w is not None:
        h.append((_REF - timedelta(days=days_4w), net_4w))
    return h


def _vote(
    *,
    asset: str = "EUR_USD",
    status: str = "fresh",
    net: int = 15_000,
    net_1w: int | None = None,
    net_4w: int | None = 5_000,
    days_1w: int = 7,
    days_4w: int = 28,
    oi: int | None = _OI,
    age_days: int | None = COT_PUBLICATION_LAG_DAYS,  # just-released → freshness 1.0
    cot_index_pct: float | None = None,
    history: list[tuple[date, int]] | None = None,
):
    """Default = a clean +10_000 4-week flow on EUR_USD, fresh just-released."""
    h = (
        history
        if history is not None
        else _hist(net, net_1w=net_1w, net_4w=net_4w, days_1w=days_1w, days_4w=days_4w)
    )
    return build_cot_vote(
        asset=asset,
        status=status,
        history=h,
        open_interest=oi,
        age_days=age_days,
        cot_index_pct=cot_index_pct,
    )


# --------------------------------------------------------------------------- #
# Directional read + polarity                                                  #
# --------------------------------------------------------------------------- #


def test_rising_net_long_is_up_on_eur_usd() -> None:
    v = _vote(net=15_000, net_4w=5_000)  # Δ4w +10_000 = full strength
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)
    assert v.freshness == pytest.approx(1.0)  # just-released (age == lag)
    assert v.honest_absence is False
    assert v.is_effective is True
    assert v.provenance == "cot"


def test_falling_net_is_down_on_eur_usd() -> None:
    v = _vote(net=5_000, net_4w=15_000)  # Δ4w -10_000
    assert v.direction_hint == "down"
    assert v.strength == pytest.approx(1.0)


def test_reducing_shorts_is_up_flow_even_while_net_short() -> None:
    # net still negative but the 4-week FLOW is positive (funds covering shorts) →
    # bullish flow per doctrine (Q1: flow direction, not absolute level).
    v = _vote(net=-5_000, net_4w=-15_000)  # Δ4w +10_000
    assert v.direction_hint == "up"


def test_polarity_reversed_for_usd_jpy() -> None:
    # JPY-future long → JPY up → USD_JPY DOWN (reverse polarity, data_pool:196).
    v = _vote(asset="USD_JPY", net=15_000, net_4w=5_000)  # rising YEN longs
    assert v.direction_hint == "down"


def test_polarity_reversed_for_usd_cad() -> None:
    v = _vote(asset="USD_CAD", net=15_000, net_4w=5_000)
    assert v.direction_hint == "down"


# --------------------------------------------------------------------------- #
# Strength normalisation (OI-relative) + clamping                              #
# --------------------------------------------------------------------------- #


def test_strength_is_oi_normalised_half() -> None:
    v = _vote(net=10_000, net_4w=5_000)  # Δ4w +5_000 = 5 % of OI → 0.5 strength
    assert v.strength == pytest.approx(0.5)


def test_strength_clamps_at_one() -> None:
    v = _vote(net=35_000, net_4w=5_000)  # Δ4w +30_000 = 30 % of OI → clamp 1.0
    assert v.strength == pytest.approx(1.0)


def test_full_strength_at_documented_oi_fraction() -> None:
    delta = int(COT_FULL_STRENGTH_OI_FRACTION * _OI)  # 10_000
    v = _vote(net=delta, net_4w=0)
    assert v.strength == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 1-week inflection dampening                                                  #
# --------------------------------------------------------------------------- #


def test_one_week_contradiction_dampens_strength() -> None:
    # Δ4w +10_000 (up trend) but Δ1w -3_000 (latest week down) → inflection → halve.
    v = _vote(net=15_000, net_1w=18_000, net_4w=5_000)
    assert v.direction_hint == "up"  # 4-week trend still sets direction
    assert v.strength == pytest.approx(1.0 * COT_REVERSAL_DAMP)  # 0.5


def test_one_week_aligned_does_not_dampen() -> None:
    # Δ4w +10_000 and Δ1w +3_000 (same sign) → no dampening.
    v = _vote(net=15_000, net_1w=12_000, net_4w=5_000)
    assert v.strength == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Gap alignment (holiday-skipped weeks) — MAJOR-1 robustness fix               #
# --------------------------------------------------------------------------- #


def test_holiday_skipped_4w_report_still_read_within_band() -> None:
    # A skipped CFTC week → the "4-week" report is 35 days back (5 calendar weeks).
    # 35 ∈ [21, 42] → still accepted as the trend lookback (not silently dropped).
    v = _vote(net=15_000, net_4w=5_000, days_4w=35)  # Δ4w +10_000 over 5 weeks
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)


def test_too_large_gap_abstains_no_readable_trend() -> None:
    # Only an old report 50 days back (> 42) → no report ~4 weeks back → abstain,
    # rather than mislabel a 7-week move as "Δ4w".
    hist = [(_REF, 15_000), (_REF - timedelta(days=50), 5_000)]
    v = _vote(history=hist)
    assert v.honest_absence is True
    assert v.signed_contribution() == pytest.approx(0.0)


def test_gapped_one_week_report_skips_reversal_not_misfired() -> None:
    # The nearest "1-week" report is 14 days back (> 11) → reversal check is SKIPPED
    # (not computed against a 2-week gap). Δ4w still read from the -28 report.
    hist = [
        (_REF, 15_000),
        (_REF - timedelta(days=14), 18_000),  # would dampen if mis-read as 1 week
        (_REF - timedelta(days=28), 5_000),  # Δ4w +10_000 (up)
    ]
    v = _vote(history=hist)
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)  # NOT 0.5 — the 2-week gap is not "1 week"


def test_single_report_history_abstains() -> None:
    v = _vote(history=[(_REF, 15_000)])  # no prior report → no trend
    assert v.honest_absence is True


def test_mixed_datetime_and_date_history_does_not_raise() -> None:
    # Defensive (3rd fresh-verifier MINOR): a caller mixing datetime + date stamps
    # must not crash the gap sort — datetimes are normalised to date.
    hist: list[tuple[date, int]] = [
        (datetime(2026, 6, 9, 13, 30, tzinfo=UTC), 15_000),
        (date(2026, 5, 12), 5_000),  # 28 days before → Δ4w +10_000
    ]
    v = _vote(history=hist)
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Fail-closed liveness — MAJOR-2 robustness fix                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", "", "FRESH"])
def test_only_fresh_status_votes(status: str) -> None:
    # Even with a strong flow and a small age_days, a non-"fresh" status abstains —
    # the mapper never trusts an inconsistent (status, age_days) pair.
    v = _vote(status=status, age_days=3)
    assert v.honest_absence is True
    assert v.signed_contribution() == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Lag-aware freshness — MINOR-2 fix                                            #
# --------------------------------------------------------------------------- #


def test_just_released_report_is_full_freshness() -> None:
    # CFTC ~3-day publication lag: a just-released report (age == lag) must score 1.0,
    # not ~0.79 (the unavoidable lag is not staleness).
    v = _vote(age_days=COT_PUBLICATION_LAG_DAYS)
    assert v.freshness == pytest.approx(1.0)


def test_freshness_decays_after_lag() -> None:
    v = _vote(age_days=8)
    expected = 1.0 - (8 - COT_PUBLICATION_LAG_DAYS) / (COT_MAX_AGE_DAYS - COT_PUBLICATION_LAG_DAYS)
    assert v.freshness == pytest.approx(expected)  # 1 - 5/11


def test_max_age_report_is_zero_freshness_and_inert() -> None:
    v = _vote(age_days=COT_MAX_AGE_DAYS)  # 14 → staleness 11 / window 11 → 0
    assert v.freshness == pytest.approx(0.0)
    assert v.is_effective is False
    assert v.signed_contribution() == pytest.approx(0.0)
    assert v.honest_absence is False  # data exists, just too old to weigh


# --------------------------------------------------------------------------- #
# Honest-absence gates (ADR-103) — each contributes EXACTLY 0                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs",
    [
        {"asset": "SPX500_USD"},  # outside the COT whitelist (no E-mini code yet)
        {"asset": "ZZZ_ZZZ"},  # unknown asset
        {"oi": None},  # cannot normalise
        {"oi": 0},  # cannot normalise (zero OI)
        {"age_days": None},  # cannot verify freshness
        {"history": []},  # no reports at all
        {"net": 15_300, "net_4w": 15_000},  # Δ4w +300 = 0.3 % of OI < 1 % noise floor
        {"cot_index_pct": 95.0},  # 3-year extreme high → abstain
        {"cot_index_pct": 5.0},  # 3-year extreme low → abstain
        {"cot_index_pct": 90.0},  # boundary high (>=) → abstain
        {"cot_index_pct": 10.0},  # boundary low (<=) → abstain
    ],
)
def test_honest_absence_gates_contribute_zero(kwargs: dict[str, object]) -> None:
    v = _vote(**kwargs)  # type: ignore[arg-type]
    assert v.honest_absence is True
    assert v.is_effective is False
    assert v.signed_contribution() == pytest.approx(0.0)
    assert v.uncertainty_credit() == pytest.approx(0.0)
    assert v.provenance == "cot"


def test_mid_cot_index_is_not_extreme() -> None:
    v = _vote(cot_index_pct=50.0)
    assert v.honest_absence is False
    assert v.direction_hint == "up"


# --------------------------------------------------------------------------- #
# Construction safety: the mapper never emits an out-of-contract vote           #
# --------------------------------------------------------------------------- #


def test_extreme_inputs_never_raise_and_stay_in_bounds() -> None:
    # Absurd flow far beyond OI → strength must be clamped, not raise ValueError.
    v = _vote(net=10_000_000, net_4w=0, oi=1, age_days=3)
    assert 0.0 <= v.strength <= 1.0
    assert 0.0 <= v.freshness <= 1.0


def test_zero_flow_guard_abstains_even_if_noise_floor_lowered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fail-closed hardening (1st fresh-verifier MINOR): if the noise floor were ever
    # lowered to 0, a flat 4-week flow (Δ4w == 0) must STILL abstain — never emit a
    # phantom directional vote. Guards the "asset_dir != 0" invariant explicitly.
    monkeypatch.setattr(cot_vote_mod, "COT_MIN_OI_FRACTION", 0.0)
    v = _vote(net=15_000, net_4w=15_000)  # Δ4w == 0 (would pass a 0.0 noise floor)
    assert v.honest_absence is True
    assert v.signed_contribution() == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Integration into the fuser (flag-ON behaviour, ADR-017 / ADR-103 / ADR-022)  #
# --------------------------------------------------------------------------- #


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """7-bucket Pass-6 decomposition (mirror of test_conviction_fusion_votes._scn)."""
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


def test_aligned_cot_vote_promotes_conviction() -> None:
    vote = _vote(net=15_000, net_4w=5_000)  # up, strength 1.0, fresh 1.0
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"
    assert "cot" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))  # 66.0


def test_opposed_cot_vote_demotes_but_keeps_direction() -> None:
    vote = _vote(net=5_000, net_4w=15_000)  # down, strength 1.0
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"  # bucket-derived; the vote did NOT flip it (ADR-017)
    assert "cot" in g.disagreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))  # 54.0


def test_usd_jpy_polarity_composes_correctly_in_fuser() -> None:
    # Rising YEN longs → vote "down" → AGREES with a bearish USD_JPY bias (promotes).
    vote = _vote(asset="USD_JPY", net=15_000, net_4w=5_000)
    g = fuse_conviction(asset="USD_JPY", scenarios=_scn(0.40, 0.60), votes=[vote])
    assert g.direction == "down"
    assert "cot" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))


def test_absent_cot_vote_is_byte_identical_to_no_vote() -> None:
    absent = _vote(status="absent")  # honest_absence
    with_absent = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[absent])
    no_votes = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40))
    assert with_absent == no_votes  # frozen dataclass equality over every field


def test_cot_vote_emits_no_trade_tokens_in_rationale() -> None:
    for vote in (_vote(net=15_000, net_4w=5_000), _vote(net=5_000, net_4w=15_000)):
        g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
        assert _FORBIDDEN_RE.search(g.rationale_fr) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
