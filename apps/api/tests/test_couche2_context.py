"""Unit tests for the Couche-2 context loaders.

Tests verify the markdown rendering shape and the empty-window
sentinel behavior. Real DB integration tests live in
`test_couche2_persistence.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ichor_api.services.couche2_context import (
    Couche2Context,
    _truncate,
    build_cb_nlp_context,
    build_context_for_kind,
    build_economic_calendar_context,
    build_news_nlp_context,
    build_positioning_context,
    build_sentiment_context,
)


# ── helpers ─────────────────────────────────────────────────────────


def _mock_session(rows_per_query: list[list]) -> MagicMock:
    """Build an AsyncMock session whose .execute() returns rows in order.

    Each call to session.execute() pops one batch from `rows_per_query`.
    The returned object mimics SQLAlchemy's `.scalars().all()` chain.
    """
    session = MagicMock()
    session.execute = AsyncMock()

    def _build_result(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    side = [_build_result(rows) for rows in rows_per_query]
    session.execute.side_effect = side
    return session


def _now() -> datetime:
    return datetime.now(UTC)


# ── _truncate utility ────────────────────────────────────────────────


def test_truncate_short_returns_unchanged() -> None:
    assert _truncate("hello", 10) == "hello"


def test_truncate_long_appends_ellipsis() -> None:
    out = _truncate("a" * 50, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_truncate_none_returns_empty() -> None:
    assert _truncate(None) == ""


def test_truncate_strips_newlines() -> None:
    assert "\n" not in _truncate("line\nbreak\rhere", 100)


# ── build_cb_nlp_context ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cb_nlp_empty_window_returns_no_rows_sentinel() -> None:
    session = _mock_session([[]])  # one query, empty
    ctx = await build_cb_nlp_context(session, days=7)
    assert isinstance(ctx, Couche2Context)
    assert ctx.n_rows == 0
    assert "No CB speeches" in ctx.body
    assert ctx.sources == ["cb_speeches"]


@pytest.mark.asyncio
async def test_cb_nlp_with_rows_renders_grouped_by_cb() -> None:
    speech_fed = SimpleNamespace(
        central_bank="FED",
        speaker="Jerome Powell",
        published_at=_now() - timedelta(days=1),
        title="Monetary policy outlook for 2026",
        summary="The Committee judged that the policy stance remains restrictive.",
        url="https://federalreserve.gov/speech1",
    )
    speech_ecb = SimpleNamespace(
        central_bank="ECB",
        speaker="Christine Lagarde",
        published_at=_now() - timedelta(days=2),
        title="Inflation trajectory in the euro area",
        summary="Inflation is converging towards target.",
        url="https://ecb.europa.eu/speech1",
    )
    session = _mock_session([[speech_fed, speech_ecb]])

    ctx = await build_cb_nlp_context(session)

    assert ctx.n_rows == 2
    assert "## ECB" in ctx.body
    assert "## FED" in ctx.body
    assert "Jerome Powell" in ctx.body
    assert "Lagarde" in ctx.body
    assert "federalreserve.gov" in ctx.body


# ── build_news_nlp_context ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_news_nlp_empty_window_returns_sentinel() -> None:
    session = _mock_session([[]])
    ctx = await build_news_nlp_context(session, hours=4)
    assert ctx.n_rows == 0
    assert "No headlines" in ctx.body


@pytest.mark.asyncio
async def test_news_nlp_groups_by_source_kind_and_renders_tone() -> None:
    item1 = SimpleNamespace(
        source="reuters",
        source_kind="news",
        title="Fed signals patience on rate cuts",
        summary="Officials see no urgency.",
        published_at=_now() - timedelta(hours=1),
        url="https://reuters.com/1",
        tone_label="negative",
        tone_score=-0.42,
    )
    item2 = SimpleNamespace(
        source="ecb_press",
        source_kind="central_bank",
        title="ECB holds rates steady",
        summary=None,
        published_at=_now() - timedelta(hours=2),
        url="https://ecb.europa.eu/press1",
        tone_label=None,
        tone_score=None,
    )
    session = _mock_session([[item1, item2]])
    ctx = await build_news_nlp_context(session, hours=4)

    assert ctx.n_rows == 2
    assert "## news" in ctx.body
    assert "## central_bank" in ctx.body
    assert "[tone=negative -0.42]" in ctx.body
    # No tone block when score is None
    assert "[tone=None" not in ctx.body


# ── build_sentiment_context ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_sentiment_empty_aaii_emits_explicit_null_instruction() -> None:
    session = _mock_session([[]])
    ctx = await build_sentiment_context(session)
    assert "AAII data not yet ingested" in ctx.body
    assert "return aaii=null" in ctx.body
    assert "Reddit/Google Trends collectors not yet wired" in ctx.body


@pytest.mark.asyncio
async def test_sentiment_with_aaii_renders_weekly_rows() -> None:
    today = date.today()
    rows = [
        SimpleNamespace(observation_date=today, series_id="AAII_BULLISH", value=0.42),
        SimpleNamespace(observation_date=today, series_id="AAII_BEARISH", value=0.32),
        SimpleNamespace(observation_date=today, series_id="AAII_NEUTRAL", value=0.26),
        SimpleNamespace(observation_date=today, series_id="AAII_SPREAD", value=0.10),
    ]
    session = _mock_session([rows])
    ctx = await build_sentiment_context(session)
    assert "AAII Sentiment Survey" in ctx.body
    assert "bull=42%" in ctx.body
    assert "bear=32%" in ctx.body
    assert ctx.n_rows == 4


# ── build_positioning_context ────────────────────────────────────────


@pytest.mark.asyncio
async def test_positioning_all_empty_emits_three_null_sentinels() -> None:
    # Three queries : COT, GEX, Polymarket — all return empty
    session = _mock_session([[], [], []])
    ctx = await build_positioning_context(session)
    assert "return cot=[]" in ctx.body
    assert "return gex=[]" in ctx.body
    assert "return polymarket_whales=[]" in ctx.body
    assert "iv_skews=[]" in ctx.body


@pytest.mark.asyncio
async def test_positioning_with_cot_renders_market_codes_to_assets() -> None:
    eur_row = SimpleNamespace(
        report_date=date(2026, 5, 1),
        market_code="099741",
        market_name="EURO FX",
        producer_net=-12000,
        swap_dealer_net=-50000,
        managed_money_net=85000,
        other_reportable_net=10000,
        non_reportable_net=-5000,
        open_interest=750000,
    )
    session = _mock_session([[eur_row], [], []])
    ctx = await build_positioning_context(session)
    assert "EUR_USD" in ctx.body
    assert "managed_money_net=+85,000" in ctx.body
    assert "OI=750,000" in ctx.body


@pytest.mark.asyncio
async def test_positioning_with_gex_renders_billions_format() -> None:
    gex_row = SimpleNamespace(
        asset="SPX",
        captured_at=_now() - timedelta(hours=3),
        source="yfinance",
        dealer_gex_total=2_500_000_000.0,  # +2.5bn$
        spot_at_capture=5187.0,
        gamma_flip=5160.0,
        call_wall=5250.0,
        put_wall=5100.0,
    )
    session = _mock_session([[], [gex_row], []])
    ctx = await build_positioning_context(session)
    assert "+2.50bn$" in ctx.body
    assert "spot=5187" in ctx.body
    assert "src=yfinance" in ctx.body


# ── build_economic_calendar_context ──────────────────────────────────


@pytest.mark.asyncio
async def test_economic_calendar_empty_returns_empty_string() -> None:
    session = _mock_session([[]])
    out = await build_economic_calendar_context(session, hours_ahead=24)
    assert out == ""


@pytest.mark.asyncio
async def test_economic_calendar_renders_event_with_currency_and_impact() -> None:
    event = SimpleNamespace(
        scheduled_at=_now() + timedelta(hours=2),
        currency="USD",
        impact="High",
        title="Non-Farm Payrolls",
        forecast="180K",
        previous="200K",
    )
    session = _mock_session([[event]])
    out = await build_economic_calendar_context(session, hours_ahead=24)
    assert "[USD] HIGH" in out
    assert "Non-Farm Payrolls" in out
    assert "forecast=180K" in out


# ── dispatcher ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_unknown_kind_raises() -> None:
    session = _mock_session([[]])
    with pytest.raises(ValueError, match="unknown kind"):
        await build_context_for_kind(session, "definitely_not_an_agent", hours=6)


@pytest.mark.asyncio
async def test_dispatcher_macro_kind_accepted() -> None:
    """macro is a valid kind — should run the macro context loader.

    Two queries : FRED + CB speeches, plus calendar = 3 total.
    """
    session = _mock_session([[], [], []])
    ctx = await build_context_for_kind(session, "macro")
    assert "Macro context" in ctx.body


@pytest.mark.asyncio
async def test_dispatcher_appends_economic_calendar_when_present() -> None:
    # cb_nlp uses 1 query, calendar uses 1 query
    speech = SimpleNamespace(
        central_bank="FED",
        speaker="Powell",
        published_at=_now(),
        title="Test",
        summary=None,
        url="https://x",
    )
    event = SimpleNamespace(
        scheduled_at=_now() + timedelta(hours=4),
        currency="EUR",
        impact="Medium",
        title="ECB minutes",
        forecast=None,
        previous=None,
    )
    session = _mock_session([[speech], [event]])
    ctx = await build_context_for_kind(session, "cb_nlp")
    assert "## FED" in ctx.body
    assert "Upcoming economic events" in ctx.body
    assert "economic_events" in ctx.sources
