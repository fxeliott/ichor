"""Tests for services/megacap_earnings_check.py — MEGACAP_EARNINGS_T-1 alert wiring."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import pytest
from ichor_api.services import megacap_earnings_check as svc


def test_megacap_tickers_complete_mag7():
    """All 7 Magnificent companies must be present (ordered by Q-end report)."""
    tickers = set(svc.MEGACAP_TICKERS)
    assert tickers == {"TSLA", "GOOGL", "MSFT", "META", "AAPL", "AMZN", "NVDA"}
    assert len(svc.MEGACAP_TICKERS) == 7


@pytest.mark.asyncio
async def test_evaluate_no_alerts_when_all_far_future(monkeypatch):
    """All tickers report >floor days away → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    def fake_fetch(ticker, *, today):
        # All earnings 30+ days away
        return today + timedelta(days=45)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_megacap_earnings(None, persist=True, today=today)
    assert result.tickers_with_date == 7
    assert result.tickers_alerting == 0
    assert result.alerts_fired == []
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_alert_t_minus_1(monkeypatch):
    """One ticker (NVDA) reports tomorrow → 1 alert fired with proper payload."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    def fake_fetch(ticker, *, today):
        if ticker == "NVDA":
            return today + timedelta(days=1)
        return today + timedelta(days=45)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_megacap_earnings(None, persist=True, today=today)
    assert result.tickers_alerting == 1
    assert result.alerts_fired == ["NVDA=T-1"]
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "megacap_t_minus_days"
    assert kw["asset"] == "NVDA"
    assert kw["current_value"] == 1.0
    payload = kw["extra_payload"]
    assert payload["source"] == "yfinance:earnings_calendar"
    assert payload["ticker"] == "NVDA"
    assert payload["days_to_event"] == 1
    assert payload["earnings_date"] == "2026-05-08"
    assert "fetched_at" in payload


@pytest.mark.asyncio
async def test_evaluate_fires_alert_t_minus_0(monkeypatch):
    """Earnings TODAY (T-0) should also fire."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 7, 30)

    def fake_fetch(ticker, *, today):
        if ticker in ("AAPL", "AMZN"):
            return today  # both report today
        return today + timedelta(days=30)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_megacap_earnings(None, persist=True, today=today)
    assert result.tickers_alerting == 2
    assert sorted(result.alerts_fired) == sorted(["AAPL=T-0", "AMZN=T-0"])
    assert len(captured) == 2
    metric_names = {c["metric_name"] for c in captured}
    assert metric_names == {"megacap_t_minus_days"}


@pytest.mark.asyncio
async def test_evaluate_skips_tickers_with_yfinance_failure(monkeypatch):
    """If yfinance returns None for a ticker, that ticker is silently skipped."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    def fake_fetch(ticker, *, today):
        if ticker == "NVDA":
            return None  # yfinance failure simulated
        return today + timedelta(days=2)  # T-2, just outside floor

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_megacap_earnings(None, persist=True, today=today)
    assert result.tickers_with_date == 6  # NVDA absent
    assert result.tickers_alerting == 0  # T-2 outside T-1 floor
    nvda_entry = next(t for t in result.per_ticker if t.ticker == "NVDA")
    assert nvda_entry.earnings_date is None
    assert nvda_entry.days_to_event is None
    assert "no future earnings" in nvda_entry.note


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    """`persist=False` (CLI dry-run) MUST NOT touch the alert table even
    when threshold is crossed."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    def fake_fetch(ticker, *, today):
        return today + timedelta(days=1) if ticker == "TSLA" else today + timedelta(days=45)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_megacap_earnings(None, persist=False, today=today)
    # Result still records the alert as "fired" for human-visible logging
    assert result.tickers_alerting == 1
    assert result.alerts_fired == ["TSLA=T-1"]
    # But check_metric was NOT called (CLI dry-run contract)
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_skips_past_earnings(monkeypatch):
    """If yfinance returns a date in the past (stale data), ticker is skipped.
    The _fetch helper should already filter this, but we test the integration."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    def fake_fetch(ticker, *, today):
        # Simulate the helper has filtered past dates → returns None for AAPL
        # which had an earnings date yesterday
        if ticker == "AAPL":
            return None
        return today + timedelta(days=45)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_megacap_earnings(None, persist=True, today=today)
    aapl_entry = next(t for t in result.per_ticker if t.ticker == "AAPL")
    assert aapl_entry.earnings_date is None
    assert aapl_entry.days_to_event is None
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Single source of truth — bridge constant ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("MEGACAP_EARNINGS_T_1")
    assert cat.default_threshold == svc.EARNINGS_PROXIMITY_FLOOR
    assert cat.metric_name == "megacap_t_minus_days"


def test_dataclass_shape():
    r = svc.MegacapEarningsResult(
        today=date(2026, 5, 7),
        tickers_evaluated=7,
        tickers_with_date=6,
        tickers_alerting=1,
        alerts_fired=["NVDA=T-1"],
        per_ticker=[
            svc.TickerEarnings(
                ticker="NVDA",
                earnings_date=date(2026, 5, 8),
                days_to_event=1,
            )
        ],
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "today",
        "tickers_evaluated",
        "tickers_with_date",
        "tickers_alerting",
        "alerts_fired",
        "per_ticker",
    }
    assert r.tickers_alerting == 1
    assert r.per_ticker[0].ticker == "NVDA"
    assert r.per_ticker[0].days_to_event == 1


def test_lookahead_days_reasonable():
    """LOOKAHEAD_DAYS must be > a reporting cycle quarter (~90d) for some
    tickers (NVDA reports ~3 weeks after the others) but not insanely far
    (avoid noise from announce-then-shift events)."""
    assert 30 <= svc.LOOKAHEAD_DAYS <= 120
