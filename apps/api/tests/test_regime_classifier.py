"""Unit tests for `services.regime_classifier.classify_master_regime`.

Extracted from `_section_executive_summary` inline logic in W104c. These
tests pin every threshold in one place so future calibrations can't
silently drift the regime labels (a class of bug spotlighted by ADR-024
five-bug-fix where two adjacent files drifted on session-type validation).
"""

from __future__ import annotations

import pytest
from ichor_api.services.regime_classifier import (
    RegimeInputs,
    classify_master_regime,
)


def _inputs(
    *,
    skew: float | None = None,
    vix: float | None = None,
    hy_oas: float | None = None,
    nfci: float | None = None,
    cli_us: float | None = None,
    expinf: float | None = None,
    term_prem: float | None = None,
) -> RegimeInputs:
    """Convenience builder so each test only declares the inputs it tests."""
    return RegimeInputs(
        skew=skew,
        vix=vix,
        hy_oas=hy_oas,
        nfci=nfci,
        cli_us=cli_us,
        expinf=expinf,
        term_prem=term_prem,
    )


# ───────────────────────── Crisis (priority 1) ─────────────────────────


def test_crisis_triggered_by_skew_150() -> None:
    out = classify_master_regime(_inputs(skew=152.0))
    assert out.regime == "crisis"
    assert "flight to quality" in out.rationale
    assert 0.0 < out.confidence <= 1.0


def test_crisis_triggered_by_vix_30() -> None:
    out = classify_master_regime(_inputs(vix=31.5))
    assert out.regime == "crisis"


def test_crisis_triggered_by_hy_oas_6pct() -> None:
    out = classify_master_regime(_inputs(hy_oas=6.5))
    assert out.regime == "crisis"


def test_crisis_takes_priority_over_other_templates() -> None:
    # Would normally match goldilocks (CLI >100, NFCI <0, expinf in [1.5,2.5])
    # but VIX 30+ triggers crisis first.
    out = classify_master_regime(
        _inputs(
            skew=None,
            vix=32.0,
            cli_us=101.0,
            nfci=-0.2,
            expinf=2.0,
        )
    )
    assert out.regime == "crisis"


def test_crisis_confidence_scales_with_matched_conditions() -> None:
    one = classify_master_regime(_inputs(skew=151.0))
    three = classify_master_regime(_inputs(skew=160.0, vix=35.0, hy_oas=7.0))
    assert one.confidence == pytest.approx(1 / 3, abs=1e-9)
    assert three.confidence == pytest.approx(1.0, abs=1e-9)


# ───────────────────────── Broken smile (priority 2) ───────────────────


def test_broken_smile_all_4_conditions_met() -> None:
    out = classify_master_regime(
        _inputs(
            term_prem=0.5,
            vix=18.0,
            hy_oas=3.5,
            skew=135.0,
        )
    )
    assert out.regime == "broken_smile"
    assert "Stephen Jen" in out.rationale
    assert 0.0 < out.confidence <= 1.0


def test_broken_smile_fails_if_term_prem_negative() -> None:
    out = classify_master_regime(
        _inputs(
            term_prem=-0.1,
            vix=18.0,
            hy_oas=3.5,
            skew=135.0,
        )
    )
    assert out.regime != "broken_smile"


def test_broken_smile_fails_if_vix_too_high() -> None:
    out = classify_master_regime(
        _inputs(
            term_prem=0.5,
            vix=22.5,
            hy_oas=3.5,
            skew=135.0,
        )
    )
    assert out.regime != "broken_smile"


def test_broken_smile_fails_if_skew_too_low() -> None:
    out = classify_master_regime(
        _inputs(
            term_prem=0.5,
            vix=18.0,
            hy_oas=3.5,
            skew=125.0,
        )
    )
    assert out.regime != "broken_smile"


# ───────────────────────── Stagflation (priority 3) ────────────────────


def test_stagflation_growth_slowing_inflation_persisting() -> None:
    out = classify_master_regime(
        _inputs(
            cli_us=98.0,
            expinf=3.0,
        )
    )
    assert out.regime == "stagflation"
    assert "growth slowing" in out.rationale.lower()


def test_stagflation_fails_if_cli_above_100() -> None:
    out = classify_master_regime(_inputs(cli_us=101.0, expinf=3.0))
    assert out.regime != "stagflation"


def test_stagflation_fails_if_expinf_at_target() -> None:
    out = classify_master_regime(_inputs(cli_us=98.0, expinf=2.3))
    assert out.regime != "stagflation"


# ───────────────────────── Risk-off (priority 4) ───────────────────────


def test_risk_off_triggered_by_vix_above_22() -> None:
    out = classify_master_regime(_inputs(vix=25.0, hy_oas=4.0))
    assert out.regime == "risk_off"


def test_risk_off_triggered_by_hy_oas_above_5() -> None:
    out = classify_master_regime(_inputs(vix=20.0, hy_oas=5.5))
    assert out.regime == "risk_off"


# ───────────────────────── Goldilocks (priority 5) ─────────────────────


def test_goldilocks_growth_in_trend_loose_anchored() -> None:
    out = classify_master_regime(
        _inputs(
            cli_us=101.0,
            nfci=-0.5,
            expinf=2.0,
            vix=18.0,  # below risk_off threshold
            hy_oas=4.0,  # below risk_off threshold
        )
    )
    assert out.regime == "goldilocks"
    assert "growth in trend" in out.rationale.lower()


