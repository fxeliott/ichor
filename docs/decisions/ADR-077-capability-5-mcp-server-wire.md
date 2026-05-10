# ADR-077: Capability 5 STEP-3 — MCP server on Win11 forwards to apps/api `/v1/tools/*`

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes**: none
- **Related**: ADR-009 (Voie D — no Anthropic SDK consumption), ADR-029
  (audit_log immutability — MiFID DOC-2008-23), ADR-050 (Capability 5
  registry scaffold), ADR-067 (Couche-2 async polling), ADR-071
  (Capability 5 deferral, 6-step sequence: PRE-1 / PRE-2 / STEP-1 →
  STEP-6)

## Context

ADR-071 froze the Capability 5 wiring as a 6-step sequence and
**STEP-3** is the MCP server itself : the bridge that lets the Claude
CLI on Win11 invoke the two whitelisted client tools (`query_db`,
`calc`) implemented in W83 / W84 (`services/tool_query_db.py`,
`services/tool_calc.py`). At STEP-3 onset the situation was :

1. The two tool services exist, are unit-tested standalone (29 + 28 =
   57 tests green Hetzner), and have a 100 % deterministic surface.
2. The `tool_call_audit` table exists with an immutable trigger
   (migration 0038) and is empty by design — waiting for STEP-3+.
3. PRE-1 (Cloudflare Access service token on
   `claude-runner.fxmilyapp.com`) is **NOT** wired ; pending Eliot
   manual setup.
4. The Win11 box has no Tailscale link to Hetzner ; only the existing
   public Cloudflare Tunnel for the claude-runner.

Two architectural shapes were on the table for the MCP server :

**Option A — Direct DB connection from Win11.** The MCP server opens
an asyncpg pool to Hetzner Postgres and runs `tool_query_db` /
`tool_calc` locally, then inserts the `tool_call_audit` row in the
same session.

**Option B — HTTP wrapper.** The MCP server posts every invocation to
a new Hetzner endpoint (`/v1/tools/*`) ; the apps/api process runs
the tool body and writes the audit row.

## Decision

Adopt **Option B** : the MCP server (`apps/ichor-mcp`) holds **no DB
credentials**, no Postgres dependency, no asyncpg in its requirements.
Every tool invocation forwards to `apps/api` over HTTPS, which in turn
runs the tool body, persists the immutable `tool_call_audit` row in a
**dedicated** session (so an `execute_query` rollback can never void
the trail), and returns the result.

```
[Claude CLI Win11]
   ↓ stdio MCP (jsonrpc)
[apps/ichor-mcp (this wave)]
   ↓ httpx HTTPS  (X-Ichor-Tool-Token + optional CF-Access headers)
[apps/api /v1/tools/{query_db,calc}]
   ↓ async SQLAlchemy
[Postgres: SELECT result + immutable tool_call_audit insert]
```

A single MCP server name (`ichor`) exposes the two tools — Claude CLI
will see them as `mcp__ichor__query_db` and `mcp__ichor__calc`.

## Why HTTP wrapper rather than direct DB

| Concern                           | Direct DB (Option A)                            | HTTP wrapper (Option B, chosen)                         |
| --------------------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| DB credentials on Win11           | Required (`asyncpg` URL with password)          | **Never present**                                       |
| Tailscale / SSH tunnel            | Required (Tailscale not setup, autossh fragile) | Not needed                                              |
| `tool_call_audit` atomicity       | OK (same session as query)                      | OK (dedicated session, audit-first invariant)           |
| CF Access service-token edge gate | Bypassed — direct DB                            | Layered on top of `/v1/tools/*` (defense in depth)      |
| Scope of new code                 | DB stack on Win11 + audit insert path           | One new router on Hetzner, one MCP server stub on Win11 |
| ADR-029 MiFID compliance          | Already satisfied via 0038 trigger              | Same, plus separate audit session                       |

The direct path adds risk (credentials on a developer-class machine,
fragile transport) for no tangible upside. The HTTP wrapper hop is
~50–200 ms — negligible against the 60–180 s `claude -p` subprocess
that already dwarfs it.

## Authentication

Three layers, in order of activation :

1. **`X-Ichor-Tool-Token`** — shared secret presented by the MCP
   server on every request. Production lifespan refuses to start with
   `ICHOR_API_TOOL_SERVICE_TOKEN` empty (cf `apps/api/.../main.py`
   lifespan check). Dev mode allows empty for local pytest. The
   token is rotatable via the existing SOPS secrets pipeline.
