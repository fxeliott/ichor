"""Pure tests for the content-validity classifier (S03 freshness monitor).

`classify_content` closes the Kalshi silent-death blind spot: rows arriving
(freshness GREEN) but every value NULL/degenerate. Catches the NULL class
(Kalshi yes_price) and the all-same-value class (GDELT tone=0.0 incident).
"""

from __future__ import annotations

import pytest
from ichor_api.services.collector_freshness import classify_content


def test_insufficient_sample_never_flags() -> None:
    # Below min_sample we cannot tell dead from quiet → never flag.
    assert classify_content(sample_size=5, non_null=0, distinct=0) == "insufficient_sample"
    assert classify_content(sample_size=19, non_null=0, distinct=0) == "insufficient_sample"


def test_zero_sample_short_circuits_before_division() -> None:
    # sample_size=0 must return before the non_null/sample_size division
    # (guards against ZeroDivisionError on an empty recent window).
    assert classify_content(sample_size=0, non_null=0, distinct=0) == "insufficient_sample"


def test_kalshi_all_null_is_null_dead() -> None:
    # The exact Kalshi incident: 60 rows persisted, every yes_price NULL.
    assert classify_content(sample_size=60, non_null=0, distinct=0) == "null_dead"


def test_mostly_null_above_threshold_is_null_dead() -> None:
    # null_rate = 1 - 4/100 = 0.96 > 0.95
    assert classify_content(sample_size=100, non_null=4, distinct=4) == "null_dead"


def test_null_rate_exactly_at_threshold_is_ok() -> None:
    # null_rate = 0.95, the check is strict `> max_null_rate` → not dead;
    # distinct > 1 → not degenerate → ok.
    assert classify_content(sample_size=100, non_null=5, distinct=5) == "ok"


def test_gdelt_all_same_value_is_degenerate() -> None:
    # The GDELT tone=0.0-everywhere incident: non-null but a single distinct value.
    assert classify_content(sample_size=33, non_null=33, distinct=1) == "degenerate"


def test_healthy_varied_column_is_ok() -> None:
    assert classify_content(sample_size=60, non_null=60, distinct=40) == "ok"
    # a few legitimate NULLs (below threshold) + variety → still ok
    assert classify_content(sample_size=60, non_null=55, distinct=30) == "ok"


def test_custom_thresholds_respected() -> None:
    # Stricter null tolerance flags a column the default would pass.
    assert (
        classify_content(sample_size=100, non_null=80, distinct=50, max_null_rate=0.1)
        == "null_dead"
    )
    # Lower min_sample lets a small sample be judged.
    assert classify_content(sample_size=8, non_null=0, distinct=0, min_sample=5) == "null_dead"


# ───────────────────── Catalog binding (silent-death of the monitor) ────────
# The content sweep emits on metric_name 'collector_content_degraded'. If no
# AlertDef binds that metric, check_metric matches nothing → the monitor built
# to catch silent value-rot is ITSELF silently dead (S03 residual-gap audit
# 2026-06-19, third twin of FRED_SYNTHETIC_SILENT / FRED_SERIES_SILENT). These
# guards make a missing/renamed binding a red test, not a silent prod gap.


def test_catalog_has_collector_content_degraded_alert() -> None:
    from ichor_api.alerts.catalog import BY_CODE

    alert = BY_CODE["COLLECTOR_CONTENT_DEGRADED"]
    assert alert.metric_name == "collector_content_degraded"
    assert alert.severity == "warning"
    bound = [d for d in BY_CODE.values() if d.metric_name == "collector_content_degraded"]
    assert bound, "no AlertDef bound to the emitted 'collector_content_degraded' metric"