def test_goldilocks_fails_if_inflation_above_target() -> None:
    out = classify_master_regime(
        _inputs(
            cli_us=101.0,
            nfci=-0.5,
            expinf=2.8,
            vix=18.0,
            hy_oas=4.0,
        )
    )
    assert out.regime != "goldilocks"


# ───────────────────────── Risk-on (priority 6) ────────────────────────


def test_risk_on_loose_low_vol_low_skew() -> None:
    out = classify_master_regime(
        _inputs(
            nfci=-0.5,
            skew=125.0,
            vix=15.0,
        )
    )
    assert out.regime == "risk_on"
    assert "complacent" in out.rationale.lower()


def test_risk_on_fails_if_skew_elevated() -> None:
    out = classify_master_regime(
        _inputs(
            nfci=-0.5,
            skew=135.0,
            vix=15.0,
        )
    )
    assert out.regime != "risk_on"


# ───────────────────────── Transitional (fallback) ─────────────────────


def test_transitional_when_all_inputs_none() -> None:
    out = classify_master_regime(_inputs())
    assert out.regime == "transitional"
    assert out.confidence == 0.0


def test_transitional_when_no_template_matches() -> None:
    # CLI just at 100, expinf at 2.0 (anchored), NFCI slightly positive
    # (not <-0.3), VIX 20 (between 18 and 22) → falls through everything.
    out = classify_master_regime(
        _inputs(
            cli_us=100.0,
            nfci=0.05,
            expinf=2.0,
            vix=20.0,
            skew=128.0,
            hy_oas=4.2,
        )
    )
    assert out.regime == "transitional"


# ───────────────────────── Bias hints invariants ───────────────────────


def test_every_regime_has_4_bias_hint_keys() -> None:
    """All 7 buckets must surface fx_majors / xau / us_equity_indices /
    treasuries — Pass-2 narrative generation depends on this contract."""
    expected_keys = {"fx_majors", "xau", "us_equity_indices", "treasuries"}
    seeds: list[tuple[str, RegimeInputs]] = [
        ("crisis", _inputs(vix=35.0)),
        ("broken_smile", _inputs(term_prem=0.5, vix=18.0, hy_oas=3.5, skew=135.0)),
        ("stagflation", _inputs(cli_us=98.0, expinf=3.0)),
        ("risk_off", _inputs(vix=25.0)),
        ("goldilocks", _inputs(cli_us=101.0, nfci=-0.5, expinf=2.0, vix=18.0, hy_oas=4.0)),
        ("risk_on", _inputs(nfci=-0.5, skew=125.0, vix=15.0)),
        ("transitional", _inputs()),
    ]
    for label, inputs in seeds:
        out = classify_master_regime(inputs)
        assert out.regime == label, f"expected {label}, got {out.regime}"
        assert set(out.bias_hints.keys()) == expected_keys, (
            f"regime {label} bias_hints keys = {set(out.bias_hints.keys())}, "
            f"expected {expected_keys}"
        )


def test_bias_hints_never_emit_buy_sell_tokens() -> None:
    """ADR-017 boundary regression guard. Bias hints describe macro-consistent
    observations, never trade signals — grep BUY/SELL/TP/SL must return zero."""
    forbidden = {"buy", "sell", "tp ", "sl ", "long entry", "short entry"}
    seeds: list[RegimeInputs] = [
        _inputs(vix=35.0),
        _inputs(term_prem=0.5, vix=18.0, hy_oas=3.5, skew=135.0),
        _inputs(cli_us=98.0, expinf=3.0),
        _inputs(vix=25.0),
        _inputs(cli_us=101.0, nfci=-0.5, expinf=2.0, vix=18.0, hy_oas=4.0),
        _inputs(nfci=-0.5, skew=125.0, vix=15.0),
        _inputs(),
    ]
    for inputs in seeds:
        out = classify_master_regime(inputs)
        for asset_class, hint in out.bias_hints.items():
            hint_lower = hint.lower()
            for token in forbidden:
                assert token not in hint_lower, (
                    f"forbidden token {token!r} in bias_hint[{asset_class}] "
                    f"for regime {out.regime}: {hint!r}"
                )


# ───────────────────────── Confidence bounds ───────────────────────────


def test_confidence_always_in_zero_one() -> None:
    """Confidence is a heuristic margin — must stay in [0, 1] for all paths."""
    seeds: list[RegimeInputs] = [
        _inputs(skew=200.0, vix=60.0, hy_oas=15.0),  # crisis extreme
        _inputs(term_prem=2.0, vix=10.0, hy_oas=2.0, skew=180.0),  # broken_smile extreme
        _inputs(cli_us=90.0, expinf=5.0),  # stagflation extreme
        _inputs(vix=50.0),  # risk_off extreme
        _inputs(cli_us=110.0, nfci=-2.0, expinf=2.0, vix=18.0, hy_oas=4.0),  # goldilocks
        _inputs(nfci=-1.5, skew=100.0, vix=10.0),  # risk_on extreme
        _inputs(),  # transitional
    ]
    for inputs in seeds:
        out = classify_master_regime(inputs)
        assert 0.0 <= out.confidence <= 1.0, (
            f"confidence {out.confidence} out of [0,1] for regime {out.regime}"
        )
