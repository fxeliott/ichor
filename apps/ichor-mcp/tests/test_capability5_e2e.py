"""Capability 5 STEP-6 — end-to-end integration test for the MCP server.

This is the missing piece from ADR-071's 6-step sequence. The unit tests
in `test_client.py` cover the `ToolApiClient` wire to `/v1/tools/*` and
the static `_build_tools()` descriptors. What was NOT covered :

  ┌─────────────────────────────────────────────────────────────────┐
  │ MCP client (in-memory)                                          │
  │   ─→ session.call_tool("calc", {...})                           │
  │      ─→ ichor_mcp.server._call_tool() handler                   │
  │         ─→ ToolApiClient.calc() / .query_db()                   │
  │            ─→ httpx POST /v1/tools/{calc,query_db}              │
  │               ─→ response payload                               │
  │            ─← unwrap to dict                                    │
  │         ─← wrap as MCP TextContent JSON                         │
  │      ─← CallToolResult                                          │
  └─────────────────────────────────────────────────────────────────┘

The `mcp.shared.memory.create_connected_server_and_client_session`
helper is the official 2026 pattern (mcp 1.27+) — it wires read/write
memory streams between a `Server` instance and a `ClientSession`, so we
exercise the FULL protocol layer (initialize handshake, list_tools,
call_tool framing, content unwrap) without spawning a subprocess or
opening a socket. Cross-platform safe (CI runs Linux + macOS + the dev
loop runs Windows), no port collisions, no zombies.

The httpx side is mocked by `respx`. Combined, the test proves :

  - The static tool descriptors round-trip through the protocol
    (`list_tools()` returns 2 tools with audit fields in inputSchema).
  - `call_tool("calc", ...)` invokes the real handler → real client →
    real httpx → mocked apps/api endpoint, with the request body shape
    exactly matching what `apps/api/tests/test_tools_router.py` expects.
  - The handler wraps the apps/api JSON response as a single MCP
    `TextContent` (json.dumps blob), per the audit-first error pattern.
  - The validation rejection path returns an error-shaped TextContent
    (not a thrown exception) so the model can self-correct mid-loop.

NOT covered by this test (intentionally) :
  - The actual subprocess spawn of `python -m ichor_mcp.server` —
    that's `apps/ichor-mcp` packaging concern, not protocol.
  - The Claude CLI `--mcp-config` + `--allowedTools` flag wiring —
    that's `apps/claude-runner` STEP-4 territory (test_subprocess_runner.py).
  - The orchestrator's `ToolConfig` → `RunnerCall.tools` plumbing —
    that's STEP-5 territory
    (packages/ichor_brain/tests/test_orchestrator_tool_wiring.py).

Together those three suites + this one form the full Capability 5
green-path coverage for the 6-step ADR-071 sequence.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx
from ichor_mcp.config import Settings
from ichor_mcp.server import _make_server
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_settings_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """W100b — `ichor_mcp.config._settings` is a module-level cache so
    `get_settings()` returns a Settings instance built once and reused.

    Across tests (especially in parallel runs via pytest-xdist or when
    other test files in the suite import the module BEFORE the patches
    here are applied), the cached singleton can leak the wrong base_url
    / token into a later test. Reset before AND after each test so we
    always start from a clean slate."""
    import ichor_mcp.config as _cfg

    monkeypatch.setattr(_cfg, "_settings", None)


@pytest.fixture
def mock_settings() -> Settings:
    """Settings the in-memory server will see during the test run.

    Pinned `api_base_url` is the host respx will intercept. Service
    token is set so the X-Ichor-Tool-Token header is emitted (round-
    trip checked downstream)."""
    return Settings(
        api_base_url="https://api.test",
        api_service_token="dummy-token",
        cf_access_client_id="",
        cf_access_client_secret="",
        environment="development",
    )


# ── Protocol-level e2e ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_list_tools_returns_canonical_two(mock_settings: Settings) -> None:
    """End-to-end : a client connected via in-memory transport asks
    `list_tools` and receives the canonical 2-tool set, with their
    inputSchema intact (audit fields, hard caps, enum)."""
    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.list_tools()

    names = {t.name for t in result.tools}
    assert names == {"query_db", "calc"}

    # Verify the protocol round-trips the audit fields + hard caps.
    calc_tool = next(t for t in result.tools if t.name == "calc")
    enum = calc_tool.inputSchema["properties"]["operation"]["enum"]
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
    assert "agent_kind" in calc_tool.inputSchema["properties"]
    assert "pass_index" in calc_tool.inputSchema["properties"]
    assert "session_card_id" in calc_tool.inputSchema["properties"]

    qd_tool = next(t for t in result.tools if t.name == "query_db")
    assert qd_tool.inputSchema["properties"]["max_rows"]["maximum"] == 1000


@respx.mock
@pytest.mark.asyncio
async def test_e2e_calc_happy_path_full_chain(mock_settings: Settings) -> None:
    """Full chain : MCP client → server handler → ToolApiClient →
    mocked apps/api. Asserts (a) wire body shape, (b) X-Ichor-Tool-Token
    header round-trip, (c) response wrapped as a single TextContent."""
    route = respx.post("https://api.test/v1/tools/calc").mock(
        return_value=httpx.Response(
            200,
            json={"result": [10.0, 15.0, 22.5], "duration_ms": 3},
        )
    )

    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                "calc",
                {
                    "operation": "ewma",
                    "values": [10.0, 20.0, 30.0],
                    "params": {"alpha": 0.5},
                    "agent_kind": "pass2_asset",
                    "pass_index": 2,
                    "session_card_id": "11111111-2222-3333-4444-555555555555",
                },
            )

    # (a) Wire was actually called.
    assert route.called, "MCP server did not forward the call to /v1/tools/calc"

    # (b) Request body matches the apps/api ToolCalcIn shape exactly.
    body = json.loads(route.calls[0].request.read().decode("utf-8"))
    assert body["operation"] == "ewma"
    assert body["values"] == [10.0, 20.0, 30.0]
    assert body["params"] == {"alpha": 0.5}
    assert body["agent_kind"] == "pass2_asset"
    assert body["pass_index"] == 2
    assert body["session_card_id"] == "11111111-2222-3333-4444-555555555555"

    # Service token header round-tripped through the MCP server lifespan.
    assert route.calls[0].request.headers.get("X-Ichor-Tool-Token") == "dummy-token"

    # (c) Response wrapped as ONE TextContent block containing JSON.
    assert isinstance(result, types.CallToolResult)
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    parsed = json.loads(content.text)
    assert parsed["result"] == [10.0, 15.0, 22.5]
    assert parsed["duration_ms"] == 3


@respx.mock
@pytest.mark.asyncio
async def test_e2e_query_db_happy_path_full_chain(mock_settings: Settings) -> None:
    """Same green-path but on the query_db tool. The body shape differs
    (sql + max_rows instead of operation + values + params)."""
    route = respx.post("https://api.test/v1/tools/query_db").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"asset": "EURUSD", "ts": "2026-05-10"}],
                "duration_ms": 18,
                "tables_referenced": ["session_card_audit"],
                "truncated": False,
            },
        )
    )

    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                "query_db",
                {
                    "sql": "SELECT asset, ts FROM session_card_audit LIMIT 1",
                    "max_rows": 1,
                    "agent_kind": "pass1_regime",
                    "pass_index": 1,
                },
            )

    assert route.called
    body = json.loads(route.calls[0].request.read().decode("utf-8"))
    assert body["sql"].startswith("SELECT asset")
    assert body["max_rows"] == 1
    assert body["agent_kind"] == "pass1_regime"
    assert body["pass_index"] == 1
    assert "session_card_id" not in body  # null elided by ToolApiClient

    assert isinstance(result, types.CallToolResult)
    parsed = json.loads(result.content[0].text)
    assert parsed["rows"] == [{"asset": "EURUSD", "ts": "2026-05-10"}]
    assert parsed["tables_referenced"] == ["session_card_audit"]


# ── Error paths (audit-first, never throw to client) ───────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_query_db_validation_rejection_returns_error_text(
    mock_settings: Settings,
) -> None:
    """When apps/api rejects the SQL (validation rejected the
    statement), the MCP handler MUST NOT raise — it returns a
    TextContent with the error JSON so the model can self-correct."""
    respx.post("https://api.test/v1/tools/query_db").mock(
        return_value=httpx.Response(
            400,
            json={"detail": "validation rejected: forbidden table 'trader_notes'"},
        )
    )

    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                "query_db",
                {
                    "sql": "SELECT * FROM trader_notes",
                    "agent_kind": "manual",
                    "pass_index": 1,
                },
            )

    assert isinstance(result, types.CallToolResult)
    payload = json.loads(result.content[0].text)
    assert payload["status_code"] == 400
    assert "validation rejected" in payload["error"]
    assert payload["tool"] == "query_db"


@respx.mock
@pytest.mark.asyncio
async def test_e2e_calc_bad_input_returns_error_text(mock_settings: Settings) -> None:
    """Same audit-first behaviour on `calc`.

    We use `correlation` with no `other` param — this PASSES the MCP
    framework's inputSchema validation (operation is in the enum,
    values is a non-empty array) but apps/api rejects it with 400
    because `params.other` is required for correlation. So the request
    actually reaches our handler, ToolApiClient raises ToolApiError,
    and we round-trip the structured error TextContent.

    (An unknown `operation` would be rejected upstream by the SDK
    schema validator with a plaintext error and `isError=True`, never
    reaching our handler — that's a separate defense layer covered by
    `test_e2e_input_schema_rejects_unknown_operation_upstream`.)"""
    respx.post("https://api.test/v1/tools/calc").mock(
        return_value=httpx.Response(
            400,
            json={"detail": "ToolCalcError: correlation: `params.other` is required"},
        )
    )

    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                "calc",
                {
                    "operation": "correlation",
                    "values": [1.0, 2.0, 3.0, 4.0],
                    "agent_kind": "manual",
                    "pass_index": 1,
                },
            )

    payload = json.loads(result.content[0].text)
    assert payload["status_code"] == 400
    assert "params.other" in payload["error"] or "correlation" in payload["error"]
    assert payload["tool"] == "calc"


@pytest.mark.asyncio
async def test_e2e_input_schema_rejects_unknown_operation_upstream(
    mock_settings: Settings,
) -> None:
    """Defense layer 1 : the MCP SDK validates the call's arguments
    against `inputSchema` BEFORE the handler runs. An operation outside
    the 9-element enum is rejected at the protocol layer with
    `isError=True` and a plaintext "Input validation error" message
    — our handler is never reached, no httpx POST is made.

    Useful because :
      - it proves the inputSchema we ship is actually enforced (drift
        guard : if someone removes the enum, this test fails).
      - it documents the layered defense for future readers."""
    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                "calc",
                {
                    "operation": "frobnicate",  # not in enum
                    "values": [1.0, 2.0],
                },
            )

    assert isinstance(result, types.CallToolResult)
    assert result.isError is True
    assert isinstance(result.content[0], types.TextContent)
    text = result.content[0].text
    assert "Input validation error" in text
    assert "frobnicate" in text
    # All 9 supported ops named explicitly so the model can self-correct.
    for op in ("zscore", "ewma", "correlation"):
        assert op in text


@respx.mock
@pytest.mark.asyncio
async def test_e2e_network_failure_returns_error_text(mock_settings: Settings) -> None:
    """If apps/api is unreachable (DNS / TCP failure), the handler must
    surface a 599 error TextContent — never a crash mid-tool-call."""
    respx.post("https://api.test/v1/tools/calc").mock(
        side_effect=httpx.ConnectError("DNS lookup failed")
    )

    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                "calc",
                {
                    "operation": "zscore",
                    "values": [1.0, 2.0, 3.0],
                    "agent_kind": "manual",
                    "pass_index": 1,
                },
            )

    payload = json.loads(result.content[0].text)
    assert payload["status_code"] == 599
    assert "network error" in payload["error"] or "ConnectError" in payload["error"]


# ── Defense-in-depth : unknown tool name ───────────────────────────


@pytest.mark.asyncio
async def test_e2e_unknown_tool_returns_error_not_crash(mock_settings: Settings) -> None:
    """W100b — empirical assertion (was previously a vague try/except).

    The MCP SDK 1.27 does NOT reject unknown tool names upstream — it
    forwards the call to our handler, which guards via the `name not
    in tool_index` check in server.py:209-217 and returns a single
    TextContent JSON `{"error": "unknown tool '...'. known: [...]"}`.

    The result is shaped as a normal `CallToolResult` (no exception
    raised, no `isError=True` flag — the SDK only sets isError on its
    own schema-validation failures, not on handler-returned errors).

    This test pins that contract :
      1. NO Python exception leaks across `session.call_tool()`.
      2. The result is a `CallToolResult`.
      3. The content is exactly one `TextContent` with parseable JSON.
      4. The JSON has an "error" key naming the unknown tool AND the
         known tool list (so the model can self-correct).

    If a future SDK upgrade flips this (e.g. starts rejecting unknown
    names upstream with isError=True), this test fails loudly — that's
    a contract break we want to know about, not silently absorb."""
    with patch("ichor_mcp.server.get_settings", return_value=mock_settings):
        server = _make_server()
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool("not_a_real_tool", {})

    # (1) No exception (assertion implicit: if call_tool raised, we
    # never reach this line — pytest marks the test failed).
    # (2) Shape.
    assert isinstance(result, types.CallToolResult)
    assert len(result.content) == 1
    assert isinstance(result.content[0], types.TextContent)

    # (3 + 4) Content.
    payload = json.loads(result.content[0].text)
    assert "unknown tool" in payload["error"]
    assert "not_a_real_tool" in payload["error"]
    # Both real tool names listed so the model knows what's available.
    assert "query_db" in payload["error"]
    assert "calc" in payload["error"]
