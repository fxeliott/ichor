"""Tests for services/cross_asset_heatmap.py.

Validates :
  - Bias classification per series (risk-on sign convention)
  - Empty-state handling (no FRED / no market_data → all-None cells)
  - Spread computation (10Y-2Y) when both sides exist
  - HY/IG/EM OAS pct→bps conversion
  - 4 rows × 4 cells output shape always
  - Source list dedup
  - Pure helpers (_pct_change, _level, _unique_sources, _bias_from_signed_value)

The orchestrator now issues 2 batched queries (FRED IN + market_data IN)
instead of 20 sequential ones — tests use a stub session that returns
canned (asset/series_id, date, value) tuples directly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from ichor_api.services.cross_asset_heatmap import (
    HeatmapCell,
    HeatmapRow,
    _bias_from_signed_value,
    _level,
    _pct_change,
    _unique_sources,
    assess_cross_asset_heatmap,
)

# ─────────────────────── pure helpers ───────────────────────


def test_bias_uses_risk_sign_for_known_assets() -> None:
    assert _bias_from_signed_value("SPX", 0.5) == "bull"
    assert _bias_from_signed_value("SPX", -0.5) == "bear"
    assert _bias_from_signed_value("VIX", 0.5) == "bear"  # VIX up = risk-off
    assert _bias_from_signed_value("VIX", -0.5) == "bull"
    assert _bias_from_signed_value("DXY", 0.5) == "bear"  # USD up = risk-off


def test_bias_neutral_below_threshold() -> None:
    assert _bias_from_signed_value("SPX", 0.02) == "neutral"
    assert _bias_from_signed_value("SPX", -0.04) == "neutral"


def test_bias_neutral_for_none_value() -> None:
    assert _bias_from_signed_value("SPX", None) == "neutral"


def test_bias_unknown_asset_defaults_to_plus_one_sign() -> None:
    assert _bias_from_signed_value("UNKNOWN_THING", 0.5) == "bull"


def test_pct_change_basic() -> None:
    assert _pct_change([110.0, 100.0]) == 10.0
    assert _pct_change([100.0, 110.0]) == pytest.approx(-9.0909, rel=1e-3)


def test_pct_change_handles_short_or_zero() -> None:
    assert _pct_change(None) is None
    assert _pct_change([]) is None
    assert _pct_change([100.0]) is None
    assert _pct_change([100.0, 0.0]) is None  # division-by-zero guard


def test_level_returns_first_or_none() -> None:
    assert _level([4.18, 4.16, 4.15]) == 4.18
    assert _level([]) is None
    assert _level(None) is None


def test_unique_sources_dedupes_preserving_order() -> None:
    out = _unique_sources(
        ["FRED:DGS10", "FRED:DGS2", "FRED:DGS10", "market_data:EUR_USD", "FRED:DGS2"]
    )
    assert out == ["FRED:DGS10", "FRED:DGS2", "market_data:EUR_USD"]


def test_unique_sources_handles_empty() -> None:
    assert _unique_sources([]) == []
    assert _unique_sources(iter([])) == []


# ─────────────────────── orchestrator (batched queries) ───────────────────────


class _CannedResult:
    """Minimal sqlalchemy.Result stand-in : `.all()` returns the canned rows."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _StubSession:
    """Returns FRED rows on first execute(), market_data rows on second.

    The orchestrator calls _fetch_fred_latest_two then _fetch_market_latest_two
    in that order ; we route by call index. This is more robust than
    parsing SQL strings.
    """

    def __init__(
        self,
        *,
        fred_rows: list[tuple[str, date, float]] | None = None,
        market_rows: list[tuple[str, date, float]] | None = None,
    ) -> None:
        self._fred = fred_rows or []
        self._market = market_rows or []
        self._calls = 0

    async def execute(self, _stmt: Any) -> _CannedResult:
        self._calls += 1
        if self._calls == 1:
            return _CannedResult(self._fred)
        return _CannedResult(self._market)


def _fred_row(sid: str, days_ago: int, value: float) -> tuple[str, date, float]:
    today = datetime.now(UTC).date()
    return (sid, today - timedelta(days=days_ago), value)


def _mkt_row(asset: str, days_ago: int, close: float) -> tuple[str, date, float]:
    today = datetime.now(UTC).date()
    return (asset, today - timedelta(days=days_ago), close)


@pytest.mark.asyncio
async def test_assess_returns_4_rows_4_cells_each() -> None:
    session = _StubSession()
    h = await assess_cross_asset_heatmap(session)
    assert len(h.rows) == 4
    for row in h.rows:
        assert isinstance(row, HeatmapRow)
        assert len(row.cells) == 4
        for c in row.cells:
            assert isinstance(c, HeatmapCell)


