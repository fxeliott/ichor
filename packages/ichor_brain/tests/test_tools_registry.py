"""Tests for packages/ichor_brain/tools_registry.py — Capability-5 scaffold."""

from __future__ import annotations

import pytest
from ichor_brain.tools_registry import (
    BY_NAME,
    CALC,
    CAPABILITY_5_TOOLS,
    QUERY_DB,
    RAG_HISTORICAL,
    WEB_FETCH,
    WEB_SEARCH,
    ToolDef,
    _handler_calc,
    _handler_query_db,
    _handler_rag_historical,
    assert_registry_complete,
    get_tool,
    to_anthropic_tool_param,
    tools_for_pass,
)


def test_registry_has_exactly_5_tools():
    assert len(CAPABILITY_5_TOOLS) == 5


def test_registry_tool_names_unique():
    names = [t.name for t in CAPABILITY_5_TOOLS]
    assert len(names) == len(set(names))


def test_registry_known_tool_names():
    expected = {"web_search", "web_fetch", "query_db", "calc", "rag_historical"}
    actual = {t.name for t in CAPABILITY_5_TOOLS}
    assert actual == expected


def test_each_tool_declares_adr_017_constraint():
    for tool in CAPABILITY_5_TOOLS:
        assert tool.adr_017_constraint, f"Tool {tool.name!r} missing ADR-017 constraint"
        assert len(tool.adr_017_constraint) > 30, f"Tool {tool.name!r} ADR-017 constraint too brief"


def test_each_tool_has_description():
    for tool in CAPABILITY_5_TOOLS:
        assert tool.description, f"Tool {tool.name!r} missing description"


def test_server_vs_client_split():
    server_tools = [t for t in CAPABILITY_5_TOOLS if t.execution_model == "server"]
    client_tools = [t for t in CAPABILITY_5_TOOLS if t.execution_model == "client"]
    # 2 server (web_search, web_fetch) + 3 client (query_db, calc, rag_historical)
    assert len(server_tools) == 2
    assert len(client_tools) == 3
    server_names = {t.name for t in server_tools}
    assert server_names == {"web_search", "web_fetch"}


def test_get_tool_lookup():
    assert get_tool("web_search") is WEB_SEARCH
    assert get_tool("query_db") is QUERY_DB
    assert get_tool("calc") is CALC


def test_get_tool_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        get_tool("not_a_real_tool")


def test_tools_for_pass_validates_range():
    with pytest.raises(ValueError):
        tools_for_pass(0)
    with pytest.raises(ValueError):
        tools_for_pass(5)


def test_tools_for_pass_returns_subset():
    # Pass 1 (regime) should include web_search + query_db at minimum
    p1 = {t.name for t in tools_for_pass(1)}
    assert "web_search" in p1
    assert "query_db" in p1
    # rag_historical is in_scope_v1=False → excluded everywhere v1
    assert "rag_historical" not in p1


def test_rag_historical_deferred_v1():
    assert RAG_HISTORICAL.in_scope_v1 is False


def test_other_4_tools_in_scope_v1():
    for tool in (WEB_SEARCH, WEB_FETCH, QUERY_DB, CALC):
        assert tool.in_scope_v1 is True


def test_query_db_input_schema_has_required_query():
    schema = QUERY_DB.input_schema
    assert "query" in schema["required"]
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["type"] == "string"


def test_query_db_describes_sql_whitelist():
    """Critical : query_db must document the read-only SQL whitelist."""
    desc = QUERY_DB.input_schema["properties"]["query"]["description"]
    # Forbidden DML/DDL keywords must be listed in the description
    for verb in ("INSERT", "UPDATE", "DELETE", "DROP"):
        assert verb in desc.upper()


def test_calc_input_schema_enumerates_operations():
    ops = CALC.input_schema["properties"]["operation"]["enum"]
    # At least the canonical Phase E operations must be supported
    for op in ("zscore", "rolling_mean", "log_returns", "correlation", "annualize_vol"):
        assert op in ops


def test_to_anthropic_tool_param_client_format():
    # Client tools use {name, description, input_schema}
    rendered = to_anthropic_tool_param(QUERY_DB)
    assert rendered["name"] == "query_db"
    assert "description" in rendered
    assert "input_schema" in rendered


def test_to_anthropic_tool_param_server_format():
    # Server tools use Anthropic-reserved type
    rendered = to_anthropic_tool_param(WEB_SEARCH)
    assert rendered["name"] == "web_search"
    assert rendered["type"].startswith("server_tool_")


def test_handlers_are_placeholders_raising_not_implemented():
    # Phase D.0 scaffold contract : all client handlers must raise.
    with pytest.raises(NotImplementedError):
        _handler_query_db("SELECT 1")
    with pytest.raises(NotImplementedError):
        _handler_calc("zscore", [1.0, 2.0, 3.0])
    with pytest.raises(NotImplementedError):
        _handler_rag_historical({"vix": 17}, "SPX500_USD")


def test_assert_registry_complete_passes():
    # Should not raise.
    assert_registry_complete()


def test_by_name_dict_complete():
    assert set(BY_NAME) == {t.name for t in CAPABILITY_5_TOOLS}


def test_dataclass_frozen():
    # ToolDef is frozen — should not allow mutation
    with pytest.raises(Exception):  # FrozenInstanceError
        WEB_SEARCH.name = "mutated"  # type: ignore


def test_tooldef_default_values():
    t = ToolDef(
        name="x",
        description="y",
        input_schema={},
        execution_model="client",
        adr_017_constraint="z" * 40,
    )
    assert t.primary_passes == ()
    assert t.in_scope_v1 is True
