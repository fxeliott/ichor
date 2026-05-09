"""Smoke tests for /v1/tools/* (Capability 5 STEP-3 wire, ADR-077).

Mocks the underlying services (`execute_query`, `calc`) and the audit
sessionmaker so we exercise the router's three concerns without
touching Postgres :

  1. Validation rejection / runtime error → correct HTTP status.
  2. Audit row built with the right shape on every path.
  3. `X-Ichor-Tool-Token` enforcement (bypass when settings empty,
     401 when token wrong, 200 when token matches).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ichor_api.main import app
from ichor_api.routers import tools as tools_router
from ichor_api.services.tool_query_db import ToolQueryDbError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def captured_audit_rows(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the audit sessionmaker with a stub that captures rows.

    Returns a list that fills as the route runs. Each entry is the
    kwargs that built the `ToolCallAudit` row — which is what we want
    to assert on.
    """
    captured: list[dict[str, Any]] = []

    class _AuditSession:
        def add(self, row) -> None:
            captured.append(
                {
                    "agent_kind": row.agent_kind,
                    "pass_index": row.pass_index,
                    "tool_name": row.tool_name,
                    "tool_input": row.tool_input,
                    "tool_output": row.tool_output,
                    "duration_ms": row.duration_ms,
                    "error": row.error,
                    "session_card_id": row.session_card_id,
                }
            )

        async def commit(self) -> None:
            return None

    @asynccontextmanager
    async def _ctx():
        yield _AuditSession()

    fake_sm = MagicMock()
    fake_sm.return_value = _ctx()
    monkeypatch.setattr(tools_router, "get_sessionmaker", lambda: fake_sm)
    return captured


# ── /v1/tools/query_db ─────────────────────────────────────────────


