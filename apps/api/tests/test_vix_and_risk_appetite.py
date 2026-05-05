"""Pure tests for vix_term_structure + risk_appetite.

Tests the bucket / classifier logic without a live DB.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.services.risk_appetite import (
    RiskAppetiteComponent,
    RiskAppetiteReading,
    _band,
    _curve_contribution,
    _hy_oas_contribution,
    _ig_oas_contribution,
    _sentiment_contribution,
    _vix_contribution,
    render_risk_appetite_block,
)
from ichor_api.services.vix_term_structure import (
    VixTermReading,
    _classify,
    _interpretation,
    render_vix_term_block,
)

# ─────────────────── vix_term_structure ────────────────────


def test_classify_extreme_backwardation() -> None:
    assert _classify(1.20) == "extreme_backwardation"


def test_classify_backwardation() -> None:
    assert _classify(1.05) == "backwardation"


def test_classify_flat() -> None:
    assert _classify(0.99) == "flat"


def test_classify_normal() -> None:
    assert _classify(0.90) == "normal"


def test_classify_contango() -> None:
    assert _classify(0.82) == "contango"


def test_classify_stretched_contango() -> None:
    assert _classify(0.70) == "stretched_contango"


def test_classify_none_returns_flat() -> None:
    assert _classify(None) == "flat"


def test_interpretation_extreme_backwardation_mentions_long() -> None:
    out = _interpretation("extreme_backwardation", 35.0)
    assert "long" in out.lower()
    assert "mean-revert" in out.lower()


def test_interpretation_stretched_low_vix() -> None:
    out = _interpretation("stretched_contango", 11.5)
    assert "11.5" in out
    assert "complacence" in out.lower()


def test_render_vix_term_no_data() -> None:
    r = VixTermReading(
        vix_1m=None,
        vix_3m=None,
        ratio=None,
        spread=None,
        regime="flat",
        interpretation="Données FRED VIX/VIX3M incomplètes.",
        observation_date=None,
        sources=[],
    )
    md, sources = render_vix_term_block(r)
    assert "incomplètes" in md
    assert sources == []


def test_render_vix_term_full_payload() -> None:
    r = VixTermReading(
        vix_1m=18.5,
        vix_3m=21.2,
        ratio=0.873,
        spread=-2.7,
        regime="normal",
        interpretation="Contango normal — risk-on.",
        observation_date=datetime(2026, 5, 4, tzinfo=UTC),
        sources=["FRED:VIXCLS", "FRED:VXVCLS"],
    )
    md, sources = render_vix_term_block(r)
    assert "VIX 1M = 18.50" in md
    assert "VIX 3M = 21.20" in md
    assert "0.873" in md
    assert "FRED:VIXCLS" in sources
    assert "FRED:VXVCLS" in sources


# ─────────────────── risk_appetite ────────────────────


def test_band_extreme_risk_on() -> None:
    assert _band(0.7) == "extreme_risk_on"


def test_band_risk_on() -> None:
    assert _band(0.3) == "risk_on"


def test_band_neutral() -> None:
    assert _band(0.0) == "neutral"
    assert _band(0.15) == "neutral"
    assert _band(-0.15) == "neutral"


def test_band_risk_off() -> None:
    assert _band(-0.3) == "risk_off"


def test_band_extreme_risk_off() -> None:
    assert _band(-0.7) == "extreme_risk_off"


def test_vix_contribution_panic() -> None:
    contrib, rat = _vix_contribution(35.0)
    assert contrib < 0
    assert "panique" in rat.lower() or "risk-off fort" in rat.lower()


def test_vix_contribution_calm() -> None:
    contrib, rat = _vix_contribution(12.0)
    assert contrib > 0
    assert "calme" in rat.lower() or "risk-on fort" in rat.lower()


def test_vix_contribution_neutral() -> None:
    contrib, _ = _vix_contribution(20.0)
    assert contrib == 0.0


def test_vix_contribution_none_returns_zero() -> None:
    contrib, rat = _vix_contribution(None)
    assert contrib == 0.0
    assert "n/a" in rat


def test_hy_oas_contribution_high_returns_negative() -> None:
    contrib, _ = _hy_oas_contribution(7.0)
    assert contrib < 0


def test_hy_oas_contribution_tight_returns_positive() -> None:
    contrib, _ = _hy_oas_contribution(2.5)
    assert contrib > 0


def test_ig_oas_contribution_brackets() -> None:
    assert _ig_oas_contribution(2.5)[0] < 0
    assert _ig_oas_contribution(0.5)[0] > 0
    assert _ig_oas_contribution(1.5)[0] == 0


def test_curve_contribution_positive_steep() -> None:
    contrib, _ = _curve_contribution(0.8)
    assert contrib > 0


def test_curve_contribution_inverted() -> None:
    contrib, _ = _curve_contribution(-0.6)
    assert contrib < 0


def test_sentiment_contribution_high_consumer() -> None:
    contrib, _ = _sentiment_contribution(95.0)
    assert contrib > 0


def test_sentiment_contribution_low_consumer() -> None:
    contrib, _ = _sentiment_contribution(55.0)
    assert contrib < 0


def test_render_risk_appetite_block() -> None:
    r = RiskAppetiteReading(
        composite=+0.35,
        band="risk_on",
        components=[
            RiskAppetiteComponent(
                name="VIX 1M",
                series_id="VIXCLS",
                value=14.5,
                contribution=+0.20,
                rationale="VIX 14.5 ≤ 18 (normal-bas) → risk-on",
            ),
            RiskAppetiteComponent(
                name="HY OAS",
                series_id="BAMLH0A0HYM2",
                value=2.8,
                contribution=+0.30,
                rationale="HY OAS 2.80% ≤ 3 → credit risk-on",
            ),
        ],
        sources=["FRED:VIXCLS", "FRED:BAMLH0A0HYM2"],
    )
    md, sources = render_risk_appetite_block(r)
    assert "risk_on" in md
    assert "+0.35" in md or "0.35" in md
    assert "VIX 1M" in md
    assert "HY OAS" in md
    assert "FRED:VIXCLS" in sources
