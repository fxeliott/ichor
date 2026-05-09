"""Capability 5 client-tool routes (ADR-071 STEP-3 / ADR-077).

Two endpoints exposed by the Hetzner FastAPI to the Win11 stdio MCP
server (`apps/ichor-mcp`). The MCP server holds NO database credentials;
it forwards every Capability 5 client-tool invocation here over HTTPS,
this router runs the validated body, and writes the immutable
`tool_call_audit` row in a dedicated session so the trail survives even
when the tool body raises.

Wire :

    Claude CLI (Win11)
        ↓ stdio MCP (jsonrpc)
    apps/ichor-mcp (Win11)
        ↓ httpx HTTPS
    /v1/tools/{query_db,calc} (this router, Hetzner)
        ↓ asyncpg
    Postgres + tool_call_audit (immutable, trigger from migration 0038)

Auth :
- Header `X-Ichor-Tool-Token` (shared service token from
  `ICHOR_API_TOOL_SERVICE_TOKEN`). Empty token in dev disables the
  guard ; in production the lifespan validator refuses to boot without
  one.
- CF Access JWT enforcement is layered on top by Cloudflare (PRE-1
  pending). Defense in depth, not redundant.

Boundaries (DO NOT BREAK) :
- Server tools (`web_search`, `web_fetch`) are NOT routed here. They
  are billed by Anthropic (ADR-071, Voie D ADR-009).
- The audit row is the source of truth for MiFID DOC-2008-23
  reconstruction (ADR-029). It mirrors the `audit_log` immutability
  trigger pattern (migration 0028 → 0038).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session, get_sessionmaker
from ..models import ToolCallAudit
from ..schemas import (
    ToolCalcIn,
    ToolCalcOut,
    ToolQueryDbIn,
    ToolQueryDbOut,
)
from ..services.tool_calc import ToolCalcError, calc
from ..services.tool_query_db import (
    HARD_MAX_ROWS,
    ToolQueryDbError,
    execute_query,
    validate_query,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/tools", tags=["tools"])

# Tool-name registry — keep MCP-qualified strings so `tool_call_audit.tool_name`
# is round-trippable to the MCP server config without string surgery.
_TOOL_NAME_QUERY_DB = "mcp__ichor__query_db"
_TOOL_NAME_CALC = "mcp__ichor__calc"


async def verify_service_token(
    x_ichor_tool_token: Annotated[str | None, Header(alias="X-Ichor-Tool-Token")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Constant-time check on the shared service token.

    Empty `tool_service_token` in settings (dev default) bypasses the
    check, but lifespan refuses to start in production without one
    (see config.py). In production the guard is layered with CF Access
    on the Cloudflare side."""
    expected = settings.tool_service_token.strip()
    if not expected:
        return  # Dev mode — guard disabled.
    presented = (x_ichor_tool_token or "").strip()
    # constant-time compare to avoid header-length oracles
    import hmac

    if not hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Ichor-Tool-Token missing or invalid",
        )


async def _persist_audit(
    *,
    tool_name: str,
    tool_input: dict,
    tool_output: dict | None,
    duration_ms: int,
    error: str | None,
    agent_kind: str,
    pass_index: int,
    session_card_id,
) -> None:
    """Insert one tool_call_audit row in a dedicated short-lived session.

    Dedicated session so an `execute_query` rollback cannot wipe the
    trail. ADR-029 MiFID-style immutability trigger refuses any UPDATE
    or DELETE post-insert, so once committed the row is locked."""
    sm = get_sessionmaker()
    async with sm() as audit_session:
        audit_session.add(
            ToolCallAudit(
                ran_at=datetime.now(UTC),
                agent_kind=agent_kind,
                pass_index=pass_index,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_output,
                duration_ms=duration_ms,
                error=error,
                session_card_id=session_card_id,
            )
        )
        await audit_session.commit()


