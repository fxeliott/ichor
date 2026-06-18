"""S02 socle round-8 — persist_market_data + persist_polygon_bars race-safety.

These two helpers were the last check-then-insert persist paths (SELECT existing
→ Python skip → per-row session.add → per-asset commit). Unlike their round-5
siblings they DID carry a per-asset try/except, but the in-Python skip was still
the only dedup, so two overlapping polls could both pass the skip and the second
trip the backing unique constraint (uq_market_data_asset_date_source / 0003 ;
uq_polygon_asset_ts / 0006) → an IntegrityError that rolled back and LOST the
whole asset's batch, including the non-conflicting rows. Both are now an atomic
``INSERT ... ON CONFLICT (cols) DO NOTHING`` via ``_bulk_insert_ignore_conflicts``,
kept PER ASSET so a row tripping an OHLC check still only fails its own asset.

No live-Postgres fixture exists (conftest stubs the session), so the real
on-conflict round-trip is a deploy-time guarantee. These tests cover what is
unit-testable: per-asset statement fan-out, the statement shape (ON CONFLICT ...
DO NOTHING against the right table), intra-asset de-dup, and the explicit
``id`` (UUID) the bulk pg_insert must supply (ORM default=uuid4 is not applied).
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from uuid import UUID

import pytest
from ichor_api.collectors.market_data import MarketDataPoint
from ichor_api.collectors.persistence import persist_market_data, persist_polygon_bars
from ichor_api.collectors.polygon import PolygonBar
from sqlalchemy.dialects import postgresql

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _CaptureSession:
    """AsyncSession stub that captures executed statements (never raises)."""

    def __init__(self, rowcount: int) -> None:
        self.executed: list[object] = []
        self.commits = 0
        self._rowcount = rowcount

    async def execute(self, stmt: object) -> _FakeResult:
        self.executed.append(stmt)
        return _FakeResult(self._rowcount)

    async def commit(self) -> None:
        self.commits += 1


def _compiled(stmt: object) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).upper()


def _md(asset: str, day: date_type, source: str = "stooq") -> MarketDataPoint:
    return MarketDataPoint(
        asset=asset,
        bar_date=day,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
        source=source,
        fetched_at=_NOW,
    )


def _pg(asset: str, ts: datetime) -> PolygonBar:
    return PolygonBar(
        asset=asset,
        ticker="C:EURUSD",
        bar_ts=ts,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100,
        vwap=1.4,
        transactions=10,
    )


# ── persist_market_data ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_market_data_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await persist_market_data(s, [])
    assert inserted == 0
    assert s.executed == []
    assert s.commits == 0


@pytest.mark.asyncio
async def test_market_data_emits_on_conflict_and_explicit_id() -> None:
    s = _CaptureSession(rowcount=1)
    inserted = await persist_market_data(s, [_md("EUR_USD", date_type(2026, 6, 2))])
    assert inserted == 1
    assert s.commits == 1
    assert len(s.executed) == 1
    stmt = s.executed[0]
    compiled = _compiled(stmt)
    assert "INSERT INTO MARKET_DATA" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled
    # market_data.id has no DB server_default → the bulk insert must supply it.
    params = stmt.compile(dialect=postgresql.dialect()).params
    assert isinstance(params["id_m0"], UUID)


@pytest.mark.asyncio
async def test_market_data_one_statement_per_asset() -> None:
    # Per-asset fan-out preserves OHLC-failure isolation: each asset is its own
    # ON CONFLICT statement, so a bad row in one asset cannot drop another's.
    s = _CaptureSession(rowcount=1)
    inserted = await persist_market_data(
        s,
        [
            _md("EUR_USD", date_type(2026, 6, 2)),
            _md("XAU_USD", date_type(2026, 6, 2)),
        ],
    )
    assert inserted == 2  # 1 per asset (stub rowcount)
    assert len(s.executed) == 2
    assert s.commits == 2


@pytest.mark.asyncio
async def test_market_data_dedups_same_asset_date_source() -> None:
    # Two bars with the same (asset, bar_date, source) collapse to one VALUES
    # row — Postgres rejects a duplicate arbiter within one batch.
    s = _CaptureSession(rowcount=1)
    d = date_type(2026, 6, 2)
    await persist_market_data(s, [_md("EUR_USD", d), _md("EUR_USD", d)])
    compiled = _compiled(s.executed[0])
    assert compiled.count("%(BAR_DATE") == 1


# ── persist_polygon_bars ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polygon_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await persist_polygon_bars(s, [])
    assert inserted == 0
    assert s.executed == []
    assert s.commits == 0


@pytest.mark.asyncio
async def test_polygon_emits_on_conflict_and_explicit_id() -> None:
    s = _CaptureSession(rowcount=1)
    inserted = await persist_polygon_bars(s, [_pg("EUR_USD", _NOW)])
    assert inserted == 1
    assert s.commits == 1
    assert len(s.executed) == 1
    stmt = s.executed[0]
    compiled = _compiled(stmt)
    assert "INSERT INTO POLYGON_INTRADAY" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled
    params = stmt.compile(dialect=postgresql.dialect()).params
    assert isinstance(params["id_m0"], UUID)


@pytest.mark.asyncio
async def test_polygon_one_statement_per_asset() -> None:
    s = _CaptureSession(rowcount=1)
    inserted = await persist_polygon_bars(
        s,
        [
            _pg("EUR_USD", datetime(2026, 6, 2, 13, 0, tzinfo=UTC)),
            _pg("GBP_USD", datetime(2026, 6, 2, 13, 0, tzinfo=UTC)),
        ],
    )
    assert inserted == 2
    assert len(s.executed) == 2
    assert s.commits == 2


@pytest.mark.asyncio
async def test_polygon_dedups_same_asset_ts() -> None:
    s = _CaptureSession(rowcount=1)
    ts = datetime(2026, 6, 2, 13, 0, tzinfo=UTC)
    await persist_polygon_bars(s, [_pg("EUR_USD", ts), _pg("EUR_USD", ts)])
    compiled = _compiled(s.executed[0])
    assert compiled.count("%(BAR_TS") == 1
