"""S02 socle round 5 — synthetic-FRED-source freshness sweep.

~10 collectors write into fred_observations under synthetic series_id prefixes
(BLS_/ECB_/ZQ_/AAII_/BOE_/WIKI_PV_/TREASURY_AUC_/DTS_) and were covered by
NEITHER the global `fred` spec nor `_sweep_fred_series` — so a silent death was
invisible. These pin the new per-source sweep + its scheduled-coverage contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import ichor_api.cli.run_data_freshness_check as m
import pytest

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


class _Result:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _StubSession:
    def __init__(self, max_by_pattern: dict[str, object]) -> None:
        self._max = max_by_pattern

    async def execute(self, _stmt: object, params: dict | None = None) -> _Result:
        return _Result(self._max.get((params or {}).get("pat")))


@pytest.fixture(autouse=True)
def _no_alert_write(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_check_metric(*_a: object, **_kw: object) -> list:
        return []

    monkeypatch.setattr(m, "check_metric", _fake_check_metric)


def test_tiers_cover_scheduled_synthetic_sources() -> None:
    labels = {label for label, _, _ in m._FRED_SYNTHETIC_TIERS}
    # Every SCHEDULED synthetic collector must be monitored.
    assert {
        "bls",
        "ecb_sdmx",
        "dts_treasury",
        "cme_zq",
        "aaii",
        "boe_iadb",
        "wiki_pv",
        "treasury_auc",
    } <= labels
    # The UNSCHEDULED ones must NOT be monitored (no timer → permanent false alert).
    assert not ({"defillama", "crypto_fng", "binance_funding"} & labels)
    for _, pattern, window in m._FRED_SYNTHETIC_TIERS:
        assert pattern.startswith(
            ("BLS_", "ECB_", "DTS_", "ZQ_", "AAII_", "BOE_", "WIKI_PV_", "TREASURY_AUC_")
        )
        assert window.total_seconds() > 0


@pytest.mark.asyncio
async def test_absent_synthetic_source_flagged() -> None:
    # No prefix has any row (collector never wrote) → every source is silent.
    session = _StubSession({})
    silent, _ = await m._sweep_fred_synthetic_sources(session, now=_NOW)
    assert set(silent) == {label for label, _, _ in m._FRED_SYNTHETIC_TIERS}


@pytest.mark.asyncio
async def test_fresh_synthetic_source_not_flagged() -> None:
    fresh = {pat: _NOW - timedelta(hours=1) for _, pat, _ in m._FRED_SYNTHETIC_TIERS}
    session = _StubSession(fresh)
    silent, _ = await m._sweep_fred_synthetic_sources(session, now=_NOW)
    assert silent == []


@pytest.mark.asyncio
async def test_stale_beyond_window_flagged() -> None:
    by_pat = {pat: _NOW - timedelta(hours=1) for _, pat, _ in m._FRED_SYNTHETIC_TIERS}
    by_pat["BLS_%"] = _NOW - timedelta(days=50)  # past the 45-day BLS window
    session = _StubSession(by_pat)
    silent, _ = await m._sweep_fred_synthetic_sources(session, now=_NOW)
    assert silent == ["bls"]


@pytest.mark.asyncio
async def test_naive_timestamp_coerced_to_utc() -> None:
    # A naive DB max() (no tzinfo) within window must NOT be flagged.
    naive_fresh = {pat: datetime(2026, 6, 18, 11, 0) for _, pat, _ in m._FRED_SYNTHETIC_TIERS}
    session = _StubSession(naive_fresh)
    silent, _ = await m._sweep_fred_synthetic_sources(session, now=_NOW)
    assert silent == []


def test_catalog_has_fred_synthetic_silent_alert() -> None:
    """Regression guard (S02 socle residual audit 2026-06-19) : the synthetic
    sweep emits on metric_name 'fred_synthetic_silent' [run_data_freshness_check
    :355]. There MUST be an AlertDef bound to that metric — otherwise
    evaluate_metric matches nothing, returns [], and the 8 synthetic collectors
    die SILENTLY. The autouse `_no_alert_write` fixture above stubs check_metric,
    so the sweep tests stay green even with no AlertDef — this catalog-level
    assertion is the missing mirror of the twin `fred_series_silent` (which had
    its own catalog test ; the synthetic twin did not)."""
    from ichor_api.alerts.catalog import BY_CODE

    alert = BY_CODE["FRED_SYNTHETIC_SILENT"]
    assert alert.metric_name == "fred_synthetic_silent"
    assert alert.severity == "warning"
    # The exact bug class : the emitted metric_name must resolve to >=1 AlertDef.
    bound = [d for d in BY_CODE.values() if d.metric_name == "fred_synthetic_silent"]
    assert bound, "no AlertDef bound to the emitted 'fred_synthetic_silent' metric"