2. **CF Access service token (`CF-Access-Client-Id` +
   `CF-Access-Client-Secret`)** — Cloudflare-side enforcement on
   `apps/api` ingress. Wired by Eliot manually as part of PRE-1.
   Pre-PRE-1 the request reaches apps/api directly through the
   existing tunnel ; the service-token guard remains the active gate
   meanwhile.
3. **Postgres role grants** — final backstop. The `ichor` DB role is
   provisioned with SELECT-only on the 6 allowlist tables ; even if
   layers 1–2 were bypassed and the sqlglot whitelist somehow leaked,
   the DB itself refuses anything else. (Ratified independently as
   ADR-050 rationale.)

## Tools registered

| Tool name              | Maps to                                                                  | Behavior                                             |
| ---------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------- |
| `mcp__ichor__query_db` | `services.tool_query_db.execute_query` via apps/api `/v1/tools/query_db` | sqlglot AST whitelist, 6 tables, hard-cap 1000 rows. |
| `mcp__ichor__calc`     | `services.tool_calc.calc` via apps/api `/v1/tools/calc`                  | 9 deterministic ops, pure stdlib, ADR-017 safe.      |

Server tools (`web_search`, `web_fetch`) are **excluded** from this
wave per ADR-071 — they're billed by Anthropic, violate Voie D
(ADR-009), and bring no incremental research signal we can't get from
Couche-2.

`rag_historical` is excluded too, deferred to Phase D.6.

## Audit row shape

Every successful or failed invocation produces one
`tool_call_audit` row :

| Column            | Source                                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| `tool_name`       | `mcp__ichor__query_db` or `mcp__ichor__calc` (constants in `routers/tools.py`)                               |
| `tool_input`      | Sanitised request body (no row payload — `values_len` only for calc)                                         |
| `tool_output`     | `{row_count, tables_referenced, truncated}` (query_db) or `{result_kind, result_len}` (calc). NULL on error. |
| `error`           | `f"{type(e).__name__}: {e}"` from the underlying service.                                                    |
| `agent_kind`      | Caller-supplied. Default `"manual"` for ad-hoc CLI runs.                                                     |
| `pass_index`      | 1..5. Default 1.                                                                                             |
| `session_card_id` | UUID FK to session_card_audit when invoked inside a 4-pass run. NULL otherwise.                              |
| `duration_ms`     | Wall time the route handler spent on the underlying service call.                                            |

The insertion happens in a separate `async_sessionmaker()` session so
the `execute_query` rollback path never voids the audit trail (which
ADR-029 requires).

## Consequences

**Positive**

- Win11 stays a thin presentation layer — no DB pool, no migrations,
  no maintenance overhead beyond `setup-ichor-mcp.ps1`.
- Audit centralisation : one Postgres trigger (0038) enforces
  immutability for all Capability 5 calls regardless of caller.
- Defense in depth : service-token + CF Access (PRE-1) + DB grants
  layer cleanly without redundancy.
- Path forward : STEP-4 (RunnerCall.tools plumbing) and STEP-5
  (orchestrator agentic loop) bind to existing MCP tool names —
  no further wire change.

**Negative / accepted**

- One extra HTTP hop adds ~50–200 ms per tool call. Acceptable
  against a 60–180 s `claude -p` outer round-trip.
- `apps/api` now exposes a SQL-execution surface. Mitigated by the
  three-layer auth above + the sqlglot AST whitelist + the immutable
  audit row. Also note `apps/api` already exposes 33 routers
  including `/v1/admin/status`; this is not a new "danger zone".
- `apps/ichor-mcp` is a 4th Python package in `apps/` (alongside
  `api`, `claude-runner`, `web`, `web2`). CI matrices `.github/
workflows/{ci,audit}.yml` updated accordingly.

**Pending**

- PRE-1 CF Access service token on `claude-runner.fxmilyapp.com`
  remains an Eliot manual step. Until then `/v1/tools/*` relies
  solely on the service-token header for auth. Production won't boot
  without one (lifespan check).
- STEP-4 (RunnerCall.tools plumbing) and STEP-5 (orchestrator
  `while resp.stop_reason == "tool_use"` agentic loop) are separate
  waves.
- `setup-ichor-mcp.ps1` is a one-off bootstrap, not a NSSM service —
  the MCP server is stdio-spawned per session by the Claude CLI itself.

## References

- Migration 0038 — `tool_call_audit` table + immutable trigger
- `apps/api/src/ichor_api/services/tool_query_db.py` (W83, ADR-071 STEP-1)
- `apps/api/src/ichor_api/services/tool_calc.py` (W84, ADR-071 STEP-2)
- `apps/api/src/ichor_api/routers/tools.py` (W85, this ADR)
- `apps/ichor-mcp/` (W85, this ADR)
- ADR-071 § Phase D.0 sequence
