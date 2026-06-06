"""Tests for the Phase 1 A1 live_triggers feed (ADR-106 Strand E).

`_assemble_live_triggers` turns recent real data (economic releases with a
published actual, central-bank speeches, strong-tone news) into the
verdict's `live_triggers`. Pins: source→trigger_type/impact/source mapping,
most-recent-first ordering, cap-10 truncation, the ADR-017 description
guard (a headline containing BUY/SELL is skipped, never raised), the
10-char description floor, and fail-open per-source isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.session_verdict_builder import (
    _assemble_live_triggers,
    _clip_trigger_description,
    _try_build_live_trigger,
)

_NOW = datetime(2026, 6, 2, 18, 0, 0, tzinfo=UTC)


def _result(rows: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _econ(title: str, *, actual: str = "0.4%", forecast: str | None = "0.3%", mins_ago: int = 60):
    return SimpleNamespace(
        title=title,
        actual=actual,
        forecast=forecast,
        currency="USD",
        scheduled_at=_NOW - timedelta(minutes=mins_ago),
    )


def _cb(title: str, *, bank: str = "FOMC", speaker: str | None = "Powell", mins_ago: int = 120):
    return SimpleNamespace(
        central_bank=bank,
        speaker=speaker,
        title=title,
        published_at=_NOW - timedelta(minutes=mins_ago),
    )


def _news(
    title: str,
    *,
    tone: str = "positive",
    source: str = "Reuters",
    mins_ago: int = 30,
    url: str = "",
    summary: str = "",
):
    return SimpleNamespace(
        title=title,
        tone_label=tone,
        tone_score=0.92 if tone == "positive" else -0.92,
        source=source,
        published_at=_NOW - timedelta(minutes=mins_ago),
        url=url,
        summary=summary,
    )


def _session(econ: list, cb: list, news: list) -> MagicMock:
    s = MagicMock()
    s.execute = AsyncMock(side_effect=[_result(econ), _result(cb), _result(news)])
    return s


# ── _clip_trigger_description ──────────────────────────────────────────


def test_clip_returns_none_below_minimum():
    assert _clip_trigger_description("short") is None


def test_clip_normalises_whitespace_and_clamps():
    out = _clip_trigger_description("  CPI   release    today  ")
    assert out == "CPI release today"
    long = "x" * 500
    assert len(_clip_trigger_description(long)) == 200


# ── _try_build_live_trigger ────────────────────────────────────────────


def test_try_build_valid():
    t = _try_build_live_trigger(
        trigger_type="economic_release",
        description="CPI m/m — résultat 0.4% (consensus 0.3%)",
        fired_at_utc=_NOW,
        impact="tests_verdict",
        source="economic_events:USD",
    )
    assert t is not None
    assert t.trigger_type == "economic_release"
    assert t.impact == "tests_verdict"


def test_try_build_skips_adr017_token():
    # A real headline can contain SELL; the validator would raise — skip it.
    t = _try_build_live_trigger(
        trigger_type="news_headline",
        description="Stocks SELL off sharply on rate fears (tonalité négative)",
        fired_at_utc=_NOW,
        impact="tests_verdict",
        source="news:Reuters",
    )
    assert t is None


def test_try_build_skips_too_short():
    assert (
        _try_build_live_trigger(
            trigger_type="news_headline",
            description="hi",
            fired_at_utc=_NOW,
            impact="tests_verdict",
            source="news:x",
        )
        is None
    )


def test_try_build_normalises_naive_datetime():
    naive = datetime(2026, 6, 2, 17, 0, 0)  # no tzinfo
    t = _try_build_live_trigger(
        trigger_type="central_bank_speech",
        description="FOMC · Powell : Economic Outlook",
        fired_at_utc=naive,
        impact="tests_verdict",
        source="cb_speeches:FOMC",
    )
    assert t is not None
    assert t.fired_at_utc.tzinfo is not None


# ── _assemble_live_triggers ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assemble_maps_each_source():
    session = _session(
        [_econ("CPI m/m", mins_ago=60)],
        [_cb("Economic Outlook", mins_ago=120)],
        [_news("ECB meeting steadies the euro", mins_ago=30)],
    )
    triggers = await _assemble_live_triggers(session, asset="EUR_USD", now_utc=_NOW)
    by_type = {t.trigger_type: t for t in triggers}
    assert set(by_type) == {"economic_release", "central_bank_speech", "news_headline"}
    assert by_type["economic_release"].source == "economic_events:USD"
    assert by_type["central_bank_speech"].source == "cb_speeches:FOMC"
    assert by_type["news_headline"].source == "news:Reuters"
    assert all(t.impact == "tests_verdict" for t in triggers)


@pytest.mark.asyncio
async def test_assemble_sorts_most_recent_first():
    session = _session(
        [_econ("CPI m/m", mins_ago=60)],
        [_cb("Speech", mins_ago=120)],
        [_news("Euro climbs after ECB", mins_ago=30)],
    )
    triggers = await _assemble_live_triggers(session, asset="EUR_USD", now_utc=_NOW)
    fired = [t.fired_at_utc for t in triggers]
    assert fired == sorted(fired, reverse=True)
    assert triggers[0].trigger_type == "news_headline"  # 30 min ago = newest


@pytest.mark.asyncio
async def test_assemble_caps_at_ten():
    econ = [_econ(f"Release {i}", mins_ago=10 + i) for i in range(8)]
    cb = [_cb(f"Speech {i}", mins_ago=200 + i) for i in range(5)]
    session = _session(econ, cb, [])
    triggers = await _assemble_live_triggers(session, asset="EUR_USD", now_utc=_NOW)
    assert len(triggers) == 10  # 13 built, truncated to the cap-10 contract


@pytest.mark.asyncio
async def test_assemble_fails_open_per_source():
    # Economic query raises; CB + news must still produce triggers.
    s = MagicMock()
    s.execute = AsyncMock(
        side_effect=[
            RuntimeError("db blip"),
            _result([_cb("Speech", mins_ago=120)]),
            _result([_news("Euro firms after ECB", mins_ago=30)]),
        ]
    )
    triggers = await _assemble_live_triggers(s, asset="EUR_USD", now_utc=_NOW)
    types = {t.trigger_type for t in triggers}
    assert types == {"central_bank_speech", "news_headline"}


@pytest.mark.asyncio
async def test_assemble_skips_adr017_news_row():
    # On-asset (euro/ECB) so it passes the per-asset guard and actually
    # reaches the ADR-017 description check, which then skips it for "SELL".
    session = _session(
        [],
        [],
        [_news("Euro SELL-off deepens after ECB", tone="negative", mins_ago=10)],
    )
    triggers = await _assemble_live_triggers(session, asset="EUR_USD", now_utc=_NOW)
    assert triggers == []  # the only row tripped ADR-017 → skipped, no crash


@pytest.mark.asyncio
async def test_assemble_xau_only_usd_currency():
    # XAU_USD maps to ("USD",) — just assert the helper runs and maps source.
    session = _session([_econ("NFP", mins_ago=45)], [], [])
    triggers = await _assemble_live_triggers(session, asset="XAU_USD", now_utc=_NOW)
    assert len(triggers) == 1
    assert triggers[0].source == "economic_events:USD"


@pytest.mark.asyncio
async def test_assemble_filters_offasset_news():
    # S03/D2 honesty : strong-tone news must be filtered to the verdict's
    # asset. For EUR_USD only the euro/ECB headline is relevant ; a gold-only
    # headline must NOT contaminate the EUR_USD verdict (every asset used to
    # get the same global firehose).
    session = _session(
        [],
        [],
        [
            _news("ECB decision lifts the euro sharply", mins_ago=20),
            _news("Gold soars to a fresh record high", mins_ago=10),
        ],
    )
    triggers = await _assemble_live_triggers(session, asset="EUR_USD", now_utc=_NOW)
    news = [t for t in triggers if t.trigger_type == "news_headline"]
    assert len(news) == 1
    assert "euro" in news[0].description.lower()
