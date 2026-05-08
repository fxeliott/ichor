"""Capability 5 tools registry — ADR-017 compliant scaffold (Phase D.0).

This module declares the 5 Capability-5 tools available to Claude during the
4-pass orchestrator runtime. **This is a SCAFFOLD ONLY** — handlers raise
`NotImplementedError`. Wiring into the orchestrator + claude-runner contract
is deferred to a future PR (Phase D.0 wiring).

Why scaffold first
==================

Per CLAUDE.md projet : "Capability 5 ADR-017 absente : Claude tools en
runtime (WebSearch / WebFetch / query_db / calc / rag_historical) pas câblés
dans 4-pass — modèle reçoit text-only via data_pool précompilé (gap doctrinal,
Phase D.0)".

Ratifying the scaffold first :
1. Locks the 5-tool surface area (no scope creep later)
2. Documents JSON schemas for the claude-runner contract
3. Provides a single source of truth for tool names + descriptions
4. Allows tests to import the registry without runtime dependencies
5. Marks each tool's ADR-017 boundary preservation explicitly

ADR reference : ADR-050.

Tool architecture
=================

Five tools across two execution models (per Anthropic Tool Use API 2026) :

| Tool              | Model         | Purpose                                |
| ----------------- | ------------- | -------------------------------------- |
| `web_search`      | Server (Anthropic) | Real-time web search (live macro news) |
| `web_fetch`       | Server (Anthropic) | Fetch URL content (CB minutes, papers) |
| `query_db`        | Client (Ichor)     | Read-only SQL on ichor_api DB         |
| `calc`            | Client (Ichor)     | Pure-python math (z-score, returns)   |
| `rag_historical`  | Client (Ichor)     | Vector search over historical analogues |

ADR-017 boundary preservation
==============================

**Critical** : every tool must preserve the contractual boundary "Ichor flags
context, never recommends BUY/SELL". Each tool declaration includes an
explicit `adr_017_constraint` field documenting the rule for that tool :

- `web_search` / `web_fetch` : results are CONTEXT only. Tool result schema
  rejects payloads matching `(buy|sell|long|short)` action verbs in the
  primary recommendation field.
- `query_db` : whitelist of read-only schemas (`session_card_audit`,
  `fred_observations`, `gdelt_events`, `gpr_observations`, `cb_speeches`,
  `alerts`). NO write access. SQL parser rejects DML/DDL.
- `calc` : pure deterministic math. No I/O. Output is a number or
  structured stat (mean / std / z / quantile / etc.).
- `rag_historical` : analogue retrieval only. No prediction. Returns
  similarity-ranked past episodes with their realized outcomes — the model
  uses these as context for its own probabilistic call, not as direct
  signals.

Future wiring (out of scope this PR)
=====================================

The `_handler` placeholder of each tool will be replaced by :
- `web_search` / `web_fetch` : delegated to Anthropic server-side execution
  (see Anthropic Tool Use API "server tools" docs). Ichor adds nothing.
- `query_db` : `apps/api/src/ichor_api/services/tool_query_db.py` (NEW,
  future PR), with SQL parser whitelist + audit log of every query.
- `calc` : pure stdlib `math` + `statistics` modules.
- `rag_historical` : queries `analogue_episodes` table (Phase D.6 future) or
  the existing `dtw_analogue` collector outputs.

The 4-pass orchestrator (`packages/ichor_brain/orchestrator.py`) will gain
a `tools` argument forwarded to claude-runner subprocess. Pass-by-pass tool
choice strategy :
- Pass 1 (regime) : `web_search` for live macro news, `query_db` for FRED
- Pass 2 (asset) : `calc` for z-scores, `rag_historical` for analogues
- Pass 3 (stress) : `web_fetch` for CB minutes, `query_db` for prior briefings
- Pass 4 (invalidation) : all 5 tools available

ROADMAP Phase D.0. ADR-050.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ─────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────

# Tool execution model. "server" = Anthropic-hosted, "client" = Ichor-side.
ExecutionModel = Literal["server", "client"]


@dataclass(frozen=True)
class ToolDef:
    """Definition of a Capability-5 tool — Claude API 2026 compliant.

    Maps to Anthropic Tool Use API spec :
    - `name` / `description` / `input_schema` form the tool definition
      sent to claude-runner with `tools=[...]`
    - `execution_model` distinguishes server tools (no client-side handler)
      from client tools (handler runs in Ichor-side code)
    - `adr_017_constraint` documents the boundary preservation rule

    Future fields (out of scope this PR) :
    - `_handler` : Callable[..., dict] for client tools (PLACEHOLDER raises
      NotImplementedError per Phase D.0 scaffold)
    - `cache_control` : prompt caching strategy (defer to wiring PR)
    - `defer_loading` : True for low-frequency tools (Tool Search Tool
      compat per Anthropic 2026 advanced tool use)
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    execution_model: ExecutionModel
    adr_017_constraint: str
    # Pass numbers (1-4) where this tool is most useful
    primary_passes: tuple[int, ...] = field(default_factory=tuple)
    # True when this tool is in scope for v1 claude-runner contract
    in_scope_v1: bool = True


