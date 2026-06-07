"""TDD for the Session 04 evidence-weighted conviction core (kill the 50/50).

Pure-unit tests for ``ichor_api.services.conviction_fusion.fuse_conviction``.
No DB, no LLM, no fixtures — the function is a deterministic primitive.

ADR anchors asserted here:
  * ADR-017 — direction is bucket-only; ``theme`` cannot vote direction;
    ``rationale_fr`` carries no trade-signal token.
  * ADR-022 — ``conviction_pct`` never exceeds 95.
  * Doctrine #11 — a true coin-flip returns honest ``neutral / 0.0``.
"""

from __future__ import annotations

import re

import pytest
from ichor_api.services.conviction_fusion import (
    AGREEMENT_FLOOR,
    CONVICTION_CEIL_PCT,
    fuse_conviction,
)

# Mirror of scenarios.py:50-53 _FORBIDDEN_MECHANISM_TOKENS_RE (ADR-017 boundary).
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """Build a 7-bucket Pass-6 decomposition with the given bullish/bearish
    mass concentrated in the strong buckets; the remainder sits in ``base``."""
    base = max(0.0, 1.0 - bull - bear)
    return [
        {"label": "crash_flush", "p": 0.0},
        {"label": "strong_bear", "p": bear},
        {"label": "mild_bear", "p": 0.0},
        {"label": "base", "p": base},
        {"label": "mild_bull", "p": 0.0},
        {"label": "strong_bull", "p": bull},
        {"label": "melt_up", "p": 0.0},
    ]


# 1 — hard dead-zone: a genuine coin-flip is reported honestly as neutral/0.
def test_fuse_returns_neutral_below_hard_deadzone() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.50, 0.48))
    assert g.direction == "neutral"
    assert g.conviction_pct == 0.0
    assert "pile ou face" in g.rationale_fr


# 2 — graded soft-zone: a weak edge is attenuated linearly (not cliff-dropped).
def test_fuse_grades_soft_deadzone() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.30, 0.20))  # spread 0.10
    assert g.direction == "up"
    assert g.base_conviction_pct == pytest.approx(30.0)
    # soft_scale = (0.10 - 0.05) / (0.15 - 0.05) = 0.5, no evidence => factor 1.0
    assert g.conviction_pct == pytest.approx(15.0)
    assert g.soft_zone_scale == pytest.approx(0.5)


# 3 — aligned confluence promotes conviction, but bounded.
def test_aligned_confluence_promotes_bounded() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), confluence_lean="long")
    assert g.direction == "up"
    assert 60.0 < g.conviction_pct <= 75.0
    assert "confluence" in g.agreeing
    assert g.conviction_pct == pytest.approx(66.0)  # 60 * 1.1


# 4 — opposed confluence demotes conviction, but cannot floor below the band.
def test_opposed_confluence_demotes() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), confluence_lean="short")
    assert g.direction == "up"  # direction stays bucket-derived (ADR-017)
    assert AGREEMENT_FLOOR * 60.0 <= g.conviction_pct < 60.0
    assert "confluence" in g.disagreeing
    assert g.conviction_pct == pytest.approx(54.0)  # 60 * 0.9


# 5 — dollar consensus maps per asset (USD-up => bearish EUR_USD, bullish USD_CAD).
def test_dollar_usd_up_maps_per_asset() -> None:
    eur = fuse_conviction(
        asset="EUR_USD",
        scenarios=_scn(0.60, 0.40),  # direction up
        dollar_consensus="usd_up",
        dollar_strength=1.0,
    )
    # USD up is bearish for EUR_USD => contradicts an UP bias.
    assert "dollar_coherence" in eur.disagreeing

    cad = fuse_conviction(
        asset="USD_CAD",
        scenarios=_scn(0.60, 0.40),  # direction up
        dollar_consensus="usd_up",
        dollar_strength=1.0,
    )
    # USD up is bullish for USD_CAD => corroborates an UP bias.
    assert "dollar_coherence" in cad.agreeing


# 6 — theme is structurally non-directional: it never flips/sets direction.
def test_theme_never_votes_direction() -> None:
    up_with = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), theme_present=True)
    up_without = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), theme_present=False)
    assert up_with.direction == up_without.direction == "up"
    assert "theme" not in up_with.disagreeing
    # theme presence can only add confidence, never subtract.
    assert up_with.conviction_pct >= up_without.conviction_pct

    down = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.40, 0.60), theme_present=True)
    assert down.direction == "down"  # theme did not flip a bearish read


# 7 — cap-95: stacked corroboration cannot manufacture certainty.
def test_fused_conviction_never_exceeds_95() -> None:
    g = fuse_conviction(
        asset="EUR_USD",
        scenarios=_scn(0.90, 0.05),  # base 90
        confluence_lean="long",
        theme_present=True,
        dollar_consensus="usd_down",  # USD down => bullish EUR_USD => aligns with up
        dollar_strength=1.0,
    )
    assert g.direction == "up"
    assert g.conviction_pct <= CONVICTION_CEIL_PCT
    assert g.conviction_pct == pytest.approx(95.0)  # 90 * 1.25 = 112.5 -> clamp 95


# 8 — grounding rationale names the agreeing AND disagreeing layers.
def test_grounding_rationale_lists_agreeing_disagreeing() -> None:
    g = fuse_conviction(
        asset="EUR_USD",
        scenarios=_scn(0.60, 0.40),  # up
        confluence_lean="long",  # agrees
        dollar_consensus="usd_up",  # disagrees (bearish EUR_USD)
        dollar_strength=1.0,
    )
    assert "confluence" in g.agreeing and "dollar_coherence" in g.disagreeing
    assert "confluence des facteurs" in g.rationale_fr
    assert "cohérence dollar" in g.rationale_fr
    assert "concordantes" in g.rationale_fr and "désaccord" in g.rationale_fr


# 9 — ADR-017: the rationale never emits a trade-signal token.
@pytest.mark.parametrize(
    ("bull", "bear", "lean", "theme", "usd", "strength"),
    [
        (0.50, 0.48, None, False, None, 0.0),  # neutral
        (0.30, 0.20, "long", True, "usd_up", 0.8),  # soft-zone, mixed
        (0.90, 0.05, "long", True, "usd_down", 1.0),  # capped
        (0.40, 0.60, "short", False, "usd_up", 0.5),  # down
    ],
)
def test_fused_conviction_emits_no_trade_tokens(
    bull: float, bear: float, lean, theme: bool, usd, strength: float
) -> None:
    g = fuse_conviction(
        asset="EUR_USD",
        scenarios=_scn(bull, bear),
        confluence_lean=lean,
        theme_present=theme,
        dollar_consensus=usd,
        dollar_strength=strength,
    )
    assert _FORBIDDEN_RE.search(g.rationale_fr) is None


# 10 — backward-compat: above the soft dead-zone with no evidence, conviction
# equals the legacy max(mass)*100 exactly (no silent behaviour change).
def test_no_evidence_above_soft_matches_legacy() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.70, 0.30))  # spread 0.40
    assert g.direction == "up"
    assert g.soft_zone_scale == pytest.approx(1.0)
    assert g.agreement_factor == pytest.approx(1.0)
    assert g.conviction_pct == pytest.approx(70.0)  # legacy: max(0.70,0.30)*100
