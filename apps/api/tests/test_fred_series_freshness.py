"""Per-series FRED freshness sweep — S02 socle audit (2026-06-18).

`fred_observations` holds dozens of series but the global `fred` FreshnessSpec
only checks the whole-table MAX(fetched_at), which VIX_LIVE keeps perpetually
fresh — so a daily series that dies (DGS2, a Treasury yield…) is invisible.
`_sweep_fred_series` closes that per-series silent hole. These tests pin the
detection logic + the daily-series derivation so the hole can't silently return.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import ichor_api.cli.run_data_freshness_check as dfc
import pytest
from ichor_api.alerts.catalog import BY_CODE

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


class _Result:
    def __init__(self, rows: list[tuple[str, datetime]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, datetime]]:
        return self._rows


class _Session:
    """Minimal async session double — only `execute(...).all()` is exercised."""

    def __init__(self, rows: list[tuple[str, datetime]]) -> None:
        self._rows = rows

    async def execute(self, *_a: object, **_k: object) -> _Result:
        return _Result(self._rows)


# ── derivation ────────────────────────────────────────────────────────


def test_daily_series_excludes_monthly_series() -> None:
    daily = set(dfc._FRED_DAILY_SERIES)
    # Monthly series MUST NOT be per-series-monitored (a 5-day window would
    # false-positive between their monthly prints). The curated allowlist
    # excludes them by construction — NOT a registry subtraction (the FRED age
    # registry is incomplete: CPIAUCSL is monthly yet absent from it, which is
    # exactly why the allowlist approach is used).
    assert "CPIAUCSL" not in daily, "monthly CPI must NOT be per-series-monitored"
    assert "PAYEMS" not in daily
    assert "UNRATE" not in daily
    # Daily business-day series are present.
    assert "DGS2" in daily
    assert "DGS10" in daily
    assert "VIXCLS" in daily


def test_daily_series_keys_fit_alerts_asset_column() -> None:
    assert dfc._FRED_DAILY_SERIES, "derived daily set must be non-empty"
    assert all(len(s) <= 16 for s in dfc._FRED_DAILY_SERIES)


def test_catalog_has_fred_series_silent_alert() -> None:
    alert = BY_CODE["FRED_SERIES_SILENT"]
    assert alert.metric_name == "fred_series_silent"
    assert alert.severity == "warning"


# ── sweep logic ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_fresh_no_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dfc, "check_metric", AsyncMock(return_value=[]))
    rows = [(s, _NOW - timedelta(days=1)) for s in dfc._FRED_DAILY_SERIES]
    silent, n_alerts = await dfc._sweep_fred_series(_Session(rows), now=_NOW)
    assert silent == []
    assert n_alerts == 0


@pytest.mark.asyncio
async def test_one_stale_series_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    cm = AsyncMock(return_value=[object()])  # one hit persisted
    monkeypatch.setattr(dfc, "check_metric", cm)
    fresh = _NOW - timedelta(days=1)
    rows = [(s, fresh) for s in dfc._FRED_DAILY_SERIES]
    # DGS2 froze 10 days ago while everything else stayed fresh (the TGA class).
    rows = [(s, (_NOW - timedelta(days=10)) if s == "DGS2" else t) for s, t in rows]
    silent, n_alerts = await dfc._sweep_fred_series(_Session(rows), now=_NOW)
    assert silent == ["DGS2"]
    assert n_alerts == 1
    # Aggregated alert : metric_name + asset=None + payload lists the series.
    _, kwargs = cm.call_args
    assert kwargs["metric_name"] == "fred_series_silent"
    assert kwargs["asset"] is None
    assert "DGS2" in kwargs["extra_payload"]["silent_series"]


@pytest.mark.asyncio
async def test_absent_series_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dfc, "check_metric", AsyncMock(return_value=[]))
    # DGS10 has NO row at all (collector never wrote it) → absent → silent.
    rows = [(s, _NOW - timedelta(days=1)) for s in dfc._FRED_DAILY_SERIES if s != "DGS10"]
    silent, _ = await dfc._sweep_fred_series(_Session(rows), now=_NOW)
    assert "DGS10" in silent


@pytest.mark.asyncio
async def test_naive_timestamp_is_coerced_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dfc, "check_metric", AsyncMock(return_value=[]))
    # A naive (tz-less) recent timestamp must be treated as UTC, not crash.
    naive_recent = (_NOW - timedelta(days=1)).replace(tzinfo=None)
    rows = [(s, naive_recent) for s in dfc._FRED_DAILY_SERIES]
    silent, n_alerts = await dfc._sweep_fred_series(_Session(rows), now=_NOW)
    assert silent == []
    assert n_alerts == 0
