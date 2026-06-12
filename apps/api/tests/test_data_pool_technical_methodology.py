"""S05 / Chantier E slice-1 wiring tests — ``_section_technical_methodology``.

Pins the section contract (ADR-113) :
- honest-absence prose when the read is unavailable (doctrine #11)
- populated FR prose when the read exists
- ADR-017 boundary on rendered prose (no order tokens)
- canonical source stamps (``polygon:{asset}@{ts}`` + ``methodologie:ADR-113``
  populated ; ``technical_reading:{asset}:absent`` on absence)
- section wired into ``build_data_pool`` AND ``build_asset_data_only``

Doctrine #5 pure-module discipline : monkeypatch on the internal
``assess_technical_reading`` call, no DB hit.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from ichor_api.services import data_pool as dp_mod
from ichor_api.services import technical_analysis as ta_mod
from ichor_api.services.data_pool import _section_technical_methodology
from ichor_api.services.london_session import Bar
from ichor_api.services.technical_analysis import compute_technical_reading

_FORBIDDEN_TRADE_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

_NOW = datetime(2026, 6, 11, 9, 0, tzinfo=UTC)


def _hour_bars(hour_utc: datetime, o: float, h: float, lo: float, c: float) -> list[Bar]:
    bars: list[Bar] = []
    for i in range(60):
        ts = hour_utc + timedelta(minutes=i)
        if i == 0:
            bars.append(Bar(ts=ts, open=o, high=max(o, c), low=min(o, c), close=c))
        elif i == 1:
            bars.append(Bar(ts=ts, open=c, high=h, low=c, close=c))
        elif i == 2:
            bars.append(Bar(ts=ts, open=c, high=c, low=lo, close=c))
        else:
            bars.append(Bar(ts=ts, open=c, high=c, low=c, close=c))
    return bars


def _scenario_bars() -> list[Bar]:
    """Mirror of the pure-core scenario (filler + 06-10 NY session + 06-11 AM)."""
    bars: list[Bar] = []
    base = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)
    px = 1.1000
    for i in range(24):
        hour = base + timedelta(hours=i)
        if i % 2 == 0:
            bars += _hour_bars(hour, px, px + 0.0011, px - 0.0001, px + 0.0010)
            px += 0.0010
        else:
            bars += _hour_bars(hour, px, px + 0.0001, px - 0.0011, px - 0.0010)
            px -= 0.0010
    d = datetime(2026, 6, 10, tzinfo=UTC)
    bars += _hour_bars(d.replace(hour=10), 1.0990, 1.1002, 1.0989, 1.1000)
    bars += _hour_bars(d.replace(hour=11), 1.1000, 1.1010, 1.0995, 1.1002)
    bars += _hour_bars(d.replace(hour=12), 1.1002, 1.1004, 1.0978, 1.0980)
    bars += _hour_bars(d.replace(hour=13), 1.0980, 1.0982, 1.0948, 1.0950)
    bars += _hour_bars(d.replace(hour=14), 1.0950, 1.0952, 1.0928, 1.0930)
    bars += _hour_bars(d.replace(hour=15), 1.0930, 1.0940, 1.0920, 1.0932)
    bars += _hour_bars(d.replace(hour=16), 1.0932, 1.0962, 1.0930, 1.0960)
    bars += _hour_bars(d.replace(hour=17), 1.0960, 1.0982, 1.0958, 1.0980)
    bars += _hour_bars(datetime(2026, 6, 11, 7, 0, tzinfo=UTC), 1.0980, 1.0992, 1.0975, 1.0990)
    bars += _hour_bars(datetime(2026, 6, 11, 8, 0, tzinfo=UTC), 1.0990, 1.1000, 1.0988, 1.0995)
    return bars


class TestSectionHonestAbsence:
    def test_absence_prose_and_stamp(self) -> None:
        async def _run() -> None:
            with patch.object(ta_mod, "assess_technical_reading", AsyncMock(return_value=None)):
                md, sources = await _section_technical_methodology(
                    session=AsyncMock(), asset="EUR_USD"
                )
            assert "absence honnête" in md
            assert "ADR-017" in md
            assert sources == ["technical_reading:EUR_USD:absent"]
            assert _FORBIDDEN_TRADE_TOKENS_RE.search(md) is None

        asyncio.run(_run())


class TestSectionPopulated:
    def test_populated_prose_and_stamps(self) -> None:
        reading = compute_technical_reading(_scenario_bars(), asset="EUR_USD", now_utc=_NOW)
        assert reading is not None

        async def _run() -> None:
            with patch.object(ta_mod, "assess_technical_reading", AsyncMock(return_value=reading)):
                md, sources = await _section_technical_methodology(
                    session=AsyncMock(), asset="EUR_USD"
                )
            assert "Lecture technique" in md
            assert "Élan H1" in md
            assert any(s.startswith("polygon:EUR_USD@") for s in sources)
            assert "methodologie:ADR-113" in sources
            assert _FORBIDDEN_TRADE_TOKENS_RE.search(md) is None

        asyncio.run(_run())


class TestWiring:
    def test_wired_into_build_data_pool(self) -> None:
        src = inspect.getsource(dp_mod.build_data_pool)
        assert "_section_technical_methodology" in src
        assert '"technical_methodology"' in src

    def test_wired_into_build_asset_data_only(self) -> None:
        src = inspect.getsource(dp_mod.build_asset_data_only)
        assert "_section_technical_methodology" in src
