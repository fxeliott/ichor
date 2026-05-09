"""MCP stdio server — exposes `query_db` and `calc` to Claude CLI.

Spawned per-session by `claude -p --mcp-config ichor.mcp.json
--strict-mcp-config --allowedTools mcp__ichor__query_db
mcp__ichor__calc`. The server itself does NO trade logic and holds NO
DB credentials — every tool call posts to apps/api/v1/tools/* and the
audit row is written there.

ADR-077 wire (Win11 → Hetzner) :

    list_tools()  → returns the two static tool descriptors below.
    call_tool()   → forwards arguments to ToolApiClient and wraps
                    the apps/api response in an MCP TextContent JSON
                    blob. Errors come back as a single TextContent
                    with `is_error=True` so the model can self-correct.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import mcp.server.stdio
import mcp.types as types
import structlog
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import __version__
from .client import ToolApiClient, ToolApiError
from .config import get_settings

log = structlog.get_logger(__name__)

SERVER_NAME = "ichor"


# ── Tool definitions (static input schemas) ───────────────────────


_AUDIT_FIELDS_SCHEMA: dict[str, Any] = {
    "agent_kind": {
        "type": "string",
        "default": "manual",
        "maxLength": 64,
        "description": (
            "Which 4-pass agent invoked this tool. Use 'manual' for "
            "ad-hoc invocations from `claude -p`. Otherwise: "
            "'pass1_regime', 'pass2_asset', 'pass3_stress', "
            "'pass4_invalidation', 'pass5_counterfactual'."
        ),
    },
    "pass_index": {
        "type": "integer",
        "default": 1,
        "minimum": 1,
        "maximum": 5,
        "description": "Orchestrator pass index. Pass 5 = counterfactual.",
    },
    "session_card_id": {
        "type": ["string", "null"],
        "default": None,
        "description": (
            "UUID of the parent session_card_audit row. Set by the "
            "orchestrator; leave null for ad-hoc CLI runs."
        ),
    },
}


def _build_tools() -> list[types.Tool]:
    """Return the two static tool descriptors. Pure / no I/O."""
    return [
        types.Tool(
            name="query_db",
            description=(
                "Read-only SQL access to the 6 Capability-5 allowlist "
                "tables: session_card_audit, fred_observations, "
                "gdelt_events, gpr_observations, cb_speeches, alerts. "
                "Only single SELECT/UNION/INTERSECT/EXCEPT statements "
                "are accepted. DML/DDL, schema-qualified names, and "
                "multi-statement payloads are rejected by an sqlglot "
                "AST whitelist (ADR-071 STEP-1) before reaching the "
                "DB. Hard cap of 1000 rows; default 100."
            ),
            inputSchema={
                "type": "object",
                "required": ["sql"],
                "additionalProperties": False,
                "properties": {
                    "sql": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 8192,
                        "description": (
                            "Postgres-flavoured SELECT statement. "
                            "Must reference only allowlisted tables."
                        ),
                    },
                    "max_rows": {
                        "type": ["integer", "null"],
                        "default": None,
                        "minimum": 1,
                        "maximum": 1000,
                        "description": "Row cap; default 100, hard max 1000.",
                    },
                    **_AUDIT_FIELDS_SCHEMA,
                },
            },
        ),
        types.Tool(
            name="calc",
            description=(
                "Deterministic math on a numeric array. Supported "
                "operations: zscore, rolling_mean, rolling_std, "
                "pct_change, log_returns, correlation, percentile, "
                "ewma, annualize_vol. Pure stdlib; no I/O. ADR-017 "
                "safe by construction (output is a number or list of "
                "numbers — cannot leak a direction verb)."
            ),
            inputSchema={
                "type": "object",
                "required": ["operation", "values"],
                "additionalProperties": False,
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "zscore",
                            "rolling_mean",
                            "rolling_std",
                            "pct_change",
                            "log_returns",
                            "correlation",
                            "percentile",
                            "ewma",
                            "annualize_vol",
                        ],
                    },
                    "values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 1,
                        "maxItems": 10000,
                    },
                    "params": {
                        "type": "object",
                        "default": {},
                        "description": (
                            "Per-op parameters — e.g. "
                            "{'window': 20} for rolling_mean, "
                            "{'k': 95} for percentile, "
                            "{'alpha': 0.94} for ewma, "
                            "{'other': [..]} for correlation."
                        ),
                        "additionalProperties": True,
                    },
                    **_AUDIT_FIELDS_SCHEMA,
                },
            },
        ),
    ]


# ── Lifespan + handlers ───────────────────────────────────────────


@asynccontextmanager
async def server_lifespan(_server: Server) -> AsyncIterator[dict[str, Any]]:
    """Build the shared httpx client at startup, dispose at shutdown."""
    settings = get_settings()
    client = ToolApiClient(settings)
    log.info(
        "ichor_mcp.startup",
        version=__version__,
        api_base_url=settings.api_base_url,
        environment=settings.environment,
        has_service_token=bool(settings.api_service_token),
        has_cf_access=bool(
            settings.cf_access_client_id and settings.cf_access_client_secret
        ),
    )
    try:
        yield {"client": client, "settings": settings}
    finally:
        await client.aclose()
        log.info("ichor_mcp.shutdown")


def _make_server() -> Server:
    """Build the lowlevel Server with the two handlers wired in."""
    server: Server = Server(SERVER_NAME, lifespan=server_lifespan)
    tools = _build_tools()
    tool_index = {t.name: t for t in tools}

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return tools

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        if name not in tool_index:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": f"unknown tool '{name}'. known: {list(tool_index)}"}
                    ),
                )
            ]

        ctx = server.request_context
        client: ToolApiClient = ctx.lifespan_context["client"]

        # Common audit-trail fields with defaults aligned to the schema.
        agent_kind = str(arguments.get("agent_kind") or "manual")
        pass_index = int(arguments.get("pass_index") or 1)
        session_card_id = arguments.get("session_card_id")
        if session_card_id is not None:
            session_card_id = str(session_card_id)

        try:
            if name == "query_db":
                payload = await client.query_db(
                    sql=str(arguments["sql"]),
                    max_rows=arguments.get("max_rows"),
                    agent_kind=agent_kind,
                    pass_index=pass_index,
                    session_card_id=session_card_id,
                )
            else:  # name == "calc"
                payload = await client.calc(
                    operation=str(arguments["operation"]),
                    values=list(arguments["values"]),
                    params=arguments.get("params") or {},
                    agent_kind=agent_kind,
                    pass_index=pass_index,
                    session_card_id=session_card_id,
                )
        except ToolApiError as e:
            log.warning(
                "ichor_mcp.tool.failed",
                tool=name,
                status=e.status_code,
                detail=e.detail[:200],
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": e.detail,
                            "status_code": e.status_code,
                            "tool": name,
                        }
                    ),
                )
            ]

        return [
            types.TextContent(
                type="text",
                text=json.dumps(payload, default=str),
            )
        ]

    return server


# ── Entrypoint ────────────────────────────────────────────────────


def _configure_logging(level: str) -> None:
    """Send structlog output to stderr so it doesn't pollute the MCP
    stdio JSON-RPC stream on stdout."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


async def _run() -> None:
    settings = get_settings()
    _configure_logging(settings.log_level)
    server = _make_server()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:  # pragma: no cover — entrypoint shim
    """Console entry point — `ichor-mcp` from the venv Scripts dir.

    Runs until the Claude CLI closes its end of stdio.
    """
    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    main()
