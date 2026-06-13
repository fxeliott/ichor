"""Tests for ``cli.run_benchmark_gate`` (ADR-116, Chantier A slice-2).

Pure transform helpers are tested directly; the DB read + orchestration are
tested with a stubbed async session (no Postgres, mirror of
``test_brier_aggregator_cli``). Numeric values are hand-computed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from ichor_api.cli.run_benchmark_gate import (
    VerdictRow,
    _load_verdict_rows,
    _parse_since,
    _run,
    _session_date,
    bias_to_direction,
    clamp_conviction,
    realized_return_pct,
    render_report,
    rows_to_samples,
)
from ichor_api.services.benchmark_gate import VerdictOutcomeSample

# ───────────────────────── pure helpers ─────────────────────────


class TestBiasToDirection:
    def test_maps_the_three_values(self) -> None:
        assert bias_to_direction("long") == "up"
        assert bias_to_direction("short") == "down"
        assert bias_to_direction("neutral") == "neutral"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown bias_direction"):
            bias_to_direction("flat")


class TestClampConviction:
    def test_clamps_above_cap(self) -> None:
        assert clamp_conviction(120.0) == 95.0

    def test_clamps_below_zero(self) -> None:
        assert clamp_conviction(-5.0) == 0.0

    def test_passes_through_in_band(self) -> None:
        assert clamp_conviction(72.0) == 72.0
        assert clamp_conviction(95.0) == 95.0


class TestRealizedReturnPct:
    def test_positive(self) -> None:
        # (1.105 / 1.10 - 1) * 100 = 0.4545...
        assert realized_return_pct(1.10, 1.105) == pytest.approx(0.45454545, rel=1e-6)

    def test_negative(self) -> None:
        # (0.99 / 1.00 - 1) * 100 = -1.0
        assert realized_return_pct(1.00, 0.99) == pytest.approx(-1.0)

    def test_zero_open_raises(self) -> None:
        with pytest.raises(ValueError, match="zero"):
            realized_return_pct(0.0, 1.0)


class TestSessionDate:
    def test_paris_date_of_morning_utc(self) -> None:
        # 2026-06-10 07:30 UTC = 09:30 Paris (summer) → date 2026-06-10
        gen = datetime(2026, 6, 10, 7, 30, tzinfo=UTC)
        assert _session_date(gen) == date(2026, 6, 10)

    def test_late_utc_still_same_paris_day(self) -> None:
        # 2026-06-10 21:30 UTC = 23:30 Paris → still 2026-06-10
        gen = datetime(2026, 6, 10, 21, 30, tzinfo=UTC)
        assert _session_date(gen) == date(2026, 6, 10)


class TestParseSince:
    def test_parses_iso_date_to_utc(self) -> None:
        # 2026-06-01 Paris midnight (summer, +02:00) = 2026-05-31 22:00 UTC
        out = _parse_since("2026-06-01")
        assert out == datetime(2026, 5, 31, 22, 0, tzinfo=UTC)


def _row(
    *,
    asset: str = "EUR_USD",
    day: int,
    hour: int = 8,
    bias: str = "long",
    conviction: float = 70.0,
    open_px: float | None = 1.10,
    close_px: float | None = 1.11,
) -> VerdictRow:
    return VerdictRow(
        asset=asset,
        generated_at=datetime(2026, 5, day, hour, 0, tzinfo=UTC),
        bias_direction=bias,
        conviction_pct=conviction,
        realized_open_session=open_px,
        realized_close_session=close_px,
    )


class TestRowsToSamples:
    def test_builds_sample_with_mapped_direction_and_return(self) -> None:
        samples, skipped = rows_to_samples([_row(day=1, bias="short", open_px=1.0, close_px=0.98)])
        assert skipped == 0
        assert len(samples) == 1
        s = samples[0]
        assert s.predicted_direction == "down"
        assert s.realized_return_pct == pytest.approx(-2.0)
        assert s.session_date == date(2026, 5, 1)

    def test_dedup_keeps_latest_per_asset_day(self) -> None:
        # two cards same asset+day → keep the later generated_at (conviction 80)
        rows = [
            _row(day=2, hour=7, conviction=60.0),
            _row(day=2, hour=11, conviction=80.0),
        ]
        samples, skipped = rows_to_samples(rows)
        assert len(samples) == 1
        assert samples[0].conviction_pct == 80.0

    def test_skips_unreconciled_rows(self) -> None:
        rows = [
            _row(day=1),  # reconciled
            _row(day=2, open_px=None, close_px=None),  # NULL realised
            _row(day=3, open_px=0.0, close_px=1.0),  # zero open
        ]
        samples, skipped = rows_to_samples(rows)
        assert len(samples) == 1
        assert skipped == 2

    def test_clamps_conviction_over_cap(self) -> None:
        samples, _ = rows_to_samples([_row(day=1, conviction=99.0)])
        assert samples[0].conviction_pct == 95.0

    def test_sorted_by_asset_then_date(self) -> None:
        rows = [
            _row(asset="XAU_USD", day=5),
            _row(asset="EUR_USD", day=9),
            _row(asset="EUR_USD", day=3),
        ]
        samples, _ = rows_to_samples(rows)
        keys = [(s.asset, s.session_date) for s in samples]
        assert keys == sorted(keys)


class TestRenderReport:
    def _samples(self) -> list[VerdictOutcomeSample]:
        # 6 EUR sessions, mixed — enough for an in-sample report; OOS depends on
        # the split sizes the caller passes.
        rows = [
            ("up", 70.0, 0.6),
            ("up", 65.0, -0.3),
            ("down", 55.0, -0.4),
            ("neutral", 0.0, 0.02),
            ("up", 80.0, 0.9),
            ("down", 60.0, 0.1),
        ]
        return [
            VerdictOutcomeSample(
                asset="EUR_USD",
                session_date=date(2026, 5, i + 1),
                predicted_direction=d,  # type: ignore[arg-type]
                conviction_pct=c,
                realized_return_pct=r,
            )
            for i, (d, c, r) in enumerate(rows)
        ]

    def test_in_sample_section_and_no_trade_tokens(self) -> None:
        md = render_report(
            self._samples(),
            n_skipped=2,
            cost_pct=0.02,
            dead_band_pct=0.05,
            train_size=3,
            test_size=2,
            step=2,
        )
        assert "## In-sample (diagnostic)" in md
        assert "## Walk-forward out-of-sample" in md
        assert "2 non réconcilié(s) ignoré(s)" in md
        # ADR-017 : not a single trade token in the whole rendered report
        assert "BUY" not in md.upper()
        assert "SELL" not in md.upper()

    def test_thin_history_emits_honest_oos_note(self) -> None:
        # train=20 + test=5 cannot fit 6 sessions → OOS None → honest note
        md = render_report(
            self._samples(),
            n_skipped=0,
            cost_pct=0.0,
            dead_band_pct=0.0,
            train_size=20,
            test_size=5,
            step=5,
        )
        assert "Historique insuffisant" in md


# ──────────────────── stubbed-session orchestration ────────────────────


class _StubResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows


class _StubSession:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    async def execute(self, _stmt: object) -> _StubResult:
        return _StubResult(self._rows)

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _StubSessionmaker:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def __call__(self) -> _StubSession:
        return _StubSession(self._rows)


async def test_load_verdict_rows_projects_tuples() -> None:
    rows = [
        ("EUR_USD", datetime(2026, 5, 1, 8, tzinfo=UTC), "long", 70.0, 1.10, 1.11),
    ]
    session = _StubSession(rows)
    out = await _load_verdict_rows(
        session,  # type: ignore[arg-type]
        session_type="pre_ny",
        asset_filter=None,
        since=None,
    )
    assert len(out) == 1
    assert out[0].asset == "EUR_USD"
    assert out[0].bias_direction == "long"
    assert out[0].realized_open_session == 1.10


async def test_run_renders_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        ("EUR_USD", datetime(2026, 5, d, 8, tzinfo=UTC), "long", 70.0, 1.10, 1.11)
        for d in range(1, 7)
    ]
    monkeypatch.setattr(
        "ichor_api.cli.run_benchmark_gate.get_sessionmaker",
        lambda: _StubSessionmaker(rows),
    )
    rc = await _run(
        session_type="pre_ny",
        asset_filter=None,
        since=None,
        cost_pct=0.0,
        dead_band_pct=0.0,
        train_size=3,
        test_size=2,
        step=2,
        output=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "# Benchmark gate" in out
    assert "BUY" not in out.upper()


async def test_run_honest_when_no_reconciled_samples(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        ("EUR_USD", datetime(2026, 5, 1, 8, tzinfo=UTC), "long", 70.0, None, None),
    ]
    monkeypatch.setattr(
        "ichor_api.cli.run_benchmark_gate.get_sessionmaker",
        lambda: _StubSessionmaker(rows),
    )
    rc = await _run(
        session_type="pre_ny",
        asset_filter=None,
        since=None,
        cost_pct=0.0,
        dead_band_pct=0.0,
        train_size=3,
        test_size=2,
        step=2,
        output=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Aucun verdict réconcilié" in out
    assert "pas de rapport fabriqué" in out
