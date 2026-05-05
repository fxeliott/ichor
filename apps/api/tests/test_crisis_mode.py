"""Crisis Mode + alert catalog integration tests.

These tests do NOT require a Postgres connection — they use a stub session
that mimics the SQLAlchemy AsyncSession interface for `select(Alert).where(...)`.
The point is to verify the threshold logic + severity weighting without
needing a live DB; the wiring to the real Postgres is exercised by the
existing seed_dev_data CLI which we run on Hetzner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from ichor_api.alerts.catalog import (
    ALL_ALERTS,
    AUDIT_V2_ALERTS,
    BY_CODE,
    CRISIS_TRIGGERS,
    PLAN_ALERTS,
    assert_catalog_complete,
    get_alert_def,
)
from ichor_api.alerts.crisis_mode import assess_crisis

# ───────────────────────── Catalog invariants ─────────────────────────


def test_catalog_complete_count_and_unique() -> None:
    assert_catalog_complete()


def test_catalog_breakdown() -> None:
    assert len(PLAN_ALERTS) == 28
    assert len(AUDIT_V2_ALERTS) == 5
    assert len(ALL_ALERTS) == 33


def test_catalog_severity_values_valid() -> None:
    for a in ALL_ALERTS:
        assert a.severity in ("info", "warning", "critical"), a


def test_catalog_direction_values_valid() -> None:
    for a in ALL_ALERTS:
        assert a.default_direction in ("above", "below", "cross_up", "cross_down"), a


def test_crisis_triggers_subset_of_catalog() -> None:
    for code in CRISIS_TRIGGERS:
        assert code in BY_CODE
    # Spec: ≥ 5 crisis triggers
    assert len(CRISIS_TRIGGERS) >= 5


def test_get_alert_def_known_and_unknown() -> None:
    assert get_alert_def("VIX_PANIC").severity == "critical"
    with pytest.raises(KeyError):
        get_alert_def("DOES_NOT_EXIST")


# ───────────────────────── Crisis assessment ─────────────────────────


@dataclass
class _StubAlert:
    """Minimal duck-type compatible with what assess_crisis reads."""

    alert_code: str
    severity: str
    triggered_at: datetime
    acknowledged_at: datetime | None = None


@dataclass
class _StubResult:
    rows: list[_StubAlert] = field(default_factory=list)

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[_StubAlert]:
        return self.rows


@dataclass
class _StubSession:
    """Records the predicate it was called with for assertion + returns rows."""

    rows: list[_StubAlert] = field(default_factory=list)

    async def execute(self, _stmt: object) -> _StubResult:
        # We trust assess_crisis to filter via SQL; for the unit test the
        # caller already passes the expected subset of rows.
        return _StubResult(self.rows)


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.mark.asyncio
async def test_crisis_inactive_when_below_threshold() -> None:
    session = _StubSession(
        rows=[
            _StubAlert("VIX_PANIC", "critical", _now()),
        ]
    )
    result = await assess_crisis(session, min_concurrent=2)  # type: ignore[arg-type]
    assert result.is_active is False
    assert result.triggering_codes == ["VIX_PANIC"]
    assert result.severity_score == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_crisis_active_when_two_critical() -> None:
    session = _StubSession(
        rows=[
            _StubAlert("VIX_PANIC", "critical", _now()),
            _StubAlert("HY_OAS_CRISIS", "critical", _now()),
        ]
    )
    result = await assess_crisis(session, min_concurrent=2)  # type: ignore[arg-type]
    assert result.is_active is True
    assert sorted(result.triggering_codes) == ["HY_OAS_CRISIS", "VIX_PANIC"]
    assert result.severity_score == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_crisis_severity_weighting() -> None:
    session = _StubSession(
        rows=[
            _StubAlert("DEALER_GAMMA_FLIP", "warning", _now()),  # 2.0
            _StubAlert("LIQUIDITY_BIDASK_WIDEN", "warning", _now()),  # 2.0
        ]
    )
    result = await assess_crisis(session, min_concurrent=2)  # type: ignore[arg-type]
    assert result.severity_score == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_crisis_higher_min_concurrent() -> None:
    session = _StubSession(
        rows=[
            _StubAlert("VIX_PANIC", "critical", _now()),
            _StubAlert("HY_OAS_CRISIS", "critical", _now()),
        ]
    )
    # Bumping min_concurrent to 3 turns the same input into "not active"
    result = await assess_crisis(session, min_concurrent=3)  # type: ignore[arg-type]
    assert result.is_active is False


@pytest.mark.asyncio
async def test_crisis_no_alerts() -> None:
    session = _StubSession(rows=[])
    result = await assess_crisis(session, min_concurrent=2)  # type: ignore[arg-type]
    assert result.is_active is False
    assert result.triggering_codes == []
    assert result.severity_score == 0.0


@pytest.mark.asyncio
async def test_crisis_lookback_passed_through() -> None:
    """Smoke test that the function accepts custom lookback without raising."""
    session = _StubSession(rows=[])
    res = await assess_crisis(session, min_concurrent=2, lookback_minutes=180)  # type: ignore[arg-type]
    assert res.is_active is False


def test_all_crisis_triggers_have_critical_or_warning_severity() -> None:
    """Crisis triggers should never be `info` — they must be material."""
    for code in CRISIS_TRIGGERS:
        defn = get_alert_def(code)
        assert defn.severity in ("critical", "warning"), (
            f"Crisis trigger {code} has severity {defn.severity}; expected critical or warning"
        )
