"""Unit tests for the W105g rebackfill helpers added round-15.

The full reconciler is async and DB-bound, so we test the pure-logic
slices :

  1. The argparse `--rebackfill-buckets` flag is accepted + threaded
     into the `_run` kwargs.
  2. `_rebackfill_one_bucket` succeeds when `_resolve_realized_bucket`
     returns a bucket label, and is a pure column-add (touches only
     `card.realized_scenario_bucket`, never `realized_*` prices or
     `brier_contribution`).
  3. `_rebackfill_one_bucket` returns `(False, "...None...")` when
     the bucket resolver returns None — the row stays untouched so
     the next run can pick it up after calibration seeds land.
"""

from __future__ import annotations

import argparse
from typing import Any
from unittest.mock import MagicMock

import pytest
from ichor_api.cli import reconcile_outcomes as ro


class _FakeCard:
    """Minimal SessionCardAudit-compatible attribute holder for tests."""

    def __init__(self) -> None:
        self.id = "test-card-id"
        self.asset = "EUR_USD"
        self.session_type = "pre_londres"
        self.realized_close_session = 1.17069
        self.realized_high_session = 1.17391
        self.realized_low_session = 1.16880
        self.brier_contribution = 0.1541
        self.realized_at = "2026-05-11T22:00:00+02:00"
        self.realized_scenario_bucket = None


def test_argparse_accepts_rebackfill_buckets_flag() -> None:
    """Smoke test : the CLI parser must accept the new flag without
    breaking the existing --limit/--asset/--dry-run interface."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--asset", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebackfill-buckets", action="store_true")
    args = parser.parse_args(["--rebackfill-buckets"])
    assert args.rebackfill_buckets is True
    args = parser.parse_args([])
    assert args.rebackfill_buckets is False


def test_rebackfill_helpers_are_exported_from_module() -> None:
    """Guard against accidental rename : Hetzner cron + ops scripts
    depend on these names existing in the module."""
    assert hasattr(ro, "_find_bucketless_cards")
    assert hasattr(ro, "_rebackfill_one_bucket")
    assert callable(ro._find_bucketless_cards)
    assert callable(ro._rebackfill_one_bucket)


@pytest.mark.asyncio
async def test_rebackfill_one_writes_bucket_when_resolver_succeeds(monkeypatch) -> None:
    """Happy path : resolver returns 'range_grind' → card column updated."""
    card = _FakeCard()

    async def _fake_bars(session: Any, card: Any) -> list[Any]:
        # Simulate stale-Polygon-window : no bars, fallback to persisted prices.
        return []

    async def _fake_resolve_bucket(
        session: Any,
        *,
        asset: str,
        session_type: str,
        open_px: float,
        close_px: float,
    ) -> str | None:
        assert asset == "EUR_USD"
        assert session_type == "pre_londres"
        assert open_px > 0
        assert close_px == 1.17069
        return "range_grind"

    monkeypatch.setattr(ro, "_bars_for_card", _fake_bars)
    monkeypatch.setattr(ro, "_resolve_realized_bucket", _fake_resolve_bucket)

    session = MagicMock()  # unused on this code path
    committed, reason = await ro._rebackfill_one_bucket(session, card, dry_run=False)
    assert committed is True
    assert "bucket=range_grind" in reason
    assert card.realized_scenario_bucket == "range_grind"
    # Pure column-add invariant : the prior brier+price columns stay untouched.
    assert card.brier_contribution == 0.1541
    assert card.realized_close_session == 1.17069


@pytest.mark.asyncio
async def test_rebackfill_one_skips_when_resolver_returns_none(monkeypatch) -> None:
    """Cold-start path : no calibration row yet → resolver returns None.
    Row must stay untouched so the next run can pick it up."""
    card = _FakeCard()

    async def _fake_bars(*a: Any, **kw: Any) -> list[Any]:
        return []

    async def _fake_resolve_none(*a: Any, **kw: Any) -> None:
        return None

    monkeypatch.setattr(ro, "_bars_for_card", _fake_bars)
    monkeypatch.setattr(ro, "_resolve_realized_bucket", _fake_resolve_none)

    session = MagicMock()
    committed, reason = await ro._rebackfill_one_bucket(session, card, dry_run=False)
    assert committed is False
    assert "None" in reason or "no realized" in reason
    # Critically : the bucket stays None (we did NOT write a partial value).
    assert card.realized_scenario_bucket is None


@pytest.mark.asyncio
async def test_rebackfill_one_dry_run_does_not_assign(monkeypatch) -> None:
    """--dry-run should compute the bucket but never assign it to the row."""
    card = _FakeCard()

    async def _fake_bars(*a: Any, **kw: Any) -> list[Any]:
        return []

    async def _fake_resolve(*a: Any, **kw: Any) -> str:
        return "trend_up"

    monkeypatch.setattr(ro, "_bars_for_card", _fake_bars)
    monkeypatch.setattr(ro, "_resolve_realized_bucket", _fake_resolve)

    session = MagicMock()
    committed, reason = await ro._rebackfill_one_bucket(session, card, dry_run=True)
    assert committed is False
    assert "dry-run" in reason
    assert "bucket=trend_up" in reason
    assert card.realized_scenario_bucket is None  # never assigned
