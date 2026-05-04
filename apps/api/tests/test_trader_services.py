"""Pure tests for daily_levels + session_scenarios + rr_analysis."""

from __future__ import annotations

import pytest

from ichor_api.services.daily_levels import (
    DailyLevels,
    _classic_pivots,
    _round_levels_near,
    render_daily_levels_block,
)
from ichor_api.services.session_scenarios import (
    assess_session_scenarios,
    render_session_scenarios_block,
)
from ichor_api.services.rr_analysis import (
    assess_rr_plan,
    render_rr_block,
)


# ─────────────────────── daily_levels math ────────────────────────────


def test_classic_pivots_eur_usd_typical() -> None:
    pp, r1, r2, r3, s1, s2, s3 = _classic_pivots(1.0750, 1.0700, 1.0735)
    assert pp is not None and 1.07 < pp < 1.08
    assert r1 is not None and r1 > pp
    assert s1 is not None and s1 < pp
    # R2 - PP == PP - S2 (symmetric range)
    assert r2 is not None and s2 is not None
    assert (r2 - pp) == pytest.approx(pp - s2, abs=0.0001)


def test_classic_pivots_returns_nones_on_missing_input() -> None:
    pp, *rest = _classic_pivots(None, 1.07, 1.075)
    assert pp is None
    assert all(v is None for v in rest)


def test_round_levels_eur_usd_50_pip_step() -> None:
    levels = _round_levels_near(1.0734, "EUR_USD", count=2)
    # Should include 1.0700, 1.0750, 1.0800 etc.
    assert 1.0700 in [round(x, 4) for x in levels]
    assert 1.0750 in [round(x, 4) for x in levels]


def test_round_levels_usd_jpy_step_50_basis_points() -> None:
    levels = _round_levels_near(152.34, "USD_JPY", count=2)
    assert 152.0 in [round(x, 2) for x in levels]
    assert 152.5 in [round(x, 2) for x in levels]


def test_render_daily_levels_no_data() -> None:
    r = DailyLevels(
        asset="EUR_USD",
        spot=None, pdh=None, pdl=None, pd_close=None,
        asian_high=None, asian_low=None, weekly_high=None, weekly_low=None,
        pivot=None, r1=None, r2=None, r3=None, s1=None, s2=None, s3=None,
        round_levels=[],
    )
    md, sources = render_daily_levels_block(r)
    assert "no intraday bars" in md.lower()
    assert sources == []


def test_render_daily_levels_full_payload() -> None:
    r = DailyLevels(
        asset="EUR_USD",
        spot=1.0734, pdh=1.0750, pdl=1.0700, pd_close=1.0735,
        asian_high=1.0740, asian_low=1.0720, weekly_high=1.0780, weekly_low=1.0680,
        pivot=1.0728, r1=1.0756, r2=1.0778, r3=1.0805,
        s1=1.0706, s2=1.0678, s3=1.0656,
        round_levels=[1.07, 1.0725, 1.0750, 1.0775, 1.08],
    )
    md, sources = render_daily_levels_block(r)
    assert "EUR_USD" in md
    assert "PDH" in md or "Previous day" in md
    assert "Asian" in md
    assert "Pivots" in md
    assert sources == ["polygon_intraday:EUR_USD@daily_levels"]


# ─────────────────────── session_scenarios ────────────────────────────


def _levels_eur_at(spot: float, pdh: float = 1.0750, pdl: float = 1.0700) -> DailyLevels:
    return DailyLevels(
        asset="EUR_USD",
        spot=spot, pdh=pdh, pdl=pdl, pd_close=(pdh + pdl) / 2,
        asian_high=pdh - 0.0005, asian_low=pdl + 0.0005,
        weekly_high=pdh + 0.005, weekly_low=pdl - 0.005,
        pivot=(pdh + pdl) / 2, r1=pdh + 0.0010, r2=pdh + 0.0020, r3=pdh + 0.0040,
        s1=pdl - 0.0010, s2=pdl - 0.0020, s3=pdl - 0.0040,
        round_levels=[],
    )


def test_session_scenarios_probabilities_sum_to_one() -> None:
    s = assess_session_scenarios(
        _levels_eur_at(1.0735),
        session_type="pre_londres",
        regime="goldilocks",
        conviction_pct=60,
    )
    total = s.p_continuation + s.p_reversal + s.p_sideways
    assert total == pytest.approx(1.0, abs=0.005)


def test_session_scenarios_high_conviction_extreme_tilts_continuation() -> None:
    """Spot near PDH + high conviction → P(continuation) > P(sideways)."""
    s = assess_session_scenarios(
        _levels_eur_at(1.0748),  # near PDH
        session_type="pre_ny",
        regime="goldilocks",
        conviction_pct=80,
    )
    assert s.p_continuation > s.p_sideways


def test_session_scenarios_swept_extreme_tilts_reversal() -> None:
    """Spot above PDH (swept) → P(reversal) elevated."""
    s = assess_session_scenarios(
        _levels_eur_at(1.0760, pdh=1.0750, pdl=1.0700),  # swept above PDH
        session_type="pre_ny",
        regime="haven_bid",
        conviction_pct=40,
    )
    # When swept, p_rev gets +0.25 contribution → meaningfully > 0.20 floor
    assert s.p_reversal > 0.30


