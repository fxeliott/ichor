"""r126 ADR-099 §Impl(r126) — tempo threshold recalibration tests.

Covers :
  - `_percentile` linear-interp on edge cases (empty, single, even, odd)
  - `_compute_thresholds` ordering + clamping
  - `recalibrate_tempo_thresholds` end-to-end with stub session
  - Skip-when-sample-too-small invariant
  - ValueError on invalid window_days / min_sample_days

Pure-Python tests — no live DB. The SQL aggregation in `_daily_ranges_bp`
is exercised indirectly via the stub session pattern (we substitute the
function call ; the actual SQL is exercised by the live-DB cron smoke test
on Hetzner, not the CI pytest gate).
"""

from __future__ import annotations

from typing import Any

import pytest
from ichor_api.services import tempo_recalibration as svc
from ichor_api.services.tempo_recalibration import (
    DEFAULT_MIN_SAMPLE_DAYS,
    DEFAULT_RECALIBRATION_ASSETS,
    DEFAULT_WINDOW_DAYS,
    _compute_thresholds,
    _percentile,
    recalibrate_tempo_thresholds,
)

# ─────────────── _percentile pure-fn ────────────────


def test_percentile_empty_returns_zero() -> None:
    """Empty input → 0.0 (degenerate but doesn't crash)."""
    assert _percentile([], 50.0) == 0.0
    assert _percentile([], 90.0) == 0.0


def test_percentile_single_value() -> None:
    """Single value → that value for any p."""
    assert _percentile([42.0], 50.0) == 42.0
    assert _percentile([42.0], 90.0) == 42.0
    assert _percentile([42.0], 0.0) == 42.0


def test_percentile_two_value_linear_interp() -> None:
    """Two values → linear interpolation."""
    # p25 of [10, 20] = 10 + 0.25 * (20 - 10) = 12.5
    assert _percentile([10.0, 20.0], 25.0) == pytest.approx(12.5)
    assert _percentile([10.0, 20.0], 50.0) == pytest.approx(15.0)
    assert _percentile([10.0, 20.0], 75.0) == pytest.approx(17.5)


def test_percentile_p0_returns_min_p100_returns_max() -> None:
    sorted_xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(sorted_xs, 0.0) == 1.0
    assert _percentile(sorted_xs, 100.0) == 5.0


def test_percentile_matches_canonical_quartiles() -> None:
    """[1..9] → p25=3 / p50=5 / p75=7 (canonical quartile positions)."""
    xs = [float(i) for i in range(1, 10)]
    assert _percentile(xs, 25.0) == pytest.approx(3.0)
    assert _percentile(xs, 50.0) == pytest.approx(5.0)
    assert _percentile(xs, 75.0) == pytest.approx(7.0)


# ─────────────── _compute_thresholds ────────────────


def test_compute_thresholds_monotonic_ordering() -> None:
    """The 4 thresholds must be ordered breakout >= active >= trending >=
    range_bound >= 0 (matches the DB CHECK constraints)."""
    ranges = [float(i) for i in range(1, 101)]  # 1..100
    out = _compute_thresholds("EUR_USD", ranges_bp=ranges, window_days=90)
    assert out.breakout_bp >= out.active_bp >= out.trending_bp >= out.range_bound_bp >= 0
    # p90, p75, p50, p25 of 1..100 with linear-interp
    assert out.breakout_bp == pytest.approx(90.1, abs=0.5)
    assert out.active_bp == pytest.approx(75.25, abs=0.5)
    assert out.trending_bp == pytest.approx(50.5, abs=0.5)
    assert out.range_bound_bp == pytest.approx(25.75, abs=0.5)


def test_compute_thresholds_carries_metadata() -> None:
    out = _compute_thresholds("GBP_USD", ranges_bp=[10.0, 20.0, 30.0], window_days=42)
    assert out.asset == "GBP_USD"
    assert out.sample_size == 3
    assert out.window_days == 42


