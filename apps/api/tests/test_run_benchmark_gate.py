"""Tests for ``cli.run_benchmark_gate`` (ADR-116, Chantier A slice-2).

Pure helpers (window math, apex-verdict derivation, dedup, render) are tested
directly; the DB read + orchestration are tested with a stubbed async session
(no Postgres). Numeric values are hand-computed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from ichor_api.cli.run_benchmark_gate import (
    _Bar,
    _build_samples,
    _load_cards,
    _parse_since,
    _session_date,
    card_verdict,
    clamp_conviction,
    dedup_latest_per_session,
    ny_window_utc,
    render_report,
    window_return_pct,
)
from ichor_api.models import SessionCardAudit
from ichor_api.services.benchmark_gate import VerdictOutcomeSample

# ───────────────────────── fixtures / builders ─────────────────────────

_LABELS_BEAR = ("crash_flush", "strong_bear", "mild_bear")
_LABELS_BULL = ("mild_bull", "strong_bull", "melt_up")


def _buckets(*, bull: float, bear: float) -> list[dict]:
    """7 canonical Pass-6 buckets; ``bull``/``bear`` mass split evenly across the
    three directional buckets, remainder on ``base``. sum(p) == 1.0."""
    base = round(1.0 - bull - bear, 10)
    out = [{"label": "base", "p": base, "magnitude_pips": [-5.0, 5.0], "mechanism": "range"}]
    for lbl in _LABELS_BEAR:
        out.append(
            {"label": lbl, "p": bear / 3, "magnitude_pips": [-50.0, -10.0], "mechanism": "x"}
        )
    for lbl in _LABELS_BULL:
        out.append({"label": lbl, "p": bull / 3, "magnitude_pips": [10.0, 50.0], "mechanism": "x"})
    return out


def _card(
    *,
    asset: str = "EUR_USD",
    day: int = 1,
    hour: int = 7,
    scenarios: list[dict] | None = None,
) -> SessionCardAudit:
    return SessionCardAudit(
        asset=asset,
        generated_at=datetime(2026, 5, day, hour, 0, tzinfo=UTC),
        session_type="pre_ny",
        scenarios=scenarios if scenarios is not None else _buckets(bull=0.7, bear=0.1),
    )


# ───────────────────────── pure helpers ─────────────────────────


class TestClampConviction:
    def test_clamps_and_passes_through(self) -> None:
        assert clamp_conviction(120.0) == 95.0
        assert clamp_conviction(-5.0) == 0.0
        assert clamp_conviction(72.0) == 72.0


class TestSessionDate:
    def test_morning_utc_is_same_paris_day(self) -> None:
        assert _session_date(datetime(2026, 6, 10, 7, 30, tzinfo=UTC)) == date(2026, 6, 10)

    def test_late_utc_still_same_paris_day(self) -> None:
        assert _session_date(datetime(2026, 6, 10, 21, 30, tzinfo=UTC)) == date(2026, 6, 10)


class TestParseSince:
    def test_parses_iso_date_to_utc_summer(self) -> None:
        # 2026-06-01 Paris midnight (+02:00) = 2026-05-31 22:00 UTC
        assert _parse_since("2026-06-01") == datetime(2026, 5, 31, 22, 0, tzinfo=UTC)


class TestNyWindowUtc:
    def test_summer_paris_to_utc(self) -> None:
        # 2026-06-10 summer (+02:00): 13:00 Paris = 11:00 UTC, 20:00 = 18:00 UTC
        start, end = ny_window_utc(date(2026, 6, 10))
        assert start == datetime(2026, 6, 10, 11, 0, tzinfo=UTC)
        assert end == datetime(2026, 6, 10, 18, 0, tzinfo=UTC)

    def test_winter_paris_to_utc(self) -> None:
        # 2026-01-15 winter (+01:00): 13:00 Paris = 12:00 UTC, 20:00 = 19:00 UTC
        start, end = ny_window_utc(date(2026, 1, 15))
        assert start == datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        assert end == datetime(2026, 1, 15, 19, 0, tzinfo=UTC)


def _bars(n: int, *, open_px: float, close_px: float) -> list[_Bar]:
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    out = [_Bar(ts=base + timedelta(minutes=i), open=open_px, close=open_px) for i in range(n)]
    if out:
        out[-1] = _Bar(ts=out[-1].ts, open=open_px, close=close_px)
    return out


class TestWindowReturnPct:
    def test_open_to_close_percent(self) -> None:
        # open 1.00 (first bar), close 1.02 (last bar) → +2.0 %
        assert window_return_pct(_bars(40, open_px=1.00, close_px=1.02)) == pytest.approx(2.0)

    def test_too_few_bars_is_none(self) -> None:
        assert window_return_pct(_bars(10, open_px=1.0, close_px=1.1)) is None

    def test_non_positive_open_is_none(self) -> None:
        assert window_return_pct(_bars(40, open_px=0.0, close_px=1.0)) is None


class TestCardVerdict:
    def test_bullish_buckets_give_up(self) -> None:
        direction, conviction = card_verdict(_card(scenarios=_buckets(bull=0.7, bear=0.1)))
        assert direction == "up"
        assert 0.0 < conviction <= 95.0

    def test_bearish_buckets_give_down(self) -> None:
        direction, _ = card_verdict(_card(scenarios=_buckets(bull=0.1, bear=0.7)))
        assert direction == "down"

    def test_balanced_buckets_give_neutral(self) -> None:
        direction, conviction = card_verdict(_card(scenarios=_buckets(bull=0.35, bear=0.35)))
        assert direction == "neutral"
        assert conviction == 0.0

    def test_malformed_scenarios_fallback_neutral(self) -> None:
        assert card_verdict(_card(scenarios=[])) == ("neutral", 0.0)
        assert card_verdict(_card(scenarios=[{"label": "base", "p": 1.0}])) == ("neutral", 0.0)


class TestDedup:
    def test_keeps_latest_per_asset_day(self) -> None:
        early = _card(day=2, hour=7)
        late = _card(day=2, hour=11)
        out = dedup_latest_per_session([early, late])
        assert len(out) == 1
        assert out[0].generated_at == late.generated_at

    def test_distinct_assets_and_days_kept(self) -> None:
        cards = [_card(asset="EUR_USD", day=1), _card(asset="XAU_USD", day=1), _card(day=2)]
        assert len(dedup_latest_per_session(cards)) == 3


class TestRenderReport:
    def _samples(self) -> list[VerdictOutcomeSample]:
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

    def test_sections_skip_note_and_no_trade_tokens(self) -> None:
        md = render_report(
            self._samples(),
            n_cards=8,
            n_skipped_no_window=2,
            cost_pct=0.02,
            dead_band_pct=0.05,
            train_size=3,
            test_size=2,
            step=2,
        )
        assert "## In-sample (diagnostic)" in md
        assert "## Walk-forward out-of-sample" in md
        assert "sans fenêtre NY 13h-20h exploitable" in md
        assert "BUY" not in md.upper()
        assert "SELL" not in md.upper()

    def test_thin_history_emits_honest_oos_note(self) -> None:
        md = render_report(
            self._samples(),
            n_cards=6,
            n_skipped_no_window=0,
            cost_pct=0.0,
            dead_band_pct=0.0,
            train_size=20,
            test_size=5,
            step=5,
        )
        assert "Historique insuffisant" in md


# ──────────────────── stubbed-session orchestration ────────────────────


class _StubScalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _StubResult:
    def __init__(self, *, scalars_rows: list | None = None, all_rows: list | None = None) -> None:
        self._scalars = scalars_rows or []
        self._all = all_rows or []

    def scalars(self) -> _StubScalars:
        return _StubScalars(self._scalars)

    def all(self) -> list:
        return self._all


class _StubSession:
    """First execute() → cards (scalars), every subsequent → window bars (all)."""

    def __init__(self, cards: list, bars: list) -> None:
        self._cards = cards
        self._bars = bars
        self._n = 0

    async def execute(self, _stmt: object) -> _StubResult:
        self._n += 1
        if self._n == 1:
            return _StubResult(scalars_rows=self._cards)
        return _StubResult(all_rows=self._bars)

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _BarsSession:
    """Every execute() → window bars (for _build_samples, which is given cards
    directly and only queries bars)."""

    def __init__(self, bars: list) -> None:
        self._bars = bars

    async def execute(self, _stmt: object) -> _StubResult:
        return _StubResult(all_rows=self._bars)


class _StubSessionmaker:
    def __init__(self, cards: list, bars: list) -> None:
        self._cards = cards
        self._bars = bars

    def __call__(self) -> _StubSession:
        return _StubSession(self._cards, self._bars)


async def test_load_cards_returns_scalars() -> None:
    cards = [_card(day=1)]
    out = await _load_cards(
        _StubSession(cards, []),  # type: ignore[arg-type]
        session_type="pre_ny",
        asset_filter=None,
        since=None,
    )
    assert out == cards


async def test_build_samples_joins_verdict_and_window() -> None:
    card = _card(asset="EUR_USD", day=1, scenarios=_buckets(bull=0.7, bear=0.1))
    bar_tuples = [
        (datetime(2026, 5, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=i), 1.10, 1.10)
        for i in range(40)
    ]
    bar_tuples[-1] = (bar_tuples[-1][0], 1.10, 1.122)  # close +2 %
    session = _BarsSession(bar_tuples)
    samples, n_cards, skipped = await _build_samples(session, [card])  # type: ignore[arg-type]
    assert n_cards == 1
    assert skipped == 0
    assert len(samples) == 1
    assert samples[0].predicted_direction == "up"
    assert samples[0].realized_return_pct == pytest.approx(2.0, rel=1e-3)


async def test_build_samples_skips_when_no_window_bars() -> None:
    card = _card(day=1)
    session = _BarsSession([])  # zero bars → skip
    samples, n_cards, skipped = await _build_samples(session, [card])  # type: ignore[arg-type]
    assert samples == []
    assert n_cards == 1
    assert skipped == 1


async def test_run_honest_when_no_samples(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ichor_api.cli import run_benchmark_gate as mod

    monkeypatch.setattr(mod, "get_sessionmaker", lambda: _StubSessionmaker([_card(day=1)], []))
    rc = await mod._run(
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
    assert "pas de rapport fabriqué" in out