# Every metric_name the data-freshness CLI emits MUST resolve to >= 1 AlertDef,
# else evaluate_metric returns [] and that whole sweep dies silently. Pinning
# the full set generalizes the per-twin guards so a NEW sweep that forgets its
# AlertDef is caught at once (this is exactly how the 3 twins each slipped).
_FRESHNESS_EMITTED_METRICS = (
    "collector_age_ratio",
    "collector_absent",
    "rss_silent_feeds",
    "fred_series_silent",
    "fred_synthetic_silent",
    "collector_content_degraded",
)


@pytest.mark.parametrize("metric_name", _FRESHNESS_EMITTED_METRICS)
def test_every_freshness_sweep_metric_is_bound(metric_name: str) -> None:
    from ichor_api.alerts.catalog import BY_CODE

    bound = [d for d in BY_CODE.values() if d.metric_name == metric_name]
    assert bound, f"no AlertDef bound to emitted metric '{metric_name}' → sweep dies silently"


# ───────────────────── Runtime sweep + schema coherence ─────────────────────


class _ContentStubResult:
    def __init__(self, triple: tuple[int, int, int]) -> None:
        self._triple = triple

    def first(self) -> tuple[int, int, int]:
        return self._triple


class _ContentStubSession:
    """Returns a (count, non_null, distinct) triple per probed table, matched
    by the table name embedded in the SQL text the sweep issues."""

    def __init__(self, by_table: dict[str, tuple[int, int, int]]) -> None:
        self._by_table = by_table
        self.metric_calls: list[float] = []

    async def execute(self, stmt: object, params: object = None) -> _ContentStubResult:
        sql = str(stmt)
        for table, triple in self._by_table.items():
            if f"FROM {table}" in sql:
                return _ContentStubResult(triple)
        return _ContentStubResult((0, 0, 0))


@pytest.mark.asyncio
async def test_sweep_content_validity_classifies_degraded_columns(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The runtime SQL sweep (not just the pure classifier) must flag the
    Kalshi-NULL and GDELT-degenerate classes and pass them to check_metric."""
    from datetime import UTC, datetime

    from ichor_api.cli import run_data_freshness_check as m

    captured: dict[str, object] = {}

    async def _fake_check_metric(session, *, metric_name, current_value, asset, extra_payload):  # type: ignore[no-untyped-def]
        captured["metric_name"] = metric_name
        captured["value"] = current_value
        captured["payload"] = extra_payload
        return [object()]  # 1 hit

    monkeypatch.setattr(m, "check_metric", _fake_check_metric)

    session = _ContentStubSession(
        {
            "kalshi_markets": (60, 0, 0),  # all-NULL → null_dead
            "manifold_markets": (60, 60, 40),  # healthy → ok
            "gdelt_events": (40, 40, 1),  # single value → degenerate
        }
    )
    degraded, n_alerts = await m._sweep_content_validity(session, now=datetime.now(UTC))  # type: ignore[arg-type]
    assert "kalshi_price:null_dead" in degraded
    assert "gdelt_tone:degenerate" in degraded
    assert all("manifold" not in d for d in degraded)  # healthy column not flagged
    assert n_alerts == 1
    assert captured["metric_name"] == "collector_content_degraded"
    assert captured["value"] == float(len(degraded))


def test_content_probe_columns_exist_on_their_tables() -> None:
    """A typo in a `_CONTENT_PROBES` column name would make the SQL fail at
    runtime (caught, logged, skipped) → a false-green where the probe never
    runs. Pin every probed (table, ts_col, value_col) against the real schema."""
    import ichor_api.models  # noqa: F401 — register all tables on Base.metadata
    from ichor_api.cli.run_data_freshness_check import _CONTENT_PROBES
    from ichor_api.models.base import Base

    tables = Base.metadata.tables
    for label, table, ts_col, value_col, _window, _min in _CONTENT_PROBES:
        assert table in tables, f"{label}: table '{table}' not in schema"
        cols = tables[table].columns
        assert ts_col in cols, f"{label}: ts column '{ts_col}' missing on {table}"
        assert value_col in cols, f"{label}: value column '{value_col}' missing on {table}"