# ─────────────────────────────────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────────────────────────────────

WEB_SEARCH = ToolDef(
    name="web_search",
    description=(
        "Search the live web for current macro/geopolitical/markets news. "
        "Use for : intra-day news flow not yet in Ichor's data_pool, breaking "
        "events (FOMC speech, USTR press release, central bank intervention), "
        "real-time price/yield checks. Returns titles + snippets + URLs."
    ),
    # Anthropic server tool — no input_schema, server defines.
    input_schema={},
    execution_model="server",
    adr_017_constraint=(
        "Results are CONTEXT only. Synthesizing 'should I buy/sell' from "
        "search results violates ADR-017. Use search results to inform "
        "P(target_up=1) probability, not as direct trade signals."
    ),
    primary_passes=(1, 4),
)


WEB_FETCH = ToolDef(
    name="web_fetch",
    description=(
        "Fetch and parse the full content of a specific URL. Use for : "
        "FOMC minutes, ECB statements, central bank speeches, BIS papers, "
        "academic preprints, USTR Section 301 dockets. Returns parsed text "
        "(markdown-converted)."
    ),
    input_schema={},
    execution_model="server",
    adr_017_constraint=(
        "Document content informs context analysis. Direct quotes attributed "
        "to source. No BUY/SELL inference from CB speech tone alone — pair "
        "with structural analysis."
    ),
    primary_passes=(1, 3),
)


QUERY_DB = ToolDef(
    name="query_db",
    description=(
        "Execute a read-only SQL query on the Ichor production database. "
        "Whitelist of accessible tables : session_card_audit, fred_observations, "
        "gdelt_events, gpr_observations, cb_speeches, alerts. Use for : prior "
        "briefing context, historical baseline values, alert audit trail, "
        "analogue episodes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "SQL SELECT statement. Whitelist : SELECT, FROM, WHERE, "
                    "GROUP BY, ORDER BY, LIMIT, JOIN. Forbidden : INSERT, "
                    "UPDATE, DELETE, DROP, CREATE, ALTER, GRANT, EXEC."
                ),
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum rows to return. Default 100, max 1000.",
                "default": 100,
                "maximum": 1000,
            },
        },
        "required": ["query"],
    },
    execution_model="client",
    adr_017_constraint=(
        "Read-only. SQL parser rejects DML/DDL. Whitelist of tables prevents "
        "access to write-enabled or PII-bearing tables (e.g. trader_notes "
        "is excluded). Every query is audit-logged with timestamp + caller "
        "pass-id for MiFID-grade traceability per ADR-029."
    ),
    primary_passes=(1, 2, 3, 4),
)


CALC = ToolDef(
    name="calc",
    description=(
        "Pure deterministic math operations. Use for : z-score from samples, "
        "Pearson/Spearman correlation, returns from price series, percentile, "
        "rolling stats. NO I/O, NO side effects."
    ),
    input_schema={
        "type": "object",
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
                "description": "Statistical operation to perform.",
            },
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Input array.",
            },
            "params": {
                "type": "object",
                "description": (
                    "Operation-specific parameters (e.g. window size for "
                    "rolling stats, percentile k for percentile)."
                ),
            },
        },
        "required": ["operation", "values"],
    },
    execution_model="client",
    adr_017_constraint=(
        "Pure stdlib math. No data fetching. No model invocation. Output "
        "is a deterministic number or structured stat. Cannot leak BUY/SELL "
        "by construction (no language output)."
    ),
    primary_passes=(2, 3),
)


