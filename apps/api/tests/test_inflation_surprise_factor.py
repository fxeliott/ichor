"""r137 — tests for the regime-conditioned inflation-surprise confluence
driver (`_factor_inflation_surprise`).

The driver is SEPARATE from the growth `surprise_index` factor (orthogonal
regime axes). Per the ichor-trader r137 advisory :
  - USD leg unconditional (hot inflation = USD-positive across regimes)
  - equity leg conditioned on the growth backdrop (dampened under reflation)
  - XAU = 0 (sign genuinely ambiguous)
  - smaller coefficient (×0.3 vs growth's ×0.5)
"""

from __future__ import annotations

import pytest
from ichor_api.services import confluence_engine
from ichor_api.services.surprise_index import SurpriseIndexReading


def _reading(*, inflation: float | None, growth: float | None) -> SurpriseIndexReading:
    return SurpriseIndexReading(
        region="US",
        composite=growth,
        band="neutral",
        series=[],
        n_series_used=0,
        inflation_composite=inflation,
    )


def _patch(monkeypatch, reading: SurpriseIndexReading) -> None:
    async def _fake(_session) -> SurpriseIndexReading:
        return reading

    monkeypatch.setattr(confluence_engine, "assess_surprise_index", _fake)


@pytest.mark.asyncio
async def test_returns_none_when_inflation_composite_absent(monkeypatch) -> None:
    _patch(monkeypatch, _reading(inflation=None, growth=0.5))
    d = await confluence_engine._factor_inflation_surprise(None, "SPX500_USD")
    assert d is None


@pytest.mark.asyncio
async def test_xau_contribution_is_zero_by_design(monkeypatch) -> None:
    # Gold's inflation reaction is a genuine 3-way tug → honest zero.
    _patch(monkeypatch, _reading(inflation=4.0, growth=-1.0))
    d = await confluence_engine._factor_inflation_surprise(None, "XAU_USD")
    assert d is not None
    assert d.contribution == 0.0
    assert d.factor == "inflation_surprise"  # SEPARATE from growth factor


@pytest.mark.asyncio
async def test_equity_full_negative_under_stagflation(monkeypatch) -> None:
    # Hot inflation (+2.0) + soft growth (≤0) → full equity-negative.
    # raw = clamp(2.0 * 0.3, -1, 1) = 0.6 ; equity_damp = 1.0 (growth ≤ 0).
    _patch(monkeypatch, _reading(inflation=2.0, growth=-0.5))
    d = await confluence_engine._factor_inflation_surprise(None, "SPX500_USD")
    assert d is not None
    assert d.contribution == pytest.approx(-0.6, abs=1e-9)


@pytest.mark.asyncio
async def test_equity_dampened_under_reflation(monkeypatch) -> None:
    # Hot inflation (+2.0) + hot growth (+1.0) → dampened equity-negative.
    # raw = 0.6 ; reflation = 1.0 → equity_damp = 1.0 - 0.7 = 0.3 ;
    # contribution = -0.6 * 0.3 = -0.18 (much weaker hawkish hit).
    _patch(monkeypatch, _reading(inflation=2.0, growth=1.0))
    d = await confluence_engine._factor_inflation_surprise(None, "NAS100_USD")
    assert d is not None
    assert d.contribution == pytest.approx(-0.18, abs=1e-9)
    # The reflation dampening must make |equity| SMALLER than the stagflation case.
    assert abs(d.contribution) < 0.6


@pytest.mark.asyncio
async def test_usd_leg_is_unconditional_x_usd(monkeypatch) -> None:
    # EUR_USD : hot inflation → USD strong → short the pair (-raw), and this
    # sign does NOT depend on the growth backdrop (USD leg is regime-robust).
    for growth in (-1.0, 0.0, 1.0):
        _patch(monkeypatch, _reading(inflation=2.0, growth=growth))
        d = await confluence_engine._factor_inflation_surprise(None, "EUR_USD")
        assert d is not None
        assert d.contribution == pytest.approx(-0.6, abs=1e-9)  # always -raw


@pytest.mark.asyncio
async def test_usd_leg_unconditional_usd_base(monkeypatch) -> None:
    # USD_CAD (USD-base) : hot inflation → USD strong → pair UP (+raw),
    # unconditional on growth.
    for growth in (-1.0, 1.0):
        _patch(monkeypatch, _reading(inflation=2.0, growth=growth))
        d = await confluence_engine._factor_inflation_surprise(None, "USD_CAD")
        assert d is not None
        assert d.contribution == pytest.approx(0.6, abs=1e-9)  # always +raw


@pytest.mark.asyncio
async def test_coefficient_smaller_than_growth(monkeypatch) -> None:
    # Inflation uses ×0.3 ; growth uses ×0.5. For the SAME z and the USD
    # (unconditional) leg, |inflation contribution| < |growth contribution|.
    _patch(monkeypatch, _reading(inflation=1.0, growth=0.0))
    infl = await confluence_engine._factor_inflation_surprise(None, "EUR_USD")
    assert infl is not None
    # inflation: -clamp(1.0*0.3) = -0.3 ; growth would be -clamp(1.0*0.5) = -0.5.
    assert infl.contribution == pytest.approx(-0.3, abs=1e-9)
    assert abs(infl.contribution) < 0.5


@pytest.mark.asyncio
async def test_contribution_clamped_to_unit_interval(monkeypatch) -> None:
    # Extreme inflation z (+10) → raw clamps to 1.0 ; USD leg = -1.0.
    _patch(monkeypatch, _reading(inflation=10.0, growth=-1.0))
    d = await confluence_engine._factor_inflation_surprise(None, "EUR_USD")
    assert d is not None
    assert d.contribution == pytest.approx(-1.0, abs=1e-9)
    assert -1.0 <= d.contribution <= 1.0


@pytest.mark.asyncio
async def test_evidence_names_the_regime(monkeypatch) -> None:
    _patch(monkeypatch, _reading(inflation=2.0, growth=1.0))
    d = await confluence_engine._factor_inflation_surprise(None, "SPX500_USD")
    assert d is not None
    assert "inflation-surprise composite" in d.evidence
    assert "reflation" in d.evidence  # growth hot → reflation backdrop named
