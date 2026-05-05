"""Pure tests for portfolio_exposure synthesizer.

Math + branching tests without DB (we mock CardLite directly).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.services.portfolio_exposure import (
    _USD_AXIS,
    CardLite,
    ExposureAxis,
    ExposureReport,
    _card_weight,
    _compute_axis,
    _direction_sign,
    render_portfolio_exposure_block,
)


def _card(asset: str, bias: str, conviction: float = 50.0, mag: float = 30.0) -> CardLite:
    return CardLite(
        asset=asset,
        bias=bias,
        conviction_pct=conviction,
        magnitude_pips_low=mag,
        magnitude_pips_high=mag * 2,
        session_type="pre_londres",
        created_at=datetime.now(UTC),
    )


def test_direction_sign_long_positive() -> None:
    assert _direction_sign("long") == 1.0


def test_direction_sign_short_negative() -> None:
    assert _direction_sign("short") == -1.0


def test_direction_sign_neutral_zero() -> None:
    assert _direction_sign("neutral") == 0.0
    assert _direction_sign("garbage") == 0.0


def test_card_weight_neutral_returns_zero() -> None:
    c = _card("EUR_USD", "neutral", conviction=70)
    assert _card_weight(c) == 0.0


def test_card_weight_high_conviction_long() -> None:
    c = _card("EUR_USD", "long", conviction=80, mag=30)
    w = _card_weight(c)
    assert w > 0.5  # 0.80 × 1.0 = 0.80


def test_card_weight_low_conviction_low_mag() -> None:
    c = _card("EUR_USD", "long", conviction=10, mag=10)
    w = _card_weight(c)
    assert 0.0 < w < 0.2


def test_card_weight_short_negative() -> None:
    c = _card("USD_JPY", "short", conviction=60, mag=40)
    assert _card_weight(c) < 0


def test_compute_axis_usd_long_eur_short_increases_usd() -> None:
    """Short EUR/USD = long USD."""
    cards = [_card("EUR_USD", "short", conviction=70, mag=30)]
    axis = _compute_axis(cards, _USD_AXIS, "USD")
    assert axis.score > 0  # USD long bias from short EUR/USD


def test_compute_axis_usd_long_jpy_increases_usd() -> None:
    """Long USD/JPY = long USD."""
    cards = [_card("USD_JPY", "long", conviction=70, mag=30)]
    axis = _compute_axis(cards, _USD_AXIS, "USD")
    assert axis.score > 0


def test_compute_axis_no_active_cards_returns_zero() -> None:
    cards = [_card("EUR_USD", "neutral")]
    axis = _compute_axis(cards, _USD_AXIS, "USD")
    assert axis.score == 0


def test_compute_axis_balanced_returns_near_zero() -> None:
    """Long EUR/USD AND long USD/JPY should partially cancel."""
    cards = [
        _card("EUR_USD", "long", conviction=70, mag=30),
        _card("USD_JPY", "long", conviction=70, mag=30),
    ]
    axis = _compute_axis(cards, _USD_AXIS, "USD")
    # EUR/USD long → USD short ; USD/JPY long → USD long → cancels
    assert abs(axis.score) < 0.3


def test_render_portfolio_no_data() -> None:
    r = ExposureReport(n_cards=0, cards=[], axes=[])
    md, sources = render_portfolio_exposure_block(r)
    assert "Aucune carte" in md
    assert sources == []


def test_render_portfolio_with_axes() -> None:
    r = ExposureReport(
        n_cards=3,
        cards=[
            _card("EUR_USD", "short", conviction=70),
            _card("USD_JPY", "long", conviction=70),
            _card("XAU_USD", "short", conviction=60),
        ],
        axes=[
            ExposureAxis(
                name="USD",
                score=0.65,
                contributors=[("EUR_USD", 0.3), ("USD_JPY", 0.4)],
            ),
            ExposureAxis(name="Gold", score=-0.40, contributors=[("XAU_USD", -0.4)]),
            ExposureAxis(name="Equity", score=0.0),
            ExposureAxis(name="JPY haven", score=-0.21),
            ExposureAxis(name="Commodity FX", score=0.0),
        ],
        concentration_warnings=["Note 5/8 USD-long"],
    )
    md, sources = render_portfolio_exposure_block(r)
    assert "USD" in md
    assert "0.65" in md
    assert "Gold" in md
    assert "-0.40" in md
    assert "Concentration warnings" in md
    assert "5/8 USD-long" in md
    # Sources include provenance for each card
    assert any("EUR_USD" in s for s in sources)