def test_compute_thresholds_clamps_negative_to_zero() -> None:
    """Defense-in-depth : if a negative slips through (shouldn't), it's
    clamped to 0 before returning. The DB CHECK has nonneg too."""
    out = _compute_thresholds("EUR_USD", ranges_bp=[-5.0, 10.0, 20.0], window_days=90)
    assert out.range_bound_bp >= 0


def test_compute_thresholds_all_equal_values() -> None:
    """When every range is identical, all 4 percentiles equal that value.
    The clamping shouldn't break this degenerate case."""
    out = _compute_thresholds("XAU_USD", ranges_bp=[42.0] * 30, window_days=90)
    assert out.breakout_bp == 42.0
    assert out.active_bp == 42.0
    assert out.trending_bp == 42.0
    assert out.range_bound_bp == 42.0


# ─────────────── recalibrate_tempo_thresholds end-to-end ────────────────


class _StubSession:
    """Mimic the slice of AsyncSession this service uses : `add()` +
    `flush()` + `execute()`. We don't call `commit()` (the CLI does)."""

    def __init__(self, daily_ranges_by_asset: dict[str, list[float]]) -> None:
        self._daily_ranges = daily_ranges_by_asset
        self.added: list[Any] = []
        self.flushed: int = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1

    async def execute(self, stmt: Any, params: Any = None) -> Any:  # noqa: ARG002
        raise AssertionError("_StubSession.execute should not be called in these tests")

    async def rollback(self) -> None:  # pragma: no cover
        pass


@pytest.fixture
def stub_daily_ranges(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[float]]:
    """Replace `_daily_ranges_bp` with a dict-lookup stub so tests don't
    need a Postgres connection."""
    ranges: dict[str, list[float]] = {}

    async def _fake(
        session: Any,
        asset: str,
        *,
        window_days: int,  # noqa: ARG001
    ) -> list[float]:
        return ranges.get(asset, [])

    monkeypatch.setattr(svc, "_daily_ranges_bp", _fake)
    return ranges


@pytest.mark.asyncio
async def test_recalibrate_inserts_thresholds_for_assets_with_enough_data(
    stub_daily_ranges: dict[str, list[float]],
) -> None:
    """Happy path : 2 assets with enough samples each get one row inserted."""
    stub_daily_ranges["EUR_USD"] = [float(i) for i in range(20, 80)]  # 60 samples
    stub_daily_ranges["GBP_USD"] = [float(i) for i in range(30, 100)]  # 70 samples

    session = _StubSession(stub_daily_ranges)
    results = await recalibrate_tempo_thresholds(
        session,  # type: ignore[arg-type]
        assets=("EUR_USD", "GBP_USD"),
        window_days=90,
        min_sample_days=7,
    )

    assert len(results) == 2
    assert all(r.status == "inserted" for r in results)
    assert len(session.added) == 2
    # session.flush() called once per asset (early CHECK detection).
    assert session.flushed == 2

    eur = next(r for r in results if r.asset == "EUR_USD")
    assert eur.thresholds is not None
    assert eur.thresholds.window_days == 90
    assert eur.thresholds.sample_size == 60


