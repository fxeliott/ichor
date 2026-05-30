"""r168 G3 tests for ``_classify_risk_regime`` — self-calibrating z-score
risk-on / risk-off / transitional classifier feeding the
``CoachMacroContext.risk_regime`` field.

Eliot's verbatim §X pillar from the Fathom 2026-05-25 methodology
transcript : « régime risk on ou risk off et on a pas mal de choses à
voir pour anticiper notre risque ou non ». The classifier reads the
trailing 252d z-score of two FRED stress indicators (VIXCLS = CBOE vol,
BAMLH0A0HYM2 = ICE BofA US HY OAS in %) and labels the ambient regime
on the strict priority ladder :

  1. **risk_on**  — BOTH z ≤ -0.7σ (calm + tight credit, signal aligned)
  2. **risk_off** — EITHER z ≥ +0.7σ (single-channel stress sufficient)
  3. **transitional** — default (signal sub-threshold OR insufficient data)

The tests pin every branch of the priority ladder + the evidence-list
contract + the doctrine #11 honest-absence path when data is missing.

**Pattern #15 R59 compliance** : these tests never assert "VIX > 22 =
risk_off" or any absolute-threshold claim. They only assert "given a
mocked z-score X, the classifier returns Y" — pure dispatch logic.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from ichor_api.services.coach_macro_context_builder import (
    _RISK_REGIME_Z_RISK_OFF,
    _RISK_REGIME_Z_RISK_ON,
    _classify_risk_regime,
)

# ── Pure helper to fake FRED observations ────────────────────────────


class _FakeObs:
    """Minimal stand-in for ``FredObservation`` ORM row that
    ``_z_score_latest`` accepts (just needs a ``.value`` attribute
    coercible to float)."""

    def __init__(self, value: float) -> None:
        self.value = value
        # Some downstream callers may read observation_date — provide a
        # safe default (only the value is used by _z_score_latest).
        self.observation_date = date(2026, 5, 26)


def _build_obs_series(z_target: float, *, n: int = 252) -> list[_FakeObs]:
    """Build a fake observation list of size n whose latest value is
    chosen so that ``_z_score_latest`` returns approximately
    ``z_target``. The historical mean is fixed at 20.0 with stdev 5.0
    (calibration constants — pick any consistent shape).

    Latest value = mean + z_target * stdev = 20 + 5 * z_target. The
    z_score_latest function pops the last value, computes mean/pstdev
    on the first n-1, then z = (last - mean) / stdev.

    We seed the first n-1 values with a tight distribution around mean=20
    using deterministic spread (±5) so pstdev ≈ 5 within fp tolerance.
    """
    base = [20.0 + ((i % 3) - 1) * 5.0 for i in range(n - 1)]  # spread {15, 20, 25}
    last = 20.0 + z_target * 5.0
    return [_FakeObs(v) for v in (*base, last)]


# ── Tests ─────────────────────────────────────────────────────────────


class TestR168RiskRegimeRiskOn:
    """``risk_on`` requires BOTH VIXCLS z ≤ -0.7σ AND BAMLH0A0HYM2 z ≤
    -0.7σ — single-channel calm is not sufficient (AND discipline)."""

    @pytest.mark.asyncio
    async def test_both_z_below_threshold_yields_risk_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()

        async def fake_fetch(_session, series_id: str, _days: int):
            # Both indicators well below trend (calm + tight credit).
            return _build_obs_series(-1.5)

        monkeypatch.setattr(
            "ichor_api.services.coach_macro_context_builder._fetch_fred_window",
            fake_fetch,
        )

        regime, evidence = await _classify_risk_regime(session)

        assert regime == "risk_on"
        assert len(evidence) == 2
        # Mechanical strings : VIXCLS first, BAMLH0A0HYM2 second.
        assert evidence[0].startswith("VIXCLS z=")
        assert evidence[1].startswith("BAMLH0A0HYM2 z=")
        # Sigma sign embedded ; below trend = negative.
        assert "-" in evidence[0]
        assert "-" in evidence[1]

    @pytest.mark.asyncio
    async def test_only_vix_below_threshold_yields_transitional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Single-channel calm is not sufficient — both must be calm
        together for risk_on classification."""
        session = AsyncMock()

        async def fake_fetch(_session, series_id: str, _days: int):
            if series_id == "VIXCLS":
                return _build_obs_series(-1.5)  # below threshold
            return _build_obs_series(+0.2)  # HY-IG sub-threshold both sides

        monkeypatch.setattr(
            "ichor_api.services.coach_macro_context_builder._fetch_fred_window",
            fake_fetch,
        )

        regime, evidence = await _classify_risk_regime(session)

        assert regime == "transitional"
        # Evidence still surfaced (both classifiers ran successfully).
        assert len(evidence) == 2