@pytest.mark.asyncio
async def test_assess_with_no_data_returns_neutral_cells() -> None:
    session = _StubSession()
    h = await assess_cross_asset_heatmap(session)
    for row in h.rows:
        for c in row.cells:
            assert c.value is None
            assert c.bias == "neutral"
    assert h.sources == []


@pytest.mark.asyncio
async def test_assess_computes_2s10s_spread_when_both_yields_present() -> None:
    session = _StubSession(fred_rows=[_fred_row("DGS10", 0, 4.18), _fred_row("DGS2", 0, 4.62)])
    h = await assess_cross_asset_heatmap(session)
    rates_row = next(r for r in h.rows if r.row == "Rates")
    spread_cell = next(c for c in rates_row.cells if c.sym == "10Y-2Y")
    assert spread_cell.value == pytest.approx(-0.44)
    assert spread_cell.bias == "bear"  # inverted curve


@pytest.mark.asyncio
async def test_assess_credit_oas_pct_to_bps() -> None:
    """FRED stores OAS as percentage (e.g. 3.12) ; surface in bps (312)."""
    session = _StubSession(
        fred_rows=[
            _fred_row("BAMLH0A0HYM2", 0, 3.12),
            _fred_row("BAMLC0A0CM", 0, 0.96),
        ]
    )
    h = await assess_cross_asset_heatmap(session)
    credit_row = next(r for r in h.rows if r.row == "Credit")
    hy_cell = next(c for c in credit_row.cells if c.sym == "HY OAS")
    ig_cell = next(c for c in credit_row.cells if c.sym == "IG OAS")
    assert hy_cell.value == pytest.approx(312.0)
    assert ig_cell.value == pytest.approx(96.0)


@pytest.mark.asyncio
async def test_assess_credit_high_oas_flags_bear() -> None:
    session = _StubSession(
        fred_rows=[
            _fred_row("BAMLH0A0HYM2", 0, 5.5),
            _fred_row("BAMLC0A0CM", 0, 1.4),
        ]
    )
    h = await assess_cross_asset_heatmap(session)
    credit_row = next(r for r in h.rows if r.row == "Credit")
    hy_cell = next(c for c in credit_row.cells if c.sym == "HY OAS")
    ig_cell = next(c for c in credit_row.cells if c.sym == "IG OAS")
    assert hy_cell.bias == "bear"  # 550bps > 400 = bear
    assert ig_cell.bias == "bear"  # 140bps > 130 = bear


@pytest.mark.asyncio
async def test_assess_market_pct_change_1d_computes() -> None:
    """SPX up 0.5 % from 4500 → 4522.5."""
    session = _StubSession(
        market_rows=[
            _mkt_row("SPX", 0, 4522.5),
            _mkt_row("SPX", 1, 4500.0),
        ]
    )
    h = await assess_cross_asset_heatmap(session)
    risk_row = next(r for r in h.rows if r.row == "Risk-on")
    spx_cell = next(c for c in risk_row.cells if c.sym == "SPX")
    assert spx_cell.value == pytest.approx(0.5, rel=1e-3)
    assert spx_cell.bias == "bull"


@pytest.mark.asyncio
async def test_assess_only_one_close_returns_none() -> None:
    """One close = no pct change available."""
    session = _StubSession(market_rows=[_mkt_row("SPX", 0, 4500.0)])
    h = await assess_cross_asset_heatmap(session)
    risk_row = next(r for r in h.rows if r.row == "Risk-on")
    spx_cell = next(c for c in risk_row.cells if c.sym == "SPX")
    assert spx_cell.value is None
    assert spx_cell.bias == "neutral"


@pytest.mark.asyncio
async def test_assess_generated_at_recent() -> None:
    session = _StubSession()
    before = datetime.now(UTC)
    h = await assess_cross_asset_heatmap(session)
    after = datetime.now(UTC)
    assert before <= h.generated_at <= after


@pytest.mark.asyncio
async def test_assess_dedupes_sources() -> None:
    """Same source must appear at most once."""
    session = _StubSession(
        fred_rows=[
            _fred_row("DGS10", 0, 4.18),
            _fred_row("DGS10", 1, 4.16),  # same series, different day
        ],
        market_rows=[
            _mkt_row("EUR_USD", 0, 1.10),
            _mkt_row("EUR_USD", 1, 1.099),
        ],
    )
    h = await assess_cross_asset_heatmap(session)
    counts: dict[str, int] = {}
    for s in h.sources:
        counts[s] = counts.get(s, 0) + 1
    for src, n in counts.items():
        assert n == 1, f"source {src} appeared {n}× — should be deduped"