@pytest.mark.asyncio
async def test_recalibrate_skips_assets_with_insufficient_samples(
    stub_daily_ranges: dict[str, list[float]],
) -> None:
    """Sample size below min_sample_days → status=skipped, no row added."""
    stub_daily_ranges["EUR_USD"] = [float(i) for i in range(20, 80)]  # 60 samples
    stub_daily_ranges["XAU_USD"] = [10.0, 20.0, 30.0]  # 3 samples — too small

    session = _StubSession(stub_daily_ranges)
    results = await recalibrate_tempo_thresholds(
        session,  # type: ignore[arg-type]
        assets=("EUR_USD", "XAU_USD"),
        window_days=90,
        min_sample_days=7,
    )

    statuses = {r.asset: r.status for r in results}
    assert statuses == {"EUR_USD": "inserted", "XAU_USD": "skipped"}

    xau = next(r for r in results if r.asset == "XAU_USD")
    assert xau.thresholds is None
    assert xau.reason is not None and "sample_size" in xau.reason
    assert xau.sample_size == 3

    # Only EUR_USD made it into session.added.
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_recalibrate_dry_run_skips_db_writes(
    stub_daily_ranges: dict[str, list[float]],
) -> None:
    """dry_run=True : compute + return results, but session.add() never
    called (so the cron CLI can safely smoke-test in production)."""
    stub_daily_ranges["EUR_USD"] = [float(i) for i in range(20, 80)]

    session = _StubSession(stub_daily_ranges)
    results = await recalibrate_tempo_thresholds(
        session,  # type: ignore[arg-type]
        assets=("EUR_USD",),
        window_days=90,
        min_sample_days=7,
        dry_run=True,
    )

    assert len(results) == 1
    assert results[0].status == "inserted"
    assert results[0].thresholds is not None
    # No DB writes in dry_run mode.
    assert session.added == []
    assert session.flushed == 0


@pytest.mark.asyncio
async def test_recalibrate_empty_asset_returns_skipped(
    stub_daily_ranges: dict[str, list[float]],
) -> None:
    """Asset with zero bars in the window → skipped with sample_size=0."""
    # Note : EUR_USD intentionally not added to stub_daily_ranges.
    session = _StubSession(stub_daily_ranges)
    results = await recalibrate_tempo_thresholds(
        session,  # type: ignore[arg-type]
        assets=("EUR_USD",),
    )
    assert results[0].status == "skipped"
    assert results[0].sample_size == 0


@pytest.mark.asyncio
async def test_recalibrate_rejects_invalid_window_days(
    stub_daily_ranges: dict[str, list[float]],
) -> None:
    """window_days < 7 violates the DB CHECK floor — service raises early."""
    session = _StubSession(stub_daily_ranges)
    with pytest.raises(ValueError, match="window_days"):
        await recalibrate_tempo_thresholds(
            session,  # type: ignore[arg-type]
            assets=("EUR_USD",),
            window_days=3,
        )


@pytest.mark.asyncio
async def test_recalibrate_rejects_invalid_min_sample_days(
    stub_daily_ranges: dict[str, list[float]],
) -> None:
    session = _StubSession(stub_daily_ranges)
    with pytest.raises(ValueError, match="min_sample_days"):
        await recalibrate_tempo_thresholds(
            session,  # type: ignore[arg-type]
            assets=("EUR_USD",),
            min_sample_days=0,
        )


# ─────────────── Constants exposed for r127 frontend reuse ────────────────


def test_default_assets_match_r125_frontend_hardcoded_set() -> None:
    """The 5 frontend-shipped priority assets that the r125 sessionPulse.ts
    TEMPO_THRESHOLDS_BY_ASSET covers. Adding USD_CAD here without first
    shipping the /briefing/[asset] D1 6th route would create a r127 wire-
    side mismatch — gated by this test."""
    assert DEFAULT_RECALIBRATION_ASSETS == (
        "EUR_USD",
        "GBP_USD",
        "XAU_USD",
        "SPX500_USD",
        "NAS100_USD",
    )


def test_default_window_days_is_90() -> None:
    assert DEFAULT_WINDOW_DAYS == 90


def test_default_min_sample_days_is_7() -> None:
    assert DEFAULT_MIN_SAMPLE_DAYS == 7


# ─────────────── Drift-guard sentinels (code-reviewer Y-2 + Y-3) ────────────────


