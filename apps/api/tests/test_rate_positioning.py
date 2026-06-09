"""Tests for the S04 TIER-2 #4 UST-10Y rate-positioning context section.

`data_pool._section_rate_positioning(session, asset)` surfaces UST 10Y futures
positioning (TFF code 043602) as the discount-rate context for the rate-sensitive
equity indices (SPX500 / NAS100), descriptive + non-directional. No DB: an
AsyncSession stub whose execute() returns canned CftcTffObservation-shaped rows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ichor_api.collectors.cftc_tff import TRACKED_MARKET_CODES
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import (
    _RATE_CONTEXT_BY_ASSET,
    _UST_10Y_TFF_CODE,
    _section_rate_positioning,
)

_TODAY = datetime.now(UTC).date()


def _tff(
    report_date: date,
    *,
    lev_long: int,
    lev_short: int,
    am_long: int,
    am_short: int,
    oi: int = 1_000_000,
) -> SimpleNamespace:
    return SimpleNamespace(
        market_code=_UST_10Y_TFF_CODE,
        report_date=report_date,
        open_interest=oi,
        lev_money_long=lev_long,
        lev_money_short=lev_short,
        asset_mgr_long=am_long,
        asset_mgr_short=am_short,
    )


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)

        return _S()


def _session(rows):
    s = AsyncMock()
    s.execute = AsyncMock(return_value=_RowsResult(rows))
    return s


def test_rate_context_codes_subset_of_collector() -> None:
    # Guard (consumer ⊆ collector): the UST code must be one the TFF collector fetches.
    missing = set(_RATE_CONTEXT_BY_ASSET.values()) - set(TRACKED_MARKET_CODES)
    assert not missing, f"_RATE_CONTEXT_BY_ASSET codes not collected: {sorted(missing)}"


def test_rate_context_maps_only_index_assets() -> None:
    assert set(_RATE_CONTEXT_BY_ASSET) == {"SPX500_USD", "NAS100_USD"}
    assert all(code == _UST_10Y_TFF_CODE for code in _RATE_CONTEXT_BY_ASSET.values())


@pytest.mark.parametrize("asset", ["EUR_USD", "GBP_USD", "XAU_USD", "USD_JPY"])
async def test_non_index_asset_zero_db(asset: str) -> None:
    session = AsyncMock()
    md, src, degraded = await _section_rate_positioning(session, asset)
    assert md == ""
    assert src == []
    assert degraded == []  # not rate-mapped → no source expected, not degraded
    assert session.execute.await_count == 0


@pytest.mark.parametrize("asset", ["SPX500_USD", "NAS100_USD"])
async def test_index_asset_fresh_renders_rate_context(asset: str) -> None:
    cur = _tff(_TODAY, lev_long=300_000, lev_short=500_000, am_long=900_000, am_short=400_000)
    prev = _tff(_TODAY, lev_long=320_000, lev_short=480_000, am_long=880_000, am_short=410_000)
    md, src, degraded = await _section_rate_positioning(_session([cur, prev]), asset)
    assert "UST 10Y" in md
    assert "LevFunds net = -200,000" in md  # 300k - 500k
    assert "AssetMgr net = +500,000" in md  # 900k - 400k
    assert "not a direction" in md
    assert "Δw/w" in md
    assert degraded == []  # fresh
    assert src == [f"CFTC:TFF:{_UST_10Y_TFF_CODE}@{_TODAY.isoformat()}"]
    assert is_adr017_clean(md)


async def test_index_asset_absent_is_degraded() -> None:
    md, src, degraded = await _section_rate_positioning(_session([]), "SPX500_USD")
    assert len(degraded) == 1
    assert degraded[0].series_id == f"CFTC:TFF:{_UST_10Y_TFF_CODE}"
    assert degraded[0].status == "absent"
    assert "no persisted rows" in md
    assert src == []


async def test_index_asset_stale_is_degraded_with_band() -> None:
    cur = _tff(date(2020, 1, 1), lev_long=1, lev_short=2, am_long=3, am_short=1)
    md, _src, degraded = await _section_rate_positioning(_session([cur]), "NAS100_USD")
    assert len(degraded) == 1
    assert degraded[0].status == "stale"
    assert "STALE" in md
    assert is_adr017_clean(md)
