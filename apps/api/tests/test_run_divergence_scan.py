"""Unit tests for the divergence scan CLI helpers (sync logic only).

The async DB-bound paths are exercised via integration tests (out of
scope for unit). Here we verify:
  - severity mapping based on gap size
  - alert title rendering
"""

from __future__ import annotations

from ichor_agents.predictions.divergence import (
    DivergenceAlert,
    MatchedMarket,
    PredictionMarket,
)
from ichor_api.cli.run_divergence_scan import _alert_severity, _alert_title


def test_alert_severity_thresholds() -> None:
    assert _alert_severity(0.05) == "info"
    assert _alert_severity(0.09) == "info"
    assert _alert_severity(0.10) == "warning"
    assert _alert_severity(0.19) == "warning"
    assert _alert_severity(0.20) == "critical"
    assert _alert_severity(0.50) == "critical"


def _make_alert(gap: float, high: tuple[str, float], low: tuple[str, float]) -> DivergenceAlert:
    poly = PredictionMarket(
        venue="polymarket", market_id="x", question="Will Fed cut?", yes_price=high[1]
    )
    kal = PredictionMarket(
        venue="kalshi", market_id="x", question="Will Fed cut?", yes_price=low[1]
    )
    return DivergenceAlert(
        representative_question="Will Fed cut?",
        gap=gap,
        high=high,
        low=low,
        matched=MatchedMarket(
            representative_question="Will Fed cut?",
            similarity=1.0,
            by_venue={"polymarket": poly, "kalshi": kal},
        ),
    )


def test_alert_title_renders_venues_and_gap() -> None:
    div = _make_alert(0.15, ("polymarket", 0.65), ("kalshi", 0.50))
    title = _alert_title(div)
    assert "polymarket" in title
    assert "kalshi" in title
    assert "65%" in title
    assert "50%" in title
    # Gap is signed +15% (high - low always non-negative since `priced.sort()`)
    assert "+15%" in title