class TestR168RiskRegimeRiskOff:
    """``risk_off`` triggers when EITHER VIXCLS z ≥ +0.7σ OR
    BAMLH0A0HYM2 z ≥ +0.7σ — OR discipline catches single-channel stress."""

    @pytest.mark.asyncio
    async def test_only_vix_above_threshold_yields_risk_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()

        async def fake_fetch(_session, series_id: str, _days: int):
            if series_id == "VIXCLS":
                return _build_obs_series(+1.5)  # well above trend = stress
            return _build_obs_series(+0.0)  # HY-IG normal

        monkeypatch.setattr(
            "ichor_api.services.coach_macro_context_builder._fetch_fred_window",
            fake_fetch,
        )

        regime, evidence = await _classify_risk_regime(session)

        assert regime == "risk_off"
        assert len(evidence) == 2

    @pytest.mark.asyncio
    async def test_only_hy_above_threshold_yields_risk_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Credit-channel stress is sufficient by itself (asymmetry vs
        risk_on which requires BOTH channels calm)."""
        session = AsyncMock()

        async def fake_fetch(_session, series_id: str, _days: int):
            if series_id == "VIXCLS":
                return _build_obs_series(+0.0)  # vol calm
            return _build_obs_series(+1.5)  # credit stress

        monkeypatch.setattr(
            "ichor_api.services.coach_macro_context_builder._fetch_fred_window",
            fake_fetch,
        )

        regime, evidence = await _classify_risk_regime(session)

        assert regime == "risk_off"


class TestR168RiskRegimeTransitional:
    """``transitional`` is the doctrine #11 honest-default. Returned when
    neither indicator crosses ±0.7σ OR when data is insufficient."""

    @pytest.mark.asyncio
    async def test_both_z_near_zero_yields_transitional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()

        async def fake_fetch(_session, series_id: str, _days: int):
            return _build_obs_series(+0.3)  # sub-threshold both directions

        monkeypatch.setattr(
            "ichor_api.services.coach_macro_context_builder._fetch_fred_window",
            fake_fetch,
        )

        regime, evidence = await _classify_risk_regime(session)

        assert regime == "transitional"
        assert len(evidence) == 2  # both classifiers ran

    @pytest.mark.asyncio
    async def test_no_data_both_series_yields_transitional_empty_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When BOTH series have insufficient data (<30 obs), the
        classifier returns transitional + empty evidence. Doctrine #11
        honest absence — never fabricate a regime."""
        session = AsyncMock()

        async def fake_fetch(_session, series_id: str, _days: int):
            return []  # empty observation list

        monkeypatch.setattr(
            "ichor_api.services.coach_macro_context_builder._fetch_fred_window",
            fake_fetch,
        )

        regime, evidence = await _classify_risk_regime(session)

        assert regime == "transitional"
        assert evidence == []


class TestR168RiskRegimeThresholdConstants:
    """Pin the threshold constants. Drift would be caught either way
    (the dispatch tests above use ±1.5σ which is well past ±0.7σ), but
    pinning the constants directly catches accidental edits to the
    threshold values without an accompanying test update."""

    def test_risk_on_threshold_is_minus_zero_point_seven(self) -> None:
        """-0.7σ ≈ bottom 25th-percentile of 1y rolling history."""
        assert _RISK_REGIME_Z_RISK_ON == -0.7

    def test_risk_off_threshold_is_plus_zero_point_seven(self) -> None:
        """+0.7σ ≈ top 25th-percentile of 1y rolling history."""
        assert _RISK_REGIME_Z_RISK_OFF == +0.7

    def test_thresholds_are_symmetric_around_zero(self) -> None:
        """Symmetry guard : the |risk_on| boundary must equal the
        |risk_off| boundary so the classifier doesn't have a directional
        bias in its 'transitional' band."""
        assert abs(_RISK_REGIME_Z_RISK_ON) == abs(_RISK_REGIME_Z_RISK_OFF)


# ── CI invariant : every RiskRegime value reachable from classifier ──


def test_risk_regime_literal_lockstep_with_classifier_dispatch() -> None:
    """Pin the 3 RiskRegime Literal values vs the classifier's possible
    return values. Adding a new Literal without a corresponding dispatch
    branch must fail this test (mechanical W90-style invariant)."""
    from ichor_brain.coach_macro_context import RiskRegime

    declared = set(RiskRegime.__args__)  # type: ignore[attr-defined]
    dispatched = {"risk_on", "risk_off", "transitional"}
    missing = declared - dispatched
    extra = dispatched - declared
    assert not missing, f"RiskRegime Literal values not reachable from dispatch: {sorted(missing)}"
    assert not extra, f"Dispatch returns values not in RiskRegime Literal: {sorted(extra)}"
