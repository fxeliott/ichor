"""S02 socle — _bulk_insert_ignore_conflicts + the converted persist_* helpers.

Round-5 extends the round-3 FRED race-safety fix to 10 sibling collector
persist_* helpers: the former check-then-insert (SELECT existing → Python skip
→ per-row session.add → commit) was NOT atomic and (unlike persist_market_data
/ persist_polygon_bars) had NO try/except, so two overlapping polls could both
pass the Python skip and the second trip an uncaught IntegrityError that lost
the whole batch. Each is now a single ``INSERT ... ON CONFLICT (cols) DO
NOTHING`` via the shared ``_bulk_insert_ignore_conflicts`` helper.

The apps/api suite has no live-Postgres fixture (conftest stubs the session),
so the REAL on-conflict round-trip is a deploy-time guarantee. These tests
cover what is unit-testable: the intra-batch de-dup, the statement shape
(ON CONFLICT ... DO NOTHING against the right table), and that the row dicts
carry an explicit ``id`` (UUID) where the table has no DB server_default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from uuid import UUID

import pytest
from ichor_api.collectors.ai_gpr import AiGprObservation
from ichor_api.collectors.cboe_skew import CboeSkewObservation as CboeSkewObservationData
from ichor_api.collectors.cot import CotPosition as CotPositionData
from ichor_api.collectors.persistence import (
    _bulk_insert_ignore_conflicts,
    persist_cboe_skew_observations,
    persist_cot_positions,
    persist_gpr_observations,
)
from ichor_api.models import CboeSkewObservation, GprObservation
from sqlalchemy.dialects import postgresql

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


# ── stub session (mirrors test_collectors_persistence_fred.py) ─────────


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


def _compiled(stmt: object) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).upper()


# ── _bulk_insert_ignore_conflicts (the shared helper) ──────────────────


@pytest.mark.asyncio
async def test_bulk_helper_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await _bulk_insert_ignore_conflicts(
        s, GprObservation, [], conflict_cols=["observation_date"]
    )
    assert inserted == 0
    assert s.executed == []  # no rows → no statement
    assert s.commits == 0


@pytest.mark.asyncio
async def test_bulk_helper_dedups_intra_batch_last_wins() -> None:
    # Two rows with the same arbiter key — Postgres rejects a duplicate arbiter
    # within one VALUES batch, so the helper must collapse them to one row
    # (last occurrence wins) BEFORE building the statement.
    d = date_type(2026, 6, 1)
    rows = [
        {"observation_date": d, "skew_value": 130.0, "fetched_at": _NOW},
        {"observation_date": d, "skew_value": 145.0, "fetched_at": _NOW},
    ]
    s = _CaptureSession(rowcount=1)
    inserted = await _bulk_insert_ignore_conflicts(
        s, CboeSkewObservation, rows, conflict_cols=["observation_date"]
    )
    # rowcount from the stub (1) — the real driver reports actual inserts.
    assert inserted == 1
    assert s.commits == 1
    assert len(s.executed) == 1
    # The compiled statement carries exactly one VALUES row (the dedup collapsed
    # the duplicate arbiter). postgresql renders a 1-row insert without the
    # parameter-expanding "[POSTCOMPILE_...]" array marker.
    compiled = _compiled(s.executed[0])
    assert "INSERT INTO CBOE_SKEW_OBSERVATIONS" in compiled
    assert compiled.count("%(OBSERVATION_DATE") == 1


@pytest.mark.asyncio
async def test_bulk_helper_keeps_distinct_keys() -> None:
    rows = [
        {"observation_date": date_type(2026, 6, 1), "skew_value": 130.0, "fetched_at": _NOW},
        {"observation_date": date_type(2026, 6, 2), "skew_value": 131.0, "fetched_at": _NOW},
    ]
    s = _CaptureSession(rowcount=2)
    inserted = await _bulk_insert_ignore_conflicts(
        s, CboeSkewObservation, rows, conflict_cols=["observation_date"]
    )
    assert inserted == 2
    compiled = _compiled(s.executed[0])
    # two distinct arbiter keys → two VALUES rows
    assert compiled.count("%(OBSERVATION_DATE") == 2


@pytest.mark.asyncio
async def test_bulk_helper_compiles_on_conflict_do_nothing() -> None:
    rows = [{"observation_date": date_type(2026, 6, 1), "skew_value": 130.0, "fetched_at": _NOW}]
    s = _CaptureSession(rowcount=1)
    await _bulk_insert_ignore_conflicts(
        s, CboeSkewObservation, rows, conflict_cols=["observation_date"]
    )
    compiled = _compiled(s.executed[0])
    assert "INSERT INTO CBOE_SKEW_OBSERVATIONS" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled


@pytest.mark.asyncio
async def test_bulk_helper_negative_rowcount_falls_back_to_deduped_len() -> None:
    # Some drivers report -1 on INSERT ... ON CONFLICT → fall back to the
    # deduped length (here 2 distinct keys), NOT the raw input length (3).
    rows = [
        {"observation_date": date_type(2026, 6, 1), "skew_value": 130.0, "fetched_at": _NOW},
        {"observation_date": date_type(2026, 6, 1), "skew_value": 131.0, "fetched_at": _NOW},
        {"observation_date": date_type(2026, 6, 2), "skew_value": 132.0, "fetched_at": _NOW},
    ]
    s = _CaptureSession(rowcount=-1)
    inserted = await _bulk_insert_ignore_conflicts(
        s, CboeSkewObservation, rows, conflict_cols=["observation_date"]
    )
    assert inserted == 2  # deduped length, not 3


@pytest.mark.asyncio
async def test_bulk_helper_zero_rowcount_not_overridden() -> None:
    # rowcount 0 = "all rows conflicted" — must be reported as 0, NOT replaced
    # by the deduped length (the fallback is only for None/-1).
    rows = [{"observation_date": date_type(2026, 6, 1), "skew_value": 130.0, "fetched_at": _NOW}]
    s = _CaptureSession(rowcount=0)
    inserted = await _bulk_insert_ignore_conflicts(
        s, CboeSkewObservation, rows, conflict_cols=["observation_date"]
    )
    assert inserted == 0


# ── persist_gpr_observations (id=uuid4 supplied: no DB server_default) ──


def _gpr(day: date_type, value: float = 100.0) -> AiGprObservation:
    return AiGprObservation(observation_date=day, ai_gpr=value, fetched_at=_NOW)


@pytest.mark.asyncio
async def test_persist_gpr_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await persist_gpr_observations(s, [])
    assert inserted == 0
    assert s.executed == []
    assert s.commits == 0


@pytest.mark.asyncio
async def test_persist_gpr_emits_on_conflict_and_returns_rowcount() -> None:
    s = _CaptureSession(rowcount=2)
    inserted = await persist_gpr_observations(
        s, [_gpr(date_type(2026, 6, 1)), _gpr(date_type(2026, 6, 2))]
    )
    assert inserted == 2  # rowcount from the stub
    assert s.commits == 1
    assert len(s.executed) == 1
    compiled = _compiled(s.executed[0])
    assert "INSERT INTO GPR_OBSERVATIONS" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled


@pytest.mark.asyncio
async def test_persist_gpr_row_carries_explicit_id() -> None:
    # gpr_observations.id has NO DB server_default (migration 0005) — the bulk
    # pg_insert must supply id=uuid4() (ORM default=uuid4 is not applied).
    s = _CaptureSession(rowcount=1)
    await persist_gpr_observations(s, [_gpr(date_type(2026, 6, 1))])
    stmt = s.executed[0]
    # the bound multiparams expose the supplied id directly
    params = stmt.compile(dialect=postgresql.dialect()).params
    assert isinstance(params["id_m0"], UUID)


# ── persist_cot_positions (id=uuid4 supplied; market_code truncated [:16]) ──


def _cot(code: str, day: date_type) -> CotPositionData:
    return CotPositionData(
        report_date=day,
        market_code=code,
        market_name="GOLD",
        producer_net=1,
        swap_dealer_net=2,
        managed_money_net=3,
        other_reportable_net=4,
        non_reportable_net=5,
        open_interest=6,
        fetched_at=_NOW,
    )


@pytest.mark.asyncio
async def test_persist_cot_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    # also exercises the None-filter (persist_cot_positions drops None entries)
    inserted = await persist_cot_positions(s, [None])
    assert inserted == 0
    assert s.executed == []
    assert s.commits == 0


@pytest.mark.asyncio
async def test_persist_cot_emits_on_conflict_and_supplies_id() -> None:
    s = _CaptureSession(rowcount=1)
    inserted = await persist_cot_positions(s, [_cot("088691", date_type(2026, 6, 2)), None])
    assert inserted == 1
    assert s.commits == 1
    assert len(s.executed) == 1
    stmt = s.executed[0]
    compiled = _compiled(stmt)
    assert "INSERT INTO COT_POSITIONS" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled
    params = stmt.compile(dialect=postgresql.dialect()).params
    # cot_positions.id has no DB server_default → explicit UUID required
    assert isinstance(params["id_m0"], UUID)


@pytest.mark.asyncio
async def test_persist_cot_truncates_market_code_to_16() -> None:
    s = _CaptureSession(rowcount=1)
    await persist_cot_positions(s, [_cot("X" * 40, date_type(2026, 6, 2))])
    params = s.executed[0].compile(dialect=postgresql.dialect()).params
    assert params["market_code_m0"] == "X" * 16


# ── persist_cboe_skew_observations (NO id: DB server_default) ───────────


def _skew(day: date_type, value: float = 130.0) -> CboeSkewObservationData:
    return CboeSkewObservationData(observation_date=day, skew_value=value, fetched_at=_NOW)


@pytest.mark.asyncio
async def test_persist_skew_empty_short_circuits() -> None:
    s = _CaptureSession(rowcount=0)
    inserted = await persist_cboe_skew_observations(s, [])
    assert inserted == 0
    assert s.executed == []
    assert s.commits == 0


@pytest.mark.asyncio
async def test_persist_skew_emits_on_conflict_without_explicit_id() -> None:
    s = _CaptureSession(rowcount=2)
    inserted = await persist_cboe_skew_observations(
        s, [_skew(date_type(2026, 6, 1)), _skew(date_type(2026, 6, 2))]
    )
    assert inserted == 2
    assert s.commits == 1
    assert len(s.executed) == 1
    stmt = s.executed[0]
    compiled = _compiled(stmt)
    assert "INSERT INTO CBOE_SKEW_OBSERVATIONS" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO NOTHING" in compiled
    # cboe_skew rows do NOT carry an explicit id (the table has a DB
    # server_default gen_random_uuid(), and the ORM column also has
    # default=uuid4). We left id out of the row dict, so at COMPILE time the id
    # bind is unresolved (None) — the uuid4 is applied at execute time. This is
    # the marker distinguishing the no-explicit-id helpers from gpr/cot/gdelt,
    # which supply a concrete UUID at build time (see the gpr/cot tests).
    params = stmt.compile(dialect=postgresql.dialect()).params
    assert not any(isinstance(v, UUID) for v in params.values())


@pytest.mark.asyncio
async def test_persist_skew_dedups_duplicate_dates_to_one_row() -> None:
    # Same observation_date twice in one poll → the helper collapses to one
    # VALUES row (the ON CONFLICT arbiter cannot fire twice in a batch).
    s = _CaptureSession(rowcount=1)
    d = date_type(2026, 6, 1)
    await persist_cboe_skew_observations(s, [_skew(d, 130.0), _skew(d, 145.0)])
    compiled = _compiled(s.executed[0])
    assert compiled.count("%(OBSERVATION_DATE") == 1
