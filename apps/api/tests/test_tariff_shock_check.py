"""Tests for services/tariff_shock_check.py — TARIFF_SHOCK alert wiring."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from ichor_api.services import tariff_shock_check as svc


def _article(
    days_ago: int,
    title: str = "Trump tariff escalation hits China",
    tone: float = -2.5,
    *,
    today: date = date(2026, 5, 7),
) -> tuple[datetime, str, float]:
    seen = datetime.combine(today - timedelta(days=days_ago), datetime.min.time(), tzinfo=UTC)
    return (seen, title, tone)


def test_zscore_below_min_history_returns_none():
    z, mean, std = svc._zscore([5.0] * 10, 50.0)
    assert (z, mean, std) == (None, None, None)


def test_zscore_with_zero_std_returns_none_z():
    z, mean, std = svc._zscore([5.0] * 30, 5.0)
    assert z is None
    assert mean == 5.0
    assert std == 0.0


def test_zscore_textbook_count_spike():
    # 30 days of count ~ 5 per day, today = 50 → large z
    history = [5.0 + (i % 3 - 1) for i in range(30)]
    z, mean, std = svc._zscore(history, 50.0)
    assert z is not None and z > 10  # huge spike
    assert mean is not None
    assert std is not None and std > 0


def test_bucket_by_day_groups_correctly():
    today = date(2026, 5, 7)
    articles = [
        _article(0, today=today),  # today
        _article(0, "USTR launches Section 301 investigation", -3.0, today=today),
        _article(1, today=today),
        _article(2, today=today),
        _article(2, today=today),
        _article(40, today=today),  # outside 30d window — should be ignored
    ]
    today_count, history, n_today, tones, titles = svc._bucket_by_day(
        articles, today=today
    )
    assert today_count == 2
    assert n_today == 2
    assert len(tones) == 2
    assert len(titles) == 2
    # History has 30 daily buckets
    assert len(history) == svc.COUNT_ZSCORE_WINDOW_DAYS
    # Day -1 had 1 article, day -2 had 2 articles, others 0, day -40 ignored
    sorted_history_total = sum(history)
    assert sorted_history_total == 3


def test_bucket_by_day_caps_title_sample():
    today = date(2026, 5, 7)
    # 10 articles today — title_sample should be capped at _TITLE_SAMPLE_CAP
    articles = [_article(0, f"Tariff article #{i}", -2.0, today=today) for i in range(10)]
    today_count, _hist, _n_today, _tones, titles = svc._bucket_by_day(articles, today=today)
    assert today_count == 10
    assert len(titles) == svc._TITLE_SAMPLE_CAP
    # First 5 should be retained (insertion order)
    assert titles[0] == "Tariff article #0"
    assert titles[-1] == f"Tariff article #{svc._TITLE_SAMPLE_CAP - 1}"


@pytest.mark.asyncio
async def test_evaluate_no_articles_returns_graceful_noop(monkeypatch):
    """Empty DB → no alert, count=0, structured note."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_tariff_articles", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_tariff_shock(
        None, persist=True, today=date(2026, 5, 7)
    )
    assert result.today_count == 0
    # 30d of zero history is fine; std == 0 → z is None
    assert result.count_z is None
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_below_threshold_no_alert(monkeypatch):
    """Steady state ~5 articles/day with noise, today = 5 → z near 0 → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        out: list[tuple[datetime, str, float]] = []
        # 4-6 articles per day for past 30 days (noise to ensure std > 0)
        for d_ago in range(1, 31):
            for j in range(5 + (d_ago % 3 - 1)):
                out.append(_article(d_ago, f"hist art {d_ago}-{j}", -2.0, today=today))
        # 5 articles today → at the mean → z ~ 0
        for j in range(5):
            out.append(_article(0, f"today art {j}", -2.0, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_tariff_articles", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_tariff_shock(None, persist=True, today=today)
    assert result.count_z is not None
    assert result.count_z < svc.ALERT_COUNT_Z_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_count_spike_with_neutral_tone_no_alert(monkeypatch):
    """Count anomaly but tone not negative enough → no alert (combo gate)."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        out: list[tuple[datetime, str, float]] = []
        # baseline 2-4/day with noise (std > 0)
        for d_ago in range(1, 31):
            for j in range(2 + (d_ago % 3)):
                out.append(_article(d_ago, "hist art", -2.0, today=today))
        # Today: 50 articles but with neutral tone (-0.5, above floor)
        for j in range(50):
            out.append(_article(0, f"today art {j}", -0.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_tariff_articles", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_tariff_shock(None, persist=True, today=today)
    assert result.count_z is not None
    assert result.count_z >= svc.ALERT_COUNT_Z_FLOOR  # count anomaly present
    # avg_tone -0.5 is above the AVG_TONE_NEG_FLOOR (-1.5) → combo gate fails
    assert result.avg_tone_today is not None
    assert result.avg_tone_today > svc.AVG_TONE_NEG_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_alert_count_spike_and_negative_tone(monkeypatch):
    """Count anomaly AND negative tone → alert fired with proper source-stamp."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        out: list[tuple[datetime, str, float]] = []
        # baseline 2-4/day with noise (std > 0)
        for d_ago in range(1, 31):
            for j in range(2 + (d_ago % 3)):
                out.append(_article(d_ago, "hist art", -2.0, today=today))
        for j in range(50):
            out.append(
                _article(
                    0,
                    f"USTR Section 301 escalation #{j}",
                    -3.5,  # very negative
                    today=today,
                )
            )
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_tariff_articles", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_tariff_shock(None, persist=True, today=today)
    assert result.count_z is not None
    assert result.count_z >= svc.ALERT_COUNT_Z_FLOOR
    assert result.avg_tone_today is not None
    assert result.avg_tone_today <= svc.AVG_TONE_NEG_FLOOR
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "tariff_count_z"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "gdelt:tariff_filter"
    assert payload["today_count"] == 50
    assert payload["avg_tone_today"] is not None
    assert payload["avg_tone_today"] <= svc.AVG_TONE_NEG_FLOOR
    assert "tariff_keywords_used" in payload
    assert "tariff" in payload["tariff_keywords_used"]
    assert "section 301" in payload["tariff_keywords_used"]
    assert len(payload["title_sample"]) <= svc._TITLE_SAMPLE_CAP


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    """`persist=False` (CLI dry-run) MUST NOT touch the alert table even
    when both gates are crossed."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        out: list[tuple[datetime, str, float]] = []
        # baseline 2-4/day with noise (std > 0)
        for d_ago in range(1, 31):
            for j in range(2 + (d_ago % 3)):
                out.append(_article(d_ago, "hist art", -2.0, today=today))
        for j in range(50):
            out.append(_article(0, f"escalation {j}", -3.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_tariff_articles", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_tariff_shock(None, persist=False, today=today)
    # Both gates crossed but persist=False → no fire
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Single source of truth — bridge constant ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("TARIFF_SHOCK")
    assert cat.default_threshold == svc.ALERT_COUNT_Z_FLOOR
    assert cat.metric_name == "tariff_count_z"


def test_dataclass_shape():
    r = svc.TariffShockResult(
        today_count=50,
        baseline_mean=2.0,
        baseline_std=0.8,
        count_z=12.5,
        avg_tone_today=-3.5,
        n_history=30,
        n_articles_today=50,
        alert_fired=True,
        note="tariff today=50 baseline=2.00±0.80 count_z=+12.50 avg_tone=-3.50",
        title_sample=["USTR Section 301 escalation"],
    )
    d = asdict(r)
    expected = {
        "today_count",
        "baseline_mean",
        "baseline_std",
        "count_z",
        "avg_tone_today",
        "n_history",
        "n_articles_today",
        "alert_fired",
        "note",
        "title_sample",
    }
    assert set(d.keys()) == expected
    assert r.alert_fired is True


def test_tariff_keywords_includes_2026_macro_terms():
    """The 2026 tariff regime hinges on Section 301, IEEPA, and Section
    122 — verify those are in the filter list (post-SCOTUS Learning
    Resources v Trump pivot)."""
    keywords = set(svc.TARIFF_KEYWORDS)
    assert "section 301" in keywords
    assert "ieepa" in keywords
    assert "section 122" in keywords
    assert "ustr" in keywords
    assert "tariff" in keywords


def test_title_matches_tariff_rejects_substring_collisions():
    """The original SQL-only filter false-positives on `ustr` inside
    `industrial`/`industry`/`industrie`. The Python post-filter MUST
    reject those."""
    # False positives — ustr appears as substring inside other words
    assert not svc._title_matches_tariff(
        "U.S. Cement Industry Economic Forecast Reflects War with Iran"
    )
    assert not svc._title_matches_tariff("ACT Govt Workers Vote For Industrial Action")
    assert not svc._title_matches_tariff(
        "India Auto Industry Faces Risks from Middle East Conflict After Record Sales"
    )
    assert not svc._title_matches_tariff(
        "Trawell Co., risultati 2025 in linea con il piano industriale"
    )
    # `art program` should not match `smart program` / `start programme`
    assert not svc._title_matches_tariff("New smart program launched in Q3")
    assert not svc._title_matches_tariff("Restart programmed for next quarter")


def test_title_matches_tariff_accepts_legit_tariff_titles():
    """Real tariff news SHOULD match."""
    assert svc._title_matches_tariff("Trump tariffs hit China steel exports")
    assert svc._title_matches_tariff("USTR Launches Section 301 Investigation Against EU")
    assert svc._title_matches_tariff(
        "Trade war escalates as Beijing retaliates with reciprocal tariffs"
    )
    assert svc._title_matches_tariff("IEEPA pivot: Section 122 BOP surcharge takes effect")
    assert svc._title_matches_tariff("Liberation Day tariff anniversary marks one year")
    assert svc._title_matches_tariff("New import duties announced on Mexican avocados")
    assert svc._title_matches_tariff("Import duty hike to 25% on Chinese EVs")
    assert svc._title_matches_tariff("ART program signed with India this morning")
    assert svc._title_matches_tariff("US protectionism reaches new heights in Q2 2026")
    assert svc._title_matches_tariff("Trade-war risk premium spikes on US10Y")


def test_title_matches_tariff_case_sensitivity_for_acronyms():
    """USTR / IEEPA / ART program are case-SENSITIVE in the regex —
    the lowercase form only appears as substring inside other words."""
    # Uppercase acronym form — must match
    assert svc._title_matches_tariff("USTR statement on Section 301")
    assert svc._title_matches_tariff("IEEPA invalidation upheld by SCOTUS")
    # Lowercase substring form — must NOT match
    assert not svc._title_matches_tariff("Industrial output up 2% in March")
    assert not svc._title_matches_tariff("ieepa-style overreach criticized in editorial")