@router.post(
    "/query_db",
    response_model=ToolQueryDbOut,
    dependencies=[Depends(verify_service_token)],
    responses={
        400: {"description": "Validation rejected the SQL (non-allowlist table, DML, multi-statement)"},
        401: {"description": "Service token missing/invalid"},
        500: {"description": "Database execution failure (audit row still written)"},
    },
)
async def query_db_endpoint(
    req: ToolQueryDbIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ToolQueryDbOut:
    """Validate + execute a read-only SQL query through the sqlglot
    whitelist, audit the call regardless of outcome.

    Three-layer defense before the DB sees the SQL :
      1. sqlglot AST whitelist (single SELECT, 6 allowlist tables)
      2. HARD_MAX_ROWS post-fetch cap
      3. Postgres role grants (DB-level least-privilege backstop)

    The audit row carries the full request body and either the success
    output or the error message. Insertion happens in a dedicated
    session so error rollback in the main one never voids the trail."""
    started = time.monotonic()
    error: str | None = None
    rows: list[dict] = []
    tables_referenced: list[str] = []
    truncated = False

    # Pre-validate so we can audit the rejected SQL with the structured reason.
    validation = validate_query(req.sql)
    tables_referenced = sorted(validation.tables_referenced)

    if not validation.ok:
        error = f"validation rejected: {validation.reason}"
    else:
        try:
            rows = await execute_query(session, req.sql, req.max_rows)
            cap = req.max_rows or HARD_MAX_ROWS
            truncated = len(rows) >= min(cap, HARD_MAX_ROWS)
        except ToolQueryDbError as e:
            error = f"{type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001 — audit-first
            error = f"{type(e).__name__}: {e}"

    duration_ms = int((time.monotonic() - started) * 1000)

    tool_input = {
        "sql": req.sql,
        "max_rows": req.max_rows,
    }
    tool_output: dict | None
    if error is None:
        tool_output = {
            "row_count": len(rows),
            "tables_referenced": tables_referenced,
            "truncated": truncated,
        }
    else:
        tool_output = None

    await _persist_audit(
        tool_name=_TOOL_NAME_QUERY_DB,
        tool_input=tool_input,
        tool_output=tool_output,
        duration_ms=duration_ms,
        error=error,
        agent_kind=req.agent_kind,
        pass_index=req.pass_index,
        session_card_id=req.session_card_id,
    )

    if error is not None:
        # Validation rejection → 400. Runtime DB failure → 500.
        # The validation reason is always wrapped, so a "validation rejected"
        # prefix is the cheap discriminator.
        is_validation = error.startswith("validation rejected")
        log.warning(
            "tools.query_db.failed",
            error=error,
            agent_kind=req.agent_kind,
            duration_ms=duration_ms,
        )
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
                if is_validation
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=error,
        )

    log.info(
        "tools.query_db.ok",
        agent_kind=req.agent_kind,
        rows=len(rows),
        tables=tables_referenced,
        duration_ms=duration_ms,
    )
    return ToolQueryDbOut(
        rows=rows,
        duration_ms=duration_ms,
        tables_referenced=tables_referenced,
        truncated=truncated,
    )


@router.post(
    "/calc",
    response_model=ToolCalcOut,
    dependencies=[Depends(verify_service_token)],
    responses={
        400: {"description": "Bad input (unknown op, NaN, missing params, length mismatch)"},
        401: {"description": "Service token missing/invalid"},
    },
)
async def calc_endpoint(req: ToolCalcIn) -> ToolCalcOut:
    """Dispatch a deterministic math op (`zscore`, `rolling_mean`,
    `correlation`, …). Pure stdlib; no I/O.

    Same audit-first pattern as `query_db`. ADR-017 safe by construction
    — the output is a number or list of numbers, cannot leak a
    direction verb."""
    started = time.monotonic()
    error: str | None = None
    result_value = None

    try:
        result_value = calc(req.operation, req.values, req.params)
    except ToolCalcError as e:
        error = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 — audit-first
        error = f"{type(e).__name__}: {e}"

    duration_ms = int((time.monotonic() - started) * 1000)

    tool_input = {
        "operation": req.operation,
        "values_len": len(req.values),
        "params": req.params,
    }
    tool_output: dict | None
    if error is None:
        tool_output = {
            "result_kind": "scalar" if not isinstance(result_value, list) else "array",
            "result_len": len(result_value) if isinstance(result_value, list) else None,
        }
    else:
        tool_output = None

    await _persist_audit(
        tool_name=_TOOL_NAME_CALC,
        tool_input=tool_input,
        tool_output=tool_output,
        duration_ms=duration_ms,
        error=error,
        agent_kind=req.agent_kind,
        pass_index=req.pass_index,
        session_card_id=req.session_card_id,
    )

    if error is not None:
        log.warning(
            "tools.calc.failed",
            operation=req.operation,
            error=error,
            agent_kind=req.agent_kind,
            duration_ms=duration_ms,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    log.info(
        "tools.calc.ok",
        operation=req.operation,
        agent_kind=req.agent_kind,
        duration_ms=duration_ms,
    )
    return ToolCalcOut(result=result_value, duration_ms=duration_ms)