def test_session_scenarios_low_conviction_mid_range_tilts_sideways() -> None:
    """Spot mid-range + low conviction → sideways dominates."""
    s = assess_session_scenarios(
        _levels_eur_at(1.0725),  # middle of [1.0700, 1.0750]
        session_type="pre_londres",
        regime="usd_complacency",
        conviction_pct=15,
    )
    assert s.p_sideways > 0.30


def test_session_scenarios_returns_neutral_on_missing_levels() -> None:
    levels = DailyLevels(
        asset="EUR_USD",
        spot=None, pdh=None, pdl=None, pd_close=None,
        asian_high=None, asian_low=None, weekly_high=None, weekly_low=None,
        pivot=None, r1=None, r2=None, r3=None, s1=None, s2=None, s3=None,
        round_levels=[],
    )
    s = assess_session_scenarios(
        levels, session_type="pre_londres", regime=None, conviction_pct=50
    )
    assert s.p_continuation == pytest.approx(0.34, abs=0.01)
    assert s.p_reversal == pytest.approx(0.33, abs=0.01)
    assert s.p_sideways == pytest.approx(0.33, abs=0.01)


def test_render_session_scenarios_includes_triggers() -> None:
    s = assess_session_scenarios(
        _levels_eur_at(1.0747),
        session_type="pre_ny",
        regime="goldilocks",
        conviction_pct=70,
    )
    md, sources = render_session_scenarios_block(s)
    assert "Continuation" in md
    assert "Reversal" in md
    assert "Sideways" in md
    assert "%" in md
    assert "EUR_USD" in md
    assert sources == ["empirical_model:session_scenarios:EUR_USD"]


# ─────────────────────── rr_analysis ──────────────────────────────────


def test_rr_plan_long_eur_usd_typical() -> None:
    plan = assess_rr_plan(
        asset="EUR_USD",
        spot=1.0734,
        bias="long",
        conviction_pct=70,
        magnitude_pips_low=30,
        magnitude_pips_high=80,
    )
    assert plan.bias == "long"
    assert plan.entry_zone_low is not None
    assert plan.entry_zone_high is not None
    assert plan.stop_loss is not None and plan.stop_loss < 1.0734
    assert plan.tp1 is not None and plan.tp1 > 1.0734
    assert plan.tp3 is not None and plan.tp3 > plan.tp1
    assert plan.tp_extended is not None and plan.tp_extended > plan.tp3
    assert plan.risk_pips == 15.0  # 30 / 2
    assert plan.reward_pips_tp3 == 45.0  # 15 * 3


def test_rr_plan_short_usd_jpy() -> None:
    plan = assess_rr_plan(
        asset="USD_JPY",
        spot=152.34,
        bias="short",
        conviction_pct=60,
        magnitude_pips_low=40,
        magnitude_pips_high=120,
    )
    assert plan.bias == "short"
    assert plan.stop_loss is not None and plan.stop_loss > 152.34
    assert plan.tp3 is not None and plan.tp3 < 152.34
    assert plan.risk_pips == 20.0


def test_rr_plan_neutral_returns_blank() -> None:
    plan = assess_rr_plan(
        asset="EUR_USD",
        spot=1.0734,
        bias="neutral",
        conviction_pct=15,
        magnitude_pips_low=10,
        magnitude_pips_high=30,
    )
    assert plan.entry_zone_low is None
    assert plan.stop_loss is None
    assert plan.tp3 is None
    assert "neutral" in plan.notes.lower() or "n/c" in plan.notes.lower()


def test_rr_plan_low_conviction_warning() -> None:
    plan = assess_rr_plan(
        asset="EUR_USD",
        spot=1.0734,
        bias="long",
        conviction_pct=20,
        magnitude_pips_low=30,
        magnitude_pips_high=80,
    )
    assert "size" in plan.notes.lower() or "réduire" in plan.notes.lower()


def test_rr_plan_min_risk_5_pips() -> None:
    """Even when magnitude is tiny, risk floor at 5 pips."""
    plan = assess_rr_plan(
        asset="EUR_USD",
        spot=1.0734,
        bias="long",
        conviction_pct=70,
        magnitude_pips_low=4,
        magnitude_pips_high=10,
    )
    assert plan.risk_pips == 5.0


def test_render_rr_plan_full() -> None:
    plan = assess_rr_plan(
        asset="EUR_USD",
        spot=1.0734,
        bias="long",
        conviction_pct=70,
        magnitude_pips_low=30,
        magnitude_pips_high=80,
    )
    md, sources = render_rr_block(plan)
    assert "RR plan" in md
    assert "EUR_USD" in md
    assert "LONG" in md
    assert "Stop" in md
    assert "TP1" in md
    assert "TP3" in md
    assert sources == ["empirical_model:rr_plan:EUR_USD"]


def test_render_rr_plan_neutral() -> None:
    plan = assess_rr_plan(
        asset="EUR_USD",
        spot=1.0734,
        bias="neutral",
        conviction_pct=15,
        magnitude_pips_low=None,
        magnitude_pips_high=None,
    )
    md, sources = render_rr_block(plan)
    assert "neutral" in md or "magnitude" in md
    assert sources == []