def test_percentile_duplication_drift_guard() -> None:
    """The `_percentile` helper is duplicated between
    `services.tempo_recalibration` and `services.hourly_volatility`. The
    inline justification is doctrine-#2 strict scope (no premature shared
    module). This drift-guard test imports BOTH implementations and pins
    that they return identical outputs on a fixed sample — mechanically
    catches divergence until a 3rd occurrence triggers extraction to a
    shared module (Rule of Three)."""
    from ichor_api.services.hourly_volatility import _percentile as hv_percentile
    from ichor_api.services.tempo_recalibration import _percentile as tr_percentile

    sample = [1.5, 3.7, 8.2, 12.4, 20.1, 31.0, 44.8, 60.5, 89.3, 142.9]
    for p in (0.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0, 100.0):
        assert hv_percentile(sample, p) == tr_percentile(sample, p), (
            f"_percentile drift at p={p}: hourly_volatility vs "
            "tempo_recalibration must stay byte-identical"
        )

    # Empty + single-element + ties edge cases.
    assert hv_percentile([], 50.0) == tr_percentile([], 50.0)
    assert hv_percentile([42.0], 50.0) == tr_percentile([42.0], 50.0)
    assert hv_percentile([7.0, 7.0, 7.0], 25.0) == tr_percentile([7.0, 7.0, 7.0], 25.0)


def test_daily_ranges_bp_sql_pins_paris_tz_and_safety_filters() -> None:
    """Y-2 drift guard : the `_daily_ranges_bp` SQL is NOT exercised by
    `_StubSession` (which raises on .execute()), so a regression in the
    Paris TZ cast or the `day_open > 0` safety filter would slip past CI.
    String-match guard pins the load-bearing fragments — a future
    refactor that drops them must update this test in the same commit."""
    import re

    src = open(
        "src/ichor_api/services/tempo_recalibration.py",
        encoding="utf-8",
    ).read()
    # Paris TZ cast — the semantic alignment with frontend sessionPulse.ts.
    assert re.search(r"bar_ts\s+AT\s+TIME\s+ZONE\s+'Europe/Paris'", src, flags=re.IGNORECASE), (
        "_daily_ranges_bp must group by Paris-date (semantic match with sessionPulse.ts)"
    )
    # day_open > 0 — division-safety pre-check.
    assert "day_open > 0" in src, "_daily_ranges_bp must filter day_open > 0"
    # ARRAY_AGG("open" ORDER BY bar_ts ASC) — the "open of the Paris-day"
    # semantic.
    assert re.search(
        r'ARRAY_AGG\("open"\s+ORDER\s+BY\s+bar_ts\s+ASC\)', src, flags=re.IGNORECASE
    ), "_daily_ranges_bp must take open from earliest bar of the Paris-day"
    # Bind params for asset + cutoff (SQL injection guard).
    assert ":asset" in src and ":cutoff" in src, (
        "_daily_ranges_bp must use bind params, not string interpolation"
    )


def test_max_daily_range_bp_constant_is_50k() -> None:
    """MF-2 sanity clamp constant — pins the upper bound that protects
    `Numeric(8, 2)` from corrupt-bar overflow. Any future loosening must
    explicitly bump this test (forcing re-justification)."""
    from ichor_api.services.tempo_recalibration import _MAX_DAILY_RANGE_BP

    assert _MAX_DAILY_RANGE_BP == 50_000.0


@pytest.mark.asyncio
async def test_compute_thresholds_clamp_bottom_up_handles_negative_input(
    stub_daily_ranges: dict[str, list[float]],  # noqa: ARG001
) -> None:
    """MF-1 regression : the previous top-down clamp let a `-5.0`-induced
    `p50 < p25` slip through to `p75 < p25`. Post-fix, even with a single
    negative range mixed in, the 4 thresholds stay monotonic."""
    out = _compute_thresholds(
        "EUR_USD",
        ranges_bp=[-5.0, -3.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        window_days=90,
    )
    assert out.breakout_bp >= out.active_bp >= out.trending_bp >= out.range_bound_bp
    assert out.range_bound_bp >= 0
