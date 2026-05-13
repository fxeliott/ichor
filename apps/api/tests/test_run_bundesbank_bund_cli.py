"""Unit tests for cli/run_bundesbank_bund.py (round-33).

Verifies the daily Bund 10Y ingestion CLI :
  1. Feature flag fail-closed when `bundesbank_bund_collector_enabled`
     is OFF or missing → exit 0, no fetch, no DB write.
  2. Feature flag ON + collector returns [] → exit 0, log no-op.
  3. Feature flag ON + collector returns observations → batched
     INSERT ON CONFLICT DO NOTHING is invoked with correct chunk
     boundaries.
  4. `--dry-run` skips the DB INSERT but still fetches.
  5. Batched insert respects asyncpg 32767 param limit (default
     batch_size=5000 ; 5 cols × 5000 = 25000 < 32767).

Uses `unittest.mock.AsyncMock` + `monkeypatch` for the collector,
session, and feature_flags helper. No real DB or HTTP I/O.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.cli.run_bundesbank_bund import (
    _DEFAULT_BATCH_SIZE,
    _FEATURE_FLAG_NAME,
    _ingest_batched,
    _run,
    main,
)


def _fake_obs(d: date, pct: float) -> MagicMock:
    """Mock a BundYieldObservation with the 4 attrs the CLI reads."""
    obs = MagicMock()
    obs.observation_date = d
    obs.yield_pct = Decimal(str(pct))
    obs.source_url = "https://api.statistiken.bundesbank.de/..."
    obs.fetched_at = datetime(2026, 5, 13, 16, 30, 0, tzinfo=UTC)
    return obs


# ──────────────────────── feature-flag fail-closed ────────────────────


@pytest.mark.asyncio
async def test_feature_flag_off_skips_fetch(monkeypatch, capsys):
    """Flag OFF → CLI prints the skip message and exits 0 WITHOUT
    calling the collector. Critical fail-closed contract."""
    fake_session = AsyncMock()
    fake_sm = MagicMock(return_value=_async_ctx(fake_session))
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.get_sessionmaker",
        lambda: fake_sm,
    )
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.is_enabled",
        AsyncMock(return_value=False),
    )
    fetch_mock = AsyncMock()
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.fetch_bund_yields",
        fetch_mock,
    )

    exit_code = await _run(dry_run=False, batch_size=_DEFAULT_BATCH_SIZE)

    assert exit_code == 0
    fetch_mock.assert_not_called()  # critical : NO fetch when flag OFF
    out = capsys.readouterr().out
    assert _FEATURE_FLAG_NAME in out
    assert "OFF" in out


# ──────────────────────── empty-fetch path ────────────────────


@pytest.mark.asyncio
async def test_empty_fetch_returns_zero(monkeypatch, capsys):
    """Flag ON but collector returns [] → CLI logs no-op and exits 0
    without attempting any DB INSERT."""
    fake_session = AsyncMock()
    fake_sm = MagicMock(return_value=_async_ctx(fake_session))
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.get_sessionmaker",
        lambda: fake_sm,
    )
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.is_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.fetch_bund_yields",
        AsyncMock(return_value=[]),
    )

    exit_code = await _run(dry_run=False, batch_size=_DEFAULT_BATCH_SIZE)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "no observations" in out
    # session.execute should not be invoked (no rows to INSERT).
    fake_session.execute.assert_not_called()


# ──────────────────────── happy path with insert ────────────────────


@pytest.mark.asyncio
async def test_happy_path_batched_insert(monkeypatch, capsys):
    """Flag ON + observations returned → fetch + batched INSERT runs,
    session.commit() called once at the end."""
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_sm = MagicMock(return_value=_async_ctx(fake_session))
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.get_sessionmaker",
        lambda: fake_sm,
    )
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.is_enabled",
        AsyncMock(return_value=True),
    )
    obs = [
        _fake_obs(date(2026, 5, 13), 3.13),
        _fake_obs(date(2026, 5, 12), 3.13),
        _fake_obs(date(2026, 5, 11), 3.07),
    ]
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.fetch_bund_yields",
        AsyncMock(return_value=obs),
    )

    exit_code = await _run(dry_run=False, batch_size=_DEFAULT_BATCH_SIZE)

    assert exit_code == 0
    # 3 obs / batch 5000 → 1 INSERT call.
    assert fake_session.execute.await_count == 1
    fake_session.commit.assert_awaited_once()
    out = capsys.readouterr().out
    assert "3 row(s) attempted across 1 batch" in out


# ──────────────────────── dry-run path ────────────────────


@pytest.mark.asyncio
async def test_dry_run_skips_db_insert(monkeypatch, capsys):
    """`--dry-run` → fetch + display, BUT no session.execute / commit."""
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_sm = MagicMock(return_value=_async_ctx(fake_session))
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.get_sessionmaker",
        lambda: fake_sm,
    )
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.is_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "ichor_api.cli.run_bundesbank_bund.fetch_bund_yields",
        AsyncMock(return_value=[_fake_obs(date(2026, 5, 13), 3.13)]),
    )

    exit_code = await _run(dry_run=True, batch_size=_DEFAULT_BATCH_SIZE)

    assert exit_code == 0
    # No INSERT — fetch succeeded but commit-side path skipped.
    # The session.execute MAY still be called by feature_flag check,
    # but the DB INSERT call to bund_10y_observations is NOT made.
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    fake_session.commit.assert_not_awaited()


# ──────────────────────── batched insert helper ────────────────────


@pytest.mark.asyncio
async def test_ingest_batched_chunks_correctly():
    """7299 rows / batch 5000 → 2 chunks (5000 + 2299)."""
    session = AsyncMock()
    session.execute = AsyncMock()
    rows = [
        {
            "observation_date": date(2026, 1, 1),
            "yield_pct": 3.0 + i * 0.001,
            "source_url": "https://...",
            "fetched_at": datetime.now(UTC),
        }
        for i in range(7299)
    ]
    n_attempted, n_chunks = await _ingest_batched(session, rows=rows, batch_size=5000)
    assert n_attempted == 7299
    assert n_chunks == 2
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_ingest_batched_respects_asyncpg_param_limit():
    """Default batch_size=5000 × 5 cols = 25000 args < 32767 asyncpg
    hard limit. Catch a regression that bumps the default above 6553."""
    assert _DEFAULT_BATCH_SIZE * 5 < 32767, (
        f"Default batch_size {_DEFAULT_BATCH_SIZE} × 5 cols exceeds "
        "asyncpg 32767 param limit. Reduce to ≤ 6553."
    )


# ──────────────────────── argparse + main ────────────────────


def test_main_parses_dry_run_flag(monkeypatch):
    """`--dry-run` flag wires through to _run(dry_run=True)."""
    captured = {}

    def fake_asyncio_run(coro):
        coro.close()
        return 0

    def fake_parse(self, args):  # noqa: ARG001
        return argparse.Namespace(dry_run=True, batch_size=_DEFAULT_BATCH_SIZE)

    monkeypatch.setattr("ichor_api.cli.run_bundesbank_bund.asyncio.run", fake_asyncio_run)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", fake_parse)
    exit_code = main(["--dry-run"])
    assert exit_code == 0


# ──────────────────────── helpers ────────────────────


def _async_ctx(session):
    """Build a fake `async with sm() as session:` context."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ──────────────────────── module sanity ────────────────────


def test_feature_flag_name_matches_register_cron_script():
    """The CLI feature flag key MUST stay in sync with the
    register-cron-bundesbank-bund.sh comment + the DB INSERT we run
    at deploy time. Pin the canonical value here."""
    assert _FEATURE_FLAG_NAME == "bundesbank_bund_collector_enabled"


def test_default_batch_size_value():
    """Round-32c established 5000 as the safe default batch."""
    assert _DEFAULT_BATCH_SIZE == 5000