def test_query_db_happy_path(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rows = [{"asset": "EURUSD", "conviction": 0.81}]
    monkeypatch.setattr(tools_router, "execute_query", AsyncMock(return_value=fake_rows))

    resp = client.post(
        "/v1/tools/query_db",
        json={
            "sql": "SELECT asset, conviction FROM session_card_audit LIMIT 5",
            "max_rows": 5,
            "agent_kind": "pass1_regime",
            "pass_index": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == fake_rows
    assert body["tables_referenced"] == ["session_card_audit"]
    assert body["truncated"] is False  # len(rows)=1 < cap=5
    assert isinstance(body["duration_ms"], int)

    # Audit row shape
    assert len(captured_audit_rows) == 1
    audit = captured_audit_rows[0]
    assert audit["tool_name"] == "mcp__ichor__query_db"
    assert audit["agent_kind"] == "pass1_regime"
    assert audit["pass_index"] == 1
    assert audit["error"] is None
    assert audit["tool_output"]["row_count"] == 1
    assert audit["tool_output"]["tables_referenced"] == ["session_card_audit"]


def test_query_db_validation_rejection_returns_400_and_audits(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
) -> None:
    resp = client.post(
        "/v1/tools/query_db",
        json={
            "sql": "DROP TABLE session_card_audit",
            "agent_kind": "manual",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "validation rejected" in resp.json()["detail"].lower()

    assert len(captured_audit_rows) == 1
    audit = captured_audit_rows[0]
    assert audit["tool_output"] is None
    assert "validation rejected" in audit["error"]


def test_query_db_runtime_error_returns_500_and_audits(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools_router,
        "execute_query",
        AsyncMock(side_effect=ToolQueryDbError("execution failure: OperationalError: ...")),
    )

    resp = client.post(
        "/v1/tools/query_db",
        json={
            "sql": "SELECT * FROM alerts LIMIT 1",
            "agent_kind": "pass4_invalidation",
            "pass_index": 4,
        },
    )
    assert resp.status_code == 500
    assert len(captured_audit_rows) == 1
    audit = captured_audit_rows[0]
    assert audit["error"] is not None
    assert audit["agent_kind"] == "pass4_invalidation"
    assert audit["pass_index"] == 4
    assert audit["tool_output"] is None


def test_query_db_max_rows_clamped_in_request(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
) -> None:
    """Pydantic guard — `max_rows` field has le=1000."""
    resp = client.post(
        "/v1/tools/query_db",
        json={"sql": "SELECT * FROM alerts", "max_rows": 999_999},
    )
    assert resp.status_code == 422  # Pydantic validation


def test_query_db_session_card_id_round_trips(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tools_router, "execute_query", AsyncMock(return_value=[]))
    sid = str(uuid4())
    resp = client.post(
        "/v1/tools/query_db",
        json={
            "sql": "SELECT * FROM alerts LIMIT 1",
            "agent_kind": "pass5_counterfactual",
            "pass_index": 5,
            "session_card_id": sid,
        },
    )
    assert resp.status_code == 200
    audit = captured_audit_rows[0]
    assert str(audit["session_card_id"]) == sid


# ── /v1/tools/calc ─────────────────────────────────────────────────


def test_calc_happy_path_scalar(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
) -> None:
    """percentile returns a scalar float."""
    resp = client.post(
        "/v1/tools/calc",
        json={
            "operation": "percentile",
            "values": [10.0, 20.0, 30.0, 40.0, 50.0],
            "params": {"k": 50},
            "agent_kind": "pass2_asset",
            "pass_index": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"] == 30.0
    assert isinstance(body["duration_ms"], int)

    audit = captured_audit_rows[0]
    assert audit["tool_name"] == "mcp__ichor__calc"
    assert audit["error"] is None
    assert audit["tool_output"]["result_kind"] == "scalar"
    assert audit["tool_output"]["result_len"] is None


def test_calc_happy_path_array(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
) -> None:
    """zscore returns list[float]."""
    resp = client.post(
        "/v1/tools/calc",
        json={
            "operation": "zscore",
            "values": [1.0, 2.0, 3.0, 4.0, 5.0],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["result"], list)
    assert len(body["result"]) == 5

    audit = captured_audit_rows[0]
    assert audit["tool_output"]["result_kind"] == "array"
    assert audit["tool_output"]["result_len"] == 5
    assert audit["tool_input"]["values_len"] == 5


def test_calc_unknown_op_returns_400_and_audits(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
) -> None:
    resp = client.post(
        "/v1/tools/calc",
        json={
            "operation": "not_a_real_op",
            "values": [1.0, 2.0],
        },
    )
    assert resp.status_code == 400
    assert "unknown operation" in resp.json()["detail"].lower()
    assert len(captured_audit_rows) == 1
    assert captured_audit_rows[0]["error"] is not None
    assert captured_audit_rows[0]["tool_output"] is None


def test_calc_missing_required_param_returns_400(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
) -> None:
    """percentile without `k` is a tool-level error, not pydantic."""
    resp = client.post(
        "/v1/tools/calc",
        json={
            "operation": "percentile",
            "values": [1.0, 2.0, 3.0],
            "params": {},
        },
    )
    assert resp.status_code == 400
    audit = captured_audit_rows[0]
    assert "params.k" in audit["error"] or "k " in audit["error"]


def test_calc_empty_values_rejected_by_pydantic(
    client: TestClient,
) -> None:
    """`values: list[float] = Field(min_length=1)` — pydantic catches it."""
    resp = client.post(
        "/v1/tools/calc",
        json={"operation": "zscore", "values": []},
    )
    assert resp.status_code == 422


# ── Auth / X-Ichor-Tool-Token ──────────────────────────────────────


def test_token_bypass_when_settings_empty(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default test settings have empty `tool_service_token` → bypass."""
    monkeypatch.setattr(tools_router, "execute_query", AsyncMock(return_value=[]))
    resp = client.post(
        "/v1/tools/query_db",
        json={"sql": "SELECT * FROM alerts LIMIT 1"},
    )
    assert resp.status_code == 200


def test_token_required_when_settings_set(
    client: TestClient,
    captured_audit_rows: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ichor_api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "tool_service_token", "expected-secret-123")

    # No header → 401
    resp_no_hdr = client.post(
        "/v1/tools/calc",
        json={"operation": "zscore", "values": [1.0, 2.0]},
    )
    assert resp_no_hdr.status_code == 401

    # Wrong token → 401
    resp_bad = client.post(
        "/v1/tools/calc",
        json={"operation": "zscore", "values": [1.0, 2.0]},
        headers={"X-Ichor-Tool-Token": "wrong"},
    )
    assert resp_bad.status_code == 401

    # Right token → 200
    resp_ok = client.post(
        "/v1/tools/calc",
        json={"operation": "zscore", "values": [1.0, 2.0]},
        headers={"X-Ichor-Tool-Token": "expected-secret-123"},
    )
    assert resp_ok.status_code == 200
