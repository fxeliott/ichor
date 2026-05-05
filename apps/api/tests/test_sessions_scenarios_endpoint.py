"""Tests for /v1/sessions/{asset}/scenarios endpoint.

Mocks the AsyncSession via dependency_override so we don't need a live DB.
The router calls `extract_pass4_scenarios(row.mechanisms)` — these tests
exercise the wiring + edge cases (no row, malformed JSONB, valid 7-tree).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.main import app


def _scenario_dict(*, sid: str, proba: float = 0.20) -> dict[str, object]:
    return {
        "id": sid,
        "label": f"scenario {sid}",
        "probability": proba,
        "bias": "bull",
        "magnitude_pips": {"low": 18, "high": 32},
        "primary_mechanism": "test mechanism",
        "invalidation": "close H1 < threshold",
    }


def _card(*, mechanisms: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        generated_at=datetime(2026, 5, 5, 7, 0, tzinfo=UTC),
        session_type="pre_londres",
        asset="EUR_USD",
        model_id="claude-opus-4-7",
        regime_quadrant="goldilocks",
        bias_direction="long",
        conviction_pct=72.0,
        magnitude_pips_low=18.0,
        magnitude_pips_high=32.0,
        timing_window_start=None,
        timing_window_end=None,
        mechanisms=mechanisms,
        invalidations=None,
        catalysts=None,
        correlations_snapshot=None,
        polymarket_overlay=None,
        source_pool_hash="d" * 64,
        critic_verdict="approved",
        critic_findings=None,
        claude_duration_ms=14500,
        realized_close_session=None,
        realized_at=None,
        brier_contribution=None,
        created_at=datetime(2026, 5, 5, 7, 5, tzinfo=UTC),
    )


class _StubResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def scalar_one_or_none(self):  # type: ignore[no-untyped-def]
        return self._row


class _StubSession:
    def __init__(self, row: object | None) -> None:
        self._row = row

    async def execute(self, stmt: object) -> _StubResult:
        return _StubResult(self._row)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _override_session(row: object | None) -> None:
    async def _gen():
        yield _StubSession(row)

    app.dependency_overrides[get_session] = _gen


def _clear_override() -> None:
    app.dependency_overrides.pop(get_session, None)


def test_returns_empty_tree_when_no_card_for_asset(client: TestClient) -> None:
    _override_session(None)
    try:
        r = client.get("/v1/sessions/EUR_USD/scenarios")
        assert r.status_code == 200
        body = r.json()
        assert body["asset"] == "EUR_USD"
        assert body["n_scenarios"] == 0
        assert body["sum_probability"] == 0.0
        assert body["scenarios"] == []
        assert body["session_card_id"] is None
        assert body["tail_padded"] is False
    finally:
        _clear_override()


def test_returns_empty_tree_when_mechanisms_is_none(client: TestClient) -> None:
    _override_session(_card(mechanisms=None))
    try:
        r = client.get("/v1/sessions/EUR_USD/scenarios")
        assert r.status_code == 200
        body = r.json()
        assert body["n_scenarios"] == 0
        # The card existed → session_card_id must be populated
        assert body["session_card_id"] is not None
    finally:
        _clear_override()


def test_returns_seven_scenario_tree_when_jsonb_is_canonical(
    client: TestClient,
) -> None:
    mechanisms = [_scenario_dict(sid=f"s{i}", proba=1.0 / 7) for i in range(1, 8)]
    _override_session(_card(mechanisms=mechanisms))
    try:
        r = client.get("/v1/sessions/EUR_USD/scenarios")
        assert r.status_code == 200
        body = r.json()
        assert body["n_scenarios"] == 7
        assert abs(body["sum_probability"] - 1.0) < 0.05
        assert body["tail_padded"] is False  # 7 → canonical
        assert len(body["scenarios"]) == 7
        assert {s["id"] for s in body["scenarios"]} == {f"s{i}" for i in range(1, 8)}
    finally:
        _clear_override()


def test_tail_padded_flag_when_fewer_than_seven(client: TestClient) -> None:
    mechanisms = [_scenario_dict(sid=f"s{i}", proba=0.20) for i in range(1, 4)]
    _override_session(_card(mechanisms=mechanisms))
    try:
        r = client.get("/v1/sessions/EUR_USD/scenarios")
        assert r.status_code == 200
        body = r.json()
        assert body["n_scenarios"] == 3
        assert body["tail_padded"] is True
    finally:
        _clear_override()


def test_accepts_dict_with_scenarios_key(client: TestClient) -> None:
    """Brain runner may persist {scenarios: [...]} or [...] at the root."""
    mechanisms = {
        "scenarios": [_scenario_dict(sid="s1", proba=0.32), _scenario_dict(sid="s2", proba=0.24)]
    }
    _override_session(_card(mechanisms=mechanisms))
    try:
        r = client.get("/v1/sessions/EUR_USD/scenarios")
        assert r.status_code == 200
        body = r.json()
        assert body["n_scenarios"] == 2
        assert {s["id"] for s in body["scenarios"]} == {"s1", "s2"}
    finally:
        _clear_override()


def test_skips_malformed_entries_silently(client: TestClient) -> None:
    mechanisms = [
        _scenario_dict(sid="s1"),
        {"id": "broken", "no_required_fields": True},  # missing fields
        _scenario_dict(sid="s2"),
    ]
    _override_session(_card(mechanisms=mechanisms))
    try:
        r = client.get("/v1/sessions/EUR_USD/scenarios")
        assert r.status_code == 200
        body = r.json()
        # The broken entry is filtered out
        assert body["n_scenarios"] == 2
        assert {s["id"] for s in body["scenarios"]} == {"s1", "s2"}
    finally:
        _clear_override()


def test_invalid_asset_slug_returns_400(client: TestClient) -> None:
    _override_session(None)
    try:
        # Lowercase + hyphens fail the regex
        r = client.get("/v1/sessions/eur-usd-bad/scenarios")
        assert r.status_code == 400
    finally:
        _clear_override()