RAG_HISTORICAL = ToolDef(
    name="rag_historical",
    description=(
        "Retrieve historical analogue episodes from the Ichor analogue store. "
        "Returns top-k similarity-ranked past episodes with their realized "
        "outcomes (asset moves over the next 1d/5d/20d post-episode). Use for : "
        "DTW analogue context, pattern recognition, base-rate calibration."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query_signature": {
                "type": "object",
                "description": (
                    "Current macro signature to match against history "
                    "(e.g. {'vix_level': 17, 'term_premium_bps': 70, "
                    "'dxy_z': -0.5})."
                ),
            },
            "asset": {
                "type": "string",
                "description": "Asset of interest (e.g. 'SPX500_USD', 'XAU_USD').",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of analogue episodes to return.",
                "default": 5,
                "maximum": 20,
            },
        },
        "required": ["query_signature", "asset"],
    },
    execution_model="client",
    adr_017_constraint=(
        "Returns past episodes with REALIZED outcomes — informational only. "
        "The model must use these to calibrate its own P(target_up=1) "
        "probability, NOT to issue a direct trade recommendation. Per "
        "Tetlock superforecaster invalidation: pure pattern matching without "
        "structural reasoning is a known failure mode."
    ),
    primary_passes=(2, 4),
    in_scope_v1=False,  # Defer to Phase D.6 (analogue_episodes table TBD)
)


# ─────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────

CAPABILITY_5_TOOLS: tuple[ToolDef, ...] = (
    WEB_SEARCH,
    WEB_FETCH,
    QUERY_DB,
    CALC,
    RAG_HISTORICAL,
)

BY_NAME: dict[str, ToolDef] = {t.name: t for t in CAPABILITY_5_TOOLS}


def get_tool(name: str) -> ToolDef:
    """Lookup a tool by name. Raises KeyError if unknown."""
    if name not in BY_NAME:
        raise KeyError(
            f"Unknown Capability-5 tool: {name!r}. Valid: {sorted(BY_NAME)}"
        )
    return BY_NAME[name]


def tools_for_pass(pass_num: int) -> tuple[ToolDef, ...]:
    """Return the subset of in-scope-v1 tools relevant for a given pass.

    Pass numbering : 1 (regime) / 2 (asset) / 3 (stress) / 4 (invalidation).
    """
    if pass_num not in (1, 2, 3, 4):
        raise ValueError(f"pass_num must be in 1..4, got {pass_num}")
    return tuple(
        t
        for t in CAPABILITY_5_TOOLS
        if t.in_scope_v1 and pass_num in t.primary_passes
    )


def to_anthropic_tool_param(tool: ToolDef) -> dict[str, Any]:
    """Render a ToolDef in the format expected by Anthropic Messages API
    `tools=[...]` parameter.

    Server tools (web_search, web_fetch) use Anthropic's reserved type ;
    client tools provide their own input_schema.
    """
    if tool.execution_model == "server":
        # Anthropic-hosted tools use a reserved type prefix.
        # The exact server tool spec is per-tool ; this is a placeholder
        # that will be aligned with Anthropic's schema in the wiring PR.
        return {
            "type": f"server_tool_{tool.name}",
            "name": tool.name,
        }
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def assert_registry_complete() -> None:
    """Sanity check — invoked at module import or test time."""
    assert len(CAPABILITY_5_TOOLS) == 5, (
        f"Expected 5 Capability-5 tools, got {len(CAPABILITY_5_TOOLS)}"
    )
    names = [t.name for t in CAPABILITY_5_TOOLS]
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"
    # Every tool must declare its ADR-017 constraint.
    for t in CAPABILITY_5_TOOLS:
        assert t.adr_017_constraint, f"Tool {t.name!r} missing ADR-017 constraint"
        assert t.description, f"Tool {t.name!r} missing description"


# ─────────────────────────────────────────────────────────────────────────
# Placeholder client-side handlers — Phase D.0 wiring deferred
# ─────────────────────────────────────────────────────────────────────────


def _handler_query_db(query: str, max_rows: int = 100) -> dict[str, Any]:
    """Placeholder — Phase D.0 wiring will implement SQL whitelist + audit.

    Future location : apps/api/src/ichor_api/services/tool_query_db.py.
    """
    raise NotImplementedError(
        "query_db handler is scaffolded only. Phase D.0 wiring PR will "
        "implement SQL whitelist parser + audit log per ADR-050."
    )


def _handler_calc(operation: str, values: list[float], params: dict | None = None) -> dict[str, Any]:
    """Placeholder — Phase D.0 wiring will implement pure stdlib math dispatcher."""
    raise NotImplementedError(
        "calc handler is scaffolded only. Phase D.0 wiring PR will "
        "implement stdlib math + statistics dispatcher per ADR-050."
    )


def _handler_rag_historical(query_signature: dict, asset: str, top_k: int = 5) -> dict[str, Any]:
    """Placeholder — Phase D.6 will provide analogue_episodes store first."""
    raise NotImplementedError(
        "rag_historical handler is scaffolded only. Phase D.6 will provide "
        "the analogue_episodes table ; Phase D.0 wiring PR after that "
        "implements the retrieval logic per ADR-050."
    )


# Module-level invariant — fires on import.
assert_registry_complete()
