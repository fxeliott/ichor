"""Pure-format tests for the rich briefing context builder.

The async DB-fetch helpers are intentionally NOT covered here (would need
an async session fixture). The format helpers below are pure functions of
in-memory ORM-shaped objects — easy to test without a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from ichor_api.briefing.context_builder import (
    CHARS_PER_TOKEN,
    DEFAULT_MAX_TOKENS,
    ContextSection,
    _format_alerts,
    _format_bias,
    _format_market_data,
    _format_news,
    _format_polymarket,
    _render,
)

# ───────────────────────────── stubs ─────────────────────────────


@dataclass
class _StubBias:
    asset: str
    direction: str
    probability: float
    credible_interval_low: float
    credible_interval_high: float
    weights_snapshot: dict


@dataclass
class _StubAlert:
    severity: str
    alert_code: str
    title: str
    metric_name: str
    metric_value: float
    threshold: float
    direction: str
    triggered_at: datetime


@dataclass
class _StubBar:
    asset: str
    bar_date: date
    close: float


@dataclass
class _StubNews:
    source: str
    source_kind: str
    title: str
    published_at: datetime
    tone_label: str | None = None


@dataclass
class _StubPoly:
    slug: str
    question: str
    fetched_at: datetime
    last_prices: list[float]
    volume_usd: float | None


# ───────────────────────────── tests ─────────────────────────────


def test_format_bias_table_shape() -> None:
    bias = [
        _StubBias("EUR_USD", "long", 0.62, 0.55, 0.69, {"lightgbm": 0.4, "xgboost": 0.3}),
        _StubBias("XAU_USD", "short", 0.58, 0.50, 0.66, {"lightgbm": 1.0}),
    ]
    out = _format_bias(bias)
    assert "| Asset | Direction" in out
    assert "EUR_USD" in out
    assert "XAU_USD" in out
    # Top model = lightgbm in both cases
    assert out.count("lightgbm") == 2


def test_format_bias_empty() -> None:
    out = _format_bias([])
    assert "aucun signal" in out.lower()


def test_format_alerts_orders_and_labels() -> None:
    a = [
        _StubAlert(
            severity="critical",
            alert_code="VIX_PANIC",
            title="VIX 35",
            metric_name="VIXCLS",
            metric_value=35.5,
            threshold=35,
            direction="above",
            triggered_at=datetime(2026, 5, 3, 14, 30, tzinfo=UTC),
        ),
    ]
    out = _format_alerts(a)
    assert "CRITICAL" in out
    assert "VIX_PANIC" in out
    assert "VIX 35" in out


def test_format_alerts_empty() -> None:
    assert "nominal" in _format_alerts([]).lower()


def test_format_market_data_dd_pct() -> None:
    bars = [
        _StubBar("EUR_USD", date(2026, 5, 1), 1.0850),
        _StubBar("EUR_USD", date(2026, 5, 2), 1.0900),
        _StubBar("XAU_USD", date(2026, 5, 1), 2900.0),
        _StubBar("XAU_USD", date(2026, 5, 2), 2870.0),
    ]
    out = _format_market_data(bars)
    assert "EUR_USD" in out
    assert "XAU_USD" in out
    # +0.46% for EUR/USD, -1.03% for XAU/USD
    assert "+0.46%" in out
    assert "-1.03%" in out


def test_format_market_data_empty() -> None:
    assert "aucune barre" in _format_market_data([]).lower()


def test_format_market_data_single_bar_no_change() -> None:
    bars = [_StubBar("EUR_USD", date(2026, 5, 2), 1.0900)]
    out = _format_market_data(bars)
    assert "n/a" in out


def test_format_news_groups_by_kind() -> None:
    items = [
        _StubNews(
            "ecb_press",
            "central_bank",
            "Lagarde speaks",
            datetime(2026, 5, 3, 8, 0, tzinfo=UTC),
            "neutral",
        ),
        _StubNews("bbc_business", "news", "Markets steady", datetime(2026, 5, 3, 9, 0, tzinfo=UTC)),
    ]
    out = _format_news(items)
    assert "Banques centrales" in out
    assert "Presse finance" in out
    assert "Lagarde speaks" in out
    assert "Markets steady" in out
    assert "[neutral]" in out  # tone label rendered


def test_format_news_empty() -> None:
    assert "aucune dépêche" in _format_news([]).lower()


def test_format_polymarket_picks_latest_per_slug() -> None:
    snaps = [
        _StubPoly(
            "fed-march",
            "Will the Fed cut in March?",
            datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
            [0.42, 0.58],
            1_000_000.0,
        ),
        _StubPoly(
            "fed-march",
            "Will the Fed cut in March?",
            datetime(2026, 5, 3, 11, 0, tzinfo=UTC),
            [0.45, 0.55],
            1_100_000.0,
        ),
    ]
    out = _format_polymarket(snaps)
    # Only the latest snapshot rendered → 0.45, not 0.42
    assert "0.45" in out
    assert "0.42" not in out


def test_format_polymarket_empty() -> None:
    assert "aucun snapshot" in _format_polymarket([]).lower()


def test_render_sections_order_and_header() -> None:
    sections = [
        ContextSection("First", "body 1", priority=10),
        ContextSection("Second", "body 2", priority=5),
    ]
    out = _render("# Header", sections)
    assert out.startswith("# Header")
    assert "## First" in out
    assert "## Second" in out
    assert out.index("## First") < out.index("## Second")


def test_default_token_budget_reasonable() -> None:
    """Budget should be large enough to fit the legacy assembler ~5x over."""
    assert DEFAULT_MAX_TOKENS >= 8000
    assert CHARS_PER_TOKEN == 4
