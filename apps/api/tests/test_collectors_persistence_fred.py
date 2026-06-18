"""S02 socle — persist_fred_observations idempotent upsert.

The former check-then-insert (SELECT existing → Python skip → per-row
session.add) was NOT atomic : two concurrent FRED polls could both pass the
skip and both INSERT the same (series_id, observation_date), tripping
uq_fred_series_date (migration 0005) → an uncaught IntegrityError that lost
the whole batch. The fix is a single ``INSERT ... ON CONFLICT (series_id,
observation_date) DO NOTHING`` (mirrors cli/run_eia_crude_stocks.py).

The apps/api suite has no live-Postgres fixture (conftest stubs the session),
so the REAL on-conflict round-trip is a deploy-time guarantee (the EIA/ECB/
Bund collectors already run this exact pattern in prod). These tests cover
what is unit-testable: the pure de-dup/row-builder and the statement shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from uuid import UUID

import pytest
from ichor_api.collectors.fred import FredObservation as FredObservationData
from ichor_api.collectors.persistence import (
    _build_fred_insert_rows,
    persist_fred_observations,
)
from sqlalchemy.dialects import postgresql

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


def _obs(series: str, day: str, value: float | None = 1.0) -> FredObservationData:
    return FredObservationData(
        series_id=series,
        observation_date=day,
        value=value,
        fetched_at=_NOW,
    )


# ── pure row-builder / de-dup helper ──────────────────────────────────


def test_build_rows_constructs_all_columns() -> None:
    parsed = [(_obs("DGS10", "2026-06-01", 4.2), date_type(2026, 6, 1))]
    rows = _build_fred_insert_rows(parsed, _NOW)
    assert len(rows) == 1
    row = rows[0]
    assert row["series_id"] == "DGS10"
    assert row["observation_date"] == date_type(2026, 6, 1)
    assert row["value"] == 4.2
    assert row["fetched_at"] == _NOW
    assert row["created_at"] == _NOW
    # id must be supplied explicitly (bulk pg_insert does not apply default=uuid4).
    assert isinstance(row["id"], UUID)


def test_build_rows_dedups_intra_batch_last_wins() -> None:
    # Two identical (series, date) — ON CONFLICT DO NOTHING cannot resolve a
    # duplicate arbiter within one VALUES batch, so the builder must collapse
    # them to one row (last occurrence wins).
    d = date_type(2026, 6, 1)
    parsed = [
        (_obs("DGS10", "2026-06-01", 4.2), d),
        (_obs("DGS10", "2026-06-01", 4.9), d),
    ]
    rows = _build_fred_insert_rows(parsed, _NOW)
    assert len(rows) == 1
    assert rows[0]["value"] == 4.9


def test_build_rows_keeps_distinct_pairs() -> None:
    parsed = [
        (_obs("DGS10", "2026-06-01"), date_type(2026, 6, 1)),
        (_obs("DGS10", "2026-06-02"), date_type(2026, 6, 2)),
        (_obs("DGS2", "2026-06-01"), date_type(2026, 6, 1)),
    ]
    rows = _build_fred_insert_rows(parsed, _NOW)
    assert len(rows) == 3
    assert all(isinstance(r["id"], UUID) for r in rows)
    # all ids unique
    assert len({r["id"] for r in rows}) == 3


def test_build_rows_preserves_none_value() -> None:
    parsed = [(_obs("DGS10", "2026-06-01", None), date_type(2026, 6, 1))]
    rows = _build_fred_insert_rows(parsed, _NOW)
    assert rows[0]["value"] is None


# ── persist_fred_observations (stub session) ──────────────────────────


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _CaptureSession:
    """AsyncSession stub that captures the executed statement(s)."""

    def __init__(self, rowcount: int) -> None:
        self.executed: list[object] = []
        self.commits = 0
        self._rowcount = rowcount

    async def execute(self, stmt: object) -> _FakeResult:
        self.executed.append(stmt)
        return _FakeResult(self._rowcount)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_persist_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await persist_fred_observations(s, [])
    assert inserted == 0
    assert s.executed == []
    assert s.commits == 0


@pytest.mark.asyncio
async def test_persist_emits_on_conflict_do_nothing() -> None:
    s = _CaptureSession(rowcount=2)
    inserted = await persist_fred_observations(
        s, [_obs("DGS10", "2026-06-01"), _obs("DGS2", "2026-06-01")]
    )
    assert inserted == 2  # rowcount from the (stubbed) driver
    assert s.commits == 1
    assert len(s.executed) == 1
    compiled = str(s.executed[0].compile(dialect=postgresql.dialect())).upper()
    assert "INSERT INTO FRED_OBSERVATIONS" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled


@pytest.mark.asyncio
async def test_persist_skips_bad_dates() -> None:
    s = _CaptureSession(rowcount=1)
    inserted = await persist_fred_observations(
        s, [_obs("DGS10", "not-a-date"), _obs("DGS2", "2026-06-01")]
    )
    # one good row reaches the upsert (stub rowcount=1) ; the bad-date row is
    # dropped by the fromisoformat guard before the statement is built.
    assert inserted == 1
    assert len(s.executed) == 1


@pytest.mark.asyncio
async def test_persist_all_bad_dates_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await persist_fred_observations(s, [_obs("DGS10", "xxxx")])
    assert inserted == 0
    assert s.executed == []  # nothing parsed → no statement, no commit
    assert s.commits == 0


@pytest.mark.asyncio
async def test_persist_zero_rowcount_is_not_overridden() -> None:
    # rowcount 0 = "all rows conflicted" — must be reported as 0, NOT
    # silently replaced by len(rows) (the fallback is only for None/-1).
    s = _CaptureSession(rowcount=0)
    inserted = await persist_fred_observations(s, [_obs("DGS10", "2026-06-01")])
    assert inserted == 0


@pytest.mark.asyncio
async def test_persist_negative_rowcount_falls_back_to_len() -> None:
    # Some drivers report -1 for rowcount on INSERT ... ON CONFLICT.
    s = _CaptureSession(rowcount=-1)
    inserted = await persist_fred_observations(
        s, [_obs("DGS10", "2026-06-01"), _obs("DGS2", "2026-06-01")]
    )
    assert inserted == 2  # fell back to len(rows)
