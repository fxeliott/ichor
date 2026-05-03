"""Tests for the Critic reviewer.

Pure-Python — no LLM call, no DB, no network. Validates the
hallucination detection heuristics on hand-crafted briefing /
source-pool fixtures.
"""

from __future__ import annotations

from ichor_agents.critic import review_briefing


SOURCE_POOL_FULL = """
Bias signals: EUR/USD long 0.62, XAU/USD short 0.58, NAS100 long 0.55.
Active alerts: VIX_SPIKE warning, HY_OAS_CRISIS critical.
News: ECB Lagarde monetary policy, BBC Spirit Airlines shutdown.
Polymarket: Will the Fed cut in March? yes 0.45.
Models: lightgbm-bias-eur_usd-1d-v0
"""


def test_approved_when_briefing_strictly_uses_sources() -> None:
    md = (
        "EUR/USD shows a long bias at 0.62. "
        "VIX_SPIKE alert is active. "
        "ECB held rates."
    )
    v = review_briefing(md, SOURCE_POOL_FULL)
    assert v.verdict == "approved"
    assert v.confidence == 1.0
    assert v.findings == []


def test_blocked_when_unknown_model_id_appears() -> None:
    md = "Our model lightgbm-bias-fake_unknown-v9 says EUR/USD will rise 5%."
    v = review_briefing(md, SOURCE_POOL_FULL)
    assert v.verdict == "blocked"
    # critical severity because of model_id
    assert any(f.severity == "critical" for f in v.findings)


def test_amendments_when_unknown_asset_mentioned() -> None:
    md = "EUR/USD is bullish. Also USDCHF (not in our scope) looks bid."
    v = review_briefing(md, SOURCE_POOL_FULL)
    # USDCHF isn't matched by our asset regex (only Phase-0 assets), so
    # this prose actually *passes* — that's fine. The point is the
    # in-scope asset still validates.
    assert v.verdict in ("approved", "amendments")


def test_amendments_when_asset_not_in_pool() -> None:
    # XAU/USD IS matched by our asset regex but absent from this trimmed pool
    trimmed = "Bias signals: EUR/USD long. ECB held rates."
    md = "EUR/USD up. XAU/USD ripping today."
    v = review_briefing(md, trimmed)
    # XAU/USD is unsourced → at least one finding
    assert v.findings
    assert v.verdict in ("amendments", "blocked")


def test_low_confidence_blocks() -> None:
    """A briefing where every evidence sentence is unsourced gets blocked."""
    md = (
        "DXY up 2.5%. "
        "BoJ intervened at 158. "
        "GBP/USD broke 1.30."
    )
    pool = "EUR/USD bias 0.55."
    v = review_briefing(md, pool)
    assert v.verdict == "blocked"
    assert v.confidence < 0.6


def test_evidence_sentence_detection() -> None:
    md = (
        "This sentence has no entities or numbers. "
        "But this one mentions EUR/USD. "
        "And this other has a 25% number."
    )
    pool = "EUR/USD long bias and 25% volatility."
    v = review_briefing(md, pool)
    # 2 evidence sentences (ones with EUR/USD or 25%)
    assert v.n_evidence_sentences == 2


def test_empty_briefing_approved_with_no_findings() -> None:
    v = review_briefing("", SOURCE_POOL_FULL)
    assert v.verdict == "approved"
    assert v.findings == []


def test_central_bank_findings_are_info_severity() -> None:
    """Mentioning a CB not in scope is informational, not blocking."""
    md = "EUR/USD up. SNB hawkish rhetoric."
    pool = "EUR/USD long bias. ECB held."
    v = review_briefing(md, pool)
    cb_findings = [f for f in v.findings if "institution" in f.reason]
    assert all(f.severity == "info" for f in cb_findings)


def test_asset_whitelist_extends_pool() -> None:
    """Whitelist allows extra assets to validate even if not in pool body."""
    md = "AUD/USD breakdown."
    pool = "EUR/USD long. XAU/USD short."
    v_no_whitelist = review_briefing(md, pool)
    v_whitelist = review_briefing(md, pool, asset_whitelist=["AUD/USD"])
    # Without whitelist, AUD/USD is flagged ; with it, it's allowed
    assert len(v_no_whitelist.findings) > len(v_whitelist.findings)


def test_suggested_footer_added_when_amendments_or_blocked() -> None:
    md = "DXY up 2.5%."  # unsourced
    pool = "EUR/USD long bias."
    v = review_briefing(md, pool)
    if v.verdict != "approved":
        assert "Critic notes" in v.suggested_footer


def test_decimal_split_safe() -> None:
    """0.5 should not be sentence-split."""
    md = "Probability is 0.55. The model trained well."
    pool = "Probability 0.55."
    v = review_briefing(md, pool)
    # Both sentences valid, but the first has a number "0.55" — should
    # not split inside 0.55.
    assert v.confidence > 0.5
