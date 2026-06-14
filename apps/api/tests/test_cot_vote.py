"""S06 Chantier C · C-3 slice-0 — ``cot_vote.build_cot_vote`` producer tests.

Pure unit tests (no DB, no LLM): the mapper is a deterministic primitive
(``cot_vote.py``). Two layers of coverage:

  1. the mapper in isolation — directional read, per-asset polarity, OI-normalised
     strength, 1-week-inflection dampening, freshness decay, and every
     honest-absence gate (ADR-103);
  2. the mapper *integrated* into ``conviction_fusion.fuse_conviction(votes=...)`` —
     proving a COT vote moves conviction the right way, never flips direction
     (ADR-017), and that an absent vote is byte-identical to no vote (ADR-103).

Doctrine anchors verified 2026-06-14 (cftc.gov + reputable aggregators): flow =
momentum (``sign(Δ4w)``), 1-week contradiction = dampen, extremes = abstain,
normalise to open interest. See ``cot_vote.py`` module docstring for sources.
"""

from __future__ import annotations

import re

import pytest
from ichor_api.services import cot_vote as cot_vote_mod
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.cot_vote import (
    COT_FULL_STRENGTH_OI_FRACTION,
    COT_MAX_AGE_DAYS,
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


def _vote(
    *,
    asset: str = "EUR_USD",
    status: str = "fresh",
    net: int | None = 15_000,
    net_1w: int | None = None,
    net_4w: int | None = 5_000,
    oi: int | None = _OI,
    age_days: int | None = 0,
    cot_index_pct: float | None = None,
):
    """Default = a clean +10_000 4-week flow on EUR_USD, fresh (age 0)."""
    return build_cot_vote(
        asset=asset,
        status=status,
        managed_money_net=net,
        managed_money_net_1w_ago=net_1w,
        managed_money_net_4w_ago=net_4w,
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
    assert v.freshness == pytest.approx(1.0)  # age 0
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
# Freshness decay                                                              #
# --------------------------------------------------------------------------- #


def test_freshness_decays_linearly() -> None:
    v = _vote(age_days=7)  # half the 14-day window
    assert v.freshness == pytest.approx(1.0 - 7.0 / COT_MAX_AGE_DAYS)  # 0.5


def test_stale_report_is_inert_via_zero_freshness() -> None:
    v = _vote(age_days=20)  # older than the 14-day window
    assert v.freshness == pytest.approx(0.0)
    assert v.is_effective is False  # freshness 0 → contributes nothing
    assert v.signed_contribution() == pytest.approx(0.0)
    # NOT honest_absence: the data exists, it is just too old to weigh.
    assert v.honest_absence is False


# --------------------------------------------------------------------------- #
# Honest-absence gates (ADR-103) — each contributes EXACTLY 0                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs",
    [
        {"asset": "SPX500_USD"},  # outside the COT whitelist (no E-mini code yet)
        {"asset": "ZZZ_ZZZ"},  # unknown asset
        {"status": "absent"},  # COT table empty for this market
        {"net": None},  # no latest row
        {"net_4w": None},  # < 5 weekly reports → no 4-week trend
        {"oi": None},  # cannot normalise
        {"oi": 0},  # cannot normalise (zero OI)
        {"age_days": None},  # cannot verify freshness
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
    v = _vote(net=10_000_000, net_4w=0, oi=1)
    assert 0.0 <= v.strength <= 1.0
    assert 0.0 <= v.freshness <= 1.0


def test_zero_flow_guard_abstains_even_if_noise_floor_lowered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fail-closed hardening (fresh-verifier MINOR): if the noise floor were ever
    # lowered to 0, a flat 4-week flow (Δ4w == 0) must STILL abstain — never emit a
    # phantom directional vote. Guards the "asset_dir != 0" invariant explicitly.
    monkeypatch.setattr(cot_vote_mod, "COT_MIN_OI_FRACTION", 0.0)
    v = build_cot_vote(
        asset="EUR_USD",
        status="fresh",
        managed_money_net=10_000,
        managed_money_net_1w_ago=None,
        managed_money_net_4w_ago=10_000,  # Δ4w == 0 (would pass a 0.0 noise floor)
        open_interest=_OI,
        age_days=0,
    )
    assert v.honest_absence is True
    assert v.signed_contribution() == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Integration into the fuser (flag-ON behaviour, ADR-017 / ADR-103 / ADR-022)  #
# --------------------------------------------------------------------------- #


def test_aligned_cot_vote_promotes_conviction() -> None:
    vote = _vote(net=15_000, net_4w=5_000, age_days=0)  # up, strength 1.0, fresh 1.0
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"
    assert "cot" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))  # 66.0


def test_opposed_cot_vote_demotes_but_keeps_direction() -> None:
    vote = _vote(net=5_000, net_4w=15_000, age_days=0)  # down, strength 1.0
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"  # bucket-derived; the vote did NOT flip it (ADR-017)
    assert "cot" in g.disagreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))  # 54.0


def test_usd_jpy_polarity_composes_correctly_in_fuser() -> None:
    # Rising YEN longs → vote "down" → AGREES with a bearish USD_JPY bias (promotes).
    vote = _vote(asset="USD_JPY", net=15_000, net_4w=5_000, age_days=0)
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
