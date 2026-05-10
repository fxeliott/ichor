"""Unit tests for the apps/ichor-mcp httpx client + tool descriptors.

Uses `respx` to stub `https://api.fxmilyapp.com/v1/tools/*` so we
exercise:
  - request body shape (correct keys forwarded)
  - response unwrapping
  - non-2xx → `ToolApiError(status, detail)`
  - network failure → `ToolApiError(599, ...)`
  - header injection (X-Ichor-Tool-Token + CF-Access-*)

The MCP server's `_call_tool` handler is exercised via integration
(claude CLI handshake) — kept out of unit tests because mocking
`ServerRequestContext.lifespan_context` is tightly coupled to the
SDK's internals.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from ichor_mcp.client import ToolApiClient, ToolApiError
from ichor_mcp.config import Settings
from ichor_mcp.server import _build_tools

# ── Tool descriptors ───────────────────────────────────────────────


def test_build_tools_returns_two_tools() -> None:
    tools = _build_tools()
    assert {t.name for t in tools} == {"query_db", "calc"}


def test_query_db_schema_has_audit_fields() -> None:
    tools = _build_tools()
    qd = next(t for t in tools if t.name == "query_db")
    schema = qd.inputSchema
    assert schema["required"] == ["sql"]
    assert "agent_kind" in schema["properties"]
    assert "pass_index" in schema["properties"]
    assert "session_card_id" in schema["properties"]
    assert schema["additionalProperties"] is False
    # Hard cap surfaced to the model.
    assert schema["properties"]["max_rows"]["maximum"] == 1000


def test_calc_schema_lists_nine_ops() -> None:
    tools = _build_tools()
    cc = next(t for t in tools if t.name == "calc")
    enum = cc.inputSchema["properties"]["operation"]["enum"]
    assert set(enum) == {
        "zscore",
        "rolling_mean",
        "rolling_std",
        "pct_change",
        "log_returns",
        "correlation",
        "percentile",
        "ewma",
        "annualize_vol",
    }


# ── Headers ────────────────────────────────────────────────────────


def test_service_token_header_emitted_when_set() -> None:
    s = Settings(api_service_token="secret-abc")
    client = ToolApiClient(s)
    assert client._client.headers.get("X-Ichor-Tool-Token") == "secret-abc"


def test_no_service_token_header_when_empty() -> None:
    s = Settings(api_service_token="")
    client = ToolApiClient(s)
    assert "X-Ichor-Tool-Token" not in client._client.headers


def test_cf_access_headers_emitted_when_both_set() -> None:
    s = Settings(
        cf_access_client_id="cid",
        cf_access_client_secret="csecret",
    )
    client = ToolApiClient(s)
    assert client._client.headers["CF-Access-Client-Id"] == "cid"
    assert client._client.headers["CF-Access-Client-Secret"] == "csecret"


def test_cf_access_skipped_when_only_one_set() -> None:
    s = Settings(cf_access_client_id="cid", cf_access_client_secret="")
    client = ToolApiClient(s)
    assert "CF-Access-Client-Id" not in client._client.headers


# ── query_db wire ──────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_query_db_happy_path() -> None:
    s = Settings(api_base_url="https://api.test", api_service_token="tok")
    client = ToolApiClient(s)

    route = respx.post("https://api.test/v1/tools/query_db").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"asset": "EURUSD"}],
                "duration_ms": 12,
                "tables_referenced": ["session_card_audit"],
                "truncated": False,
            },
        )
    )

    out = await client.query_db(
        sql="SELECT asset FROM session_card_audit LIMIT 1",
        max_rows=10,
        agent_kind="pass1_regime",
        pass_index=1,
        session_card_id=None,
    )
    await client.aclose()

    assert route.called
    sent_body = route.calls[0].request.read().decode("utf-8")
    import json as _json

    body = _json.loads(sent_body)
    assert body["sql"].startswith("SELECT")
    assert body["max_rows"] == 10
    assert body["agent_kind"] == "pass1_regime"
    assert body["pass_index"] == 1
    assert "session_card_id" not in body  # None elided

    assert out["rows"] == [{"asset": "EURUSD"}]
    # Service token round-tripped on the request.
    assert route.calls[0].request.headers.get("X-Ichor-Tool-Token") == "tok"


@respx.mock
@pytest.mark.asyncio
async def test_query_db_validation_rejection_raises() -> None:
    s = Settings(api_base_url="https://api.test")
    client = ToolApiClient(s)

    respx.post("https://api.test/v1/tools/query_db").mock(
        return_value=httpx.Response(400, json={"detail": "validation rejected: forbidden table(s)"})
    )

    with pytest.raises(ToolApiError) as excinfo:
        await client.query_db(
            sql="SELECT * FROM trader_notes",
            max_rows=None,
            agent_kind="manual",
            pass_index=1,
            session_card_id=None,
        )
    await client.aclose()
    assert excinfo.value.status_code == 400
    assert "validation rejected" in excinfo.value.detail


@respx.mock
@pytest.mark.asyncio
async def test_query_db_network_error_raises_599() -> None:
    s = Settings(api_base_url="https://api.test")
    client = ToolApiClient(s)

    respx.post("https://api.test/v1/tools/query_db").mock(
        side_effect=httpx.ConnectError("DNS lookup failed")
    )

    with pytest.raises(ToolApiError) as excinfo:
        await client.query_db(
            sql="SELECT 1 FROM alerts",
            max_rows=None,
            agent_kind="manual",
            pass_index=1,
            session_card_id=None,
        )
    await client.aclose()
    assert excinfo.value.status_code == 599
    assert "ConnectError" in excinfo.value.detail or "DNS" in excinfo.value.detail


# ── calc wire ──────────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_calc_happy_path_array() -> None:
    s = Settings(api_base_url="https://api.test")
    client = ToolApiClient(s)

    route = respx.post("https://api.test/v1/tools/calc").mock(
        return_value=httpx.Response(
            200,
            json={"result": [0.0, 0.1, 0.2], "duration_ms": 1},
        )
    )
    out = await client.calc(
        operation="rolling_mean",
        values=[1.0, 2.0, 3.0, 4.0],
        params={"window": 2},
        agent_kind="pass2_asset",
        pass_index=2,
        session_card_id="11111111-2222-3333-4444-555555555555",
    )
    await client.aclose()
    assert route.called
    import json as _json

    body = _json.loads(route.calls[0].request.read().decode("utf-8"))
    assert body["operation"] == "rolling_mean"
    assert body["params"] == {"window": 2}
    assert body["session_card_id"] == "11111111-2222-3333-4444-555555555555"
    assert out["result"] == [0.0, 0.1, 0.2]


@respx.mock
@pytest.mark.asyncio
async def test_calc_unknown_op_raises_400() -> None:
    s = Settings(api_base_url="https://api.test")
    client = ToolApiClient(s)

    respx.post("https://api.test/v1/tools/calc").mock(
        return_value=httpx.Response(400, json={"detail": "ToolCalcError: unknown operation 'foo'"})
    )
    with pytest.raises(ToolApiError) as excinfo:
        await client.calc(
            operation="foo",
            values=[1.0, 2.0],
            params={},
            agent_kind="manual",
            pass_index=1,
            session_card_id=None,
        )
    await client.aclose()
    assert excinfo.value.status_code == 400
    assert "unknown operation" in excinfo.value.detail
