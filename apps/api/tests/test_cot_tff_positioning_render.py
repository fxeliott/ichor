"""S04 atomic #6 — full trader-category breakdown in the positioning sections.

`_section_tff_positioning` previously surfaced 4 of the 5 TFF trader classes
(Dealer / AssetMgr / LevFunds / Other) and dropped Non-reportable (small/retail).
`_section_cot` surfaced only managed_money + swap_dealer and dropped Commercials
(producer/merchant — the classic COT smart-money anchor) + Other-reportable +
Non-reportable. All those columns are persisted by the collectors but never
reached the LLM data-pool. This test pins the now-complete breakdown.

No DB: an AsyncMock session whose execute() returns canned ORM-shaped rows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import (
    _COT_MARKET_BY_ASSET,
    _TFF_MARKET_BY_ASSET,
    _section_cot,
    _section_tff_positioning,
)

_TODAY = datetime.now(UTC).date()


# --------------------------------------------------------------------------- #
# row builders                                                                #
# --------------------------------------------------------------------------- #
def _tff_row(
    market: str,
    report_date: date,
    *,
    nonrept_long: int = 40_000,
    nonrept_short: int = 25_000,
) -> SimpleNamespace:
    return SimpleNamespace(
        market_code=market,
        report_date=report_date,
        open_interest=1_000_000,
        dealer_long=100_000,
        dealer_short=120_000,
        asset_mgr_long=300_000,
        asset_mgr_short=180_000,
        lev_money_long=150_000,
        lev_money_short=210_000,
        other_rept_long=50_000,
        other_rept_short=40_000,
        nonrept_long=nonrept_long,
        nonrept_short=nonrept_short,
    )


def _cot_row(
    market: str,
    report_date: date,
    *,
    producer_net: int = -120_000,
    non_reportable_net: int = 8_000,
) -> SimpleNamespace:
    return SimpleNamespace(
        market_code=market,
        report_date=report_date,
        managed_money_net=50_000,
        swap_dealer_net=-30_000,
        producer_net=producer_net,
        other_reportable_net=5_000,
        non_reportable_net=non_reportable_net,
        open_interest=600_000,
    )


class _RowsResult:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def scalars(self):  # noqa: ANN202
        rows = self._rows

        class _S:
            def all(self):  # noqa: ANN202
                return list(rows)

        return _S()


def _session(rows: list[SimpleNamespace]) -> AsyncMock:
    s = AsyncMock()
    s.execute = AsyncMock(return_value=_RowsResult(rows))
    return s


# --------------------------------------------------------------------------- #
# TFF — non-reportable (retail) is now surfaced                               #
# --------------------------------------------------------------------------- #
async def test_tff_fresh_renders_nonrept_class() -> None:
    market = _TFF_MARKET_BY_ASSET["EUR_USD"]
    cur = _tff_row(market, _TODAY, nonrept_long=40_000, nonrept_short=25_000)
    md, src, degraded = await _section_tff_positioning(_session([cur]), "EUR_USD")
    # nonrept_net = 40_000 - 25_000 = +15,000
    assert "Nonrept (small/retail) net = +15,000" in md
    # the 4 pre-existing classes are still rendered (no regression)
    assert "Dealer net = -20,000" in md  # 100k - 120k
    assert "LevFunds net = -60,000" in md  # 150k - 210k
    assert degraded == []  # fresh
    assert src == [f"CFTC:TFF:{market}@{_TODAY.isoformat()}"]
    assert is_adr017_clean(md)


async def test_tff_nonrept_delta_when_prev_present() -> None:
    market = _TFF_MARKET_BY_ASSET["GBP_USD"]
    cur = _tff_row(market, _TODAY, nonrept_long=40_000, nonrept_short=25_000)
    prev = _tff_row(market, _TODAY, nonrept_long=30_000, nonrept_short=25_000)
    md, _src, _deg = await _section_tff_positioning(_session([cur, prev]), "GBP_USD")
    # cur nonrept_net +15,000 ; prev +5,000 → Δ +10,000
    assert "Nonrept +10,000" in md
    assert is_adr017_clean(md)


# --------------------------------------------------------------------------- #
# COT — commercials + non-reportable are now surfaced                         #
# --------------------------------------------------------------------------- #
async def test_cot_fresh_renders_commercials_and_small_traders() -> None:
    market = _COT_MARKET_BY_ASSET["XAU_USD"]
    cur = _cot_row(market, _TODAY, producer_net=-120_000, non_reportable_net=8_000)
    prev = _cot_row(market, _TODAY)
    md, src, degraded = await _section_cot(_session([cur, prev]), "XAU_USD")
    assert "commercials_producer_net=-120,000" in md
    assert "small_traders_non_reportable_net=+8,000" in md
    assert "other_reportable_net=+5,000" in md
    # pre-existing managed_money still rendered
    assert "managed_money_net = +50,000" in md
    assert degraded == []
    assert src == [f"CFTC:COT:{market}@{_TODAY.isoformat()}"]
    assert is_adr017_clean(md)


# --------------------------------------------------------------------------- #
# the new fields must not break the degraded (absent / stale) branches        #
# --------------------------------------------------------------------------- #
async def test_tff_absent_branch_unaffected() -> None:
    md, src, degraded = await _section_tff_positioning(_session([]), "EUR_USD")
    assert len(degraded) == 1
    assert degraded[0].status == "absent"
    assert "no persisted rows" in md
    assert "Nonrept" not in md  # no data row → no breakdown line
    assert src == []


async def test_cot_stale_band_still_renders_new_fields() -> None:
    market = _COT_MARKET_BY_ASSET["EUR_USD"]
    cur = _cot_row(market, date(2020, 1, 1))
    md, _src, degraded = await _section_cot(_session([cur]), "EUR_USD")
    assert len(degraded) == 1
    assert degraded[0].status == "stale"
    assert "STALE" in md
    assert "commercials_producer_net=" in md  # breakdown present even when stale
    assert is_adr017_clean(md)


@pytest.mark.parametrize("asset", ["EUR_USD", "GBP_USD", "SPX500_USD", "NAS100_USD"])
async def test_tff_nonrept_live_witnessed_assets(asset: str) -> None:
    """The 4 assets whose TFF market is populated in prod (XAU 088691 absent)."""
    market = _TFF_MARKET_BY_ASSET[asset]
    cur = _tff_row(market, _TODAY)
    md, _src, degraded = await _section_tff_positioning(_session([cur]), asset)
    assert "Nonrept (small/retail) net =" in md
    assert degraded == []
    assert is_adr017_clean(md)
