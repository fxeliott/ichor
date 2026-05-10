# ADR-050: Capability 5 — Claude tools runtime in 4-pass orchestrator (scaffold)

- **Status**: Accepted (scaffold only ; runtime wiring deferred to Phase D.0)
- **Date**: 2026-05-08
- **Deciders**: Eliot
- **Implements**: ROADMAP Phase D.0 (P0 doctrinal gap closure)

## Context

CLAUDE.md projet documents this gap explicitly under "Things that are
subtly broken or deferred" :

> **Capability 5 ADR-017 absente** : Claude tools en runtime
> (WebSearch / WebFetch / query_db / calc / rag_historical) pas câblés
> dans 4-pass — modèle reçoit text-only via data_pool précompilé
> (gap doctrinal, Phase D.0).

Currently, the 4-pass orchestrator (`packages/ichor_brain/orchestrator.py`)
sends a **fully-precompiled** text data_pool to Claude per pass. The model
has no way to :

- Look up a fresh value mid-reasoning ("what is the current 10Y yield?")
- Search the live web for breaking news mid-pass
- Fetch a specific FOMC speech URL referenced in the data_pool
- Compute a custom statistic the data_pool didn't pre-include
- Retrieve historical analogues to calibrate base rates

Per Tetlock superforecaster research + Anthropic Tool Use API 2026 best
practices, this is a structural cap on reasoning quality. The model is
forced to either (a) accept the data_pool as-is and reason within its
limits, or (b) hallucinate a value it can't verify — the latter being a
direct ADR-017 boundary risk.

This ADR ratifies **Capability 5** : the 5 tools the model will gain
runtime access to in Phase D.0 wiring.

## Decision

Wire 5 tools across 2 execution models per Anthropic Tool Use API 2026 :

### Server tools (Anthropic-hosted)

1. **`web_search`** — live web search (real-time macro/geopol news)
2. **`web_fetch`** — URL content fetch (CB minutes, papers, press releases)

### Client tools (Ichor-side)

3. **`query_db`** — read-only SQL on Ichor DB (whitelist of 6 tables)
4. **`calc`** — pure stdlib math operations (z-score, rolling stats, etc.)
5. **`rag_historical`** — top-k analogue retrieval (Phase D.6 deferred)

### Architecture : scaffold first, wire later

This PR ships **scaffold only** :

- Tool definitions in `packages/ichor_brain/tools_registry.py`
- JSON schemas matching Anthropic Tool Use API 2026 spec
- Per-tool ADR-017 constraint documentation
- Pass-mapping helpers (`tools_for_pass(n)`)
- `to_anthropic_tool_param(tool)` rendering for the Messages API
- Placeholder handlers raising `NotImplementedError`
- Comprehensive tests (~22 cases) verifying scaffold contract

**Out of scope this PR** (Phase D.0 future wiring) :

- Modifying `orchestrator.py` to invoke tools mid-pass
- Implementing the SQL whitelist parser for `query_db`
- Adding `cache_control` for prompt caching with tools
- Updating `claude-runner` Win11 contract to forward `tools=[...]`
- The `analogue_episodes` table for `rag_historical` (Phase D.6)

### Tool-by-tool ADR-017 constraints

Each tool ships with an explicit `adr_017_constraint` string documenting
the boundary preservation rule :

| Tool             | ADR-017 constraint summary                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `web_search`     | Results are CONTEXT only. No BUY/SELL synthesis from search.                                                             |
| `web_fetch`      | Document content informs context, no direct CB-tone-only inference.                                                      |
| `query_db`       | Read-only whitelist (6 tables). Audit-logged per ADR-029 MiFID.                                                          |
| `calc`           | Pure deterministic math, no I/O, output cannot leak BUY/SELL by construction.                                            |
| `rag_historical` | Past episodes informational only — model calibrates its own P(target_up=1), pure pattern matching forbidden per Tetlock. |

### Pass-mapping strategy (informative)

Per the 4-pass orchestrator structure :

| Pass             | Purpose            | Primary tools available               |
| ---------------- | ------------------ | ------------------------------------- |
| 1 (regime)       | Macro state call   | `web_search`, `web_fetch`, `query_db` |
| 2 (asset)        | Per-asset bias     | `query_db`, `calc`, `rag_historical`  |
| 3 (stress)       | Invalidation tests | `web_fetch`, `query_db`               |
| 4 (invalidation) | Final synthesis    | All 5 tools                           |

`rag_historical.in_scope_v1=False` until Phase D.6 ships the
`analogue_episodes` table.

### Anthropic Tool Use API 2026 alignment

Per the Anthropic Tool Use API 2026 docs reviewed for this ADR :

- **Server tools** (`web_search`, `web_fetch`) execute on Anthropic
  infrastructure — no client handler needed, results streamed back as
  `server_tool_use` blocks in the response.
- **Client tools** require the client-side agentic loop : while
  `stop_reason == "tool_use"`, execute handler, send back `tool_result`,
  continue conversation.
- **Strict tool use** : `strict: true` ensures Claude's tool calls match
  schema exactly (will be added in wiring PR).
- **Parallel tool use** : `disable_parallel_tool_use=true` if needed for
  ordering ; default allows parallel for Claude 4+ models.
- **Extended thinking compat** : only `tool_choice: auto|none` work with
  thinking mode (per CLAUDE.md projet, Opus 4.7 uses adaptive thinking
  always — wiring PR must use `auto`).
- **Tool Search Tool** (Anthropic 2026 advanced feature) preserves up to
  85% context tokens vs traditional approach ; we may adopt with
  `defer_loading=true` on `rag_historical` once Phase D.6 ships.

## Consequences

### Pros

- **Closes the P0 doctrinal gap** documented in CLAUDE.md
- Tool surface area locked (no scope creep) before wiring
- JSON schemas serve as contract between `ichor_brain` and `claude-runner`
- Tests verify scaffold integrity at import time
- Each tool's ADR-017 boundary preservation explicitly documented
- Can be extended (more tools later) with same pattern

### Cons

- Scaffold without wiring is a deferred completion (Phase D.0 future PR)
- Until wiring lands, tools_registry.py is unused at runtime — risk of
  drift between scaffold and eventual implementation
- `rag_historical` deferred to Phase D.6 — incomplete coverage in v1

### Neutral

- The 5 tools selected match what Eliot's 2026 macro narrative needs
  (FRED queries, web search for breaking news, calc for ad-hoc stats).
  Adding a 6th tool later is non-breaking.
- Server tools (`web_search`, `web_fetch`) leverage Anthropic infrastructure
  → no Ichor-side rate limit / scaling concerns.

## Alternatives rejected

### A — Full Capability-5 wiring in single PR (8-12h)

**Rejected**. Touches `orchestrator.py`, `runner_client.py`, all 5 client
handlers, claude-runner contract, integration tests with Win11 subprocess.
Too risky for one PR. Scaffold + wiring split is the cleaner path.

### B — Skip Capability 5 entirely

**Rejected**. CLAUDE.md projet explicitly tags this as P0 doctrinal gap.
Leaves the model text-only forever, capping reasoning quality.

### C — Adopt MCP (Model Context Protocol) instead of native tool use

**Rejected for v1**. MCP is the Anthropic-recommended pattern for
multi-tool architectures, but adds another protocol layer. Ichor's 5 tools
are stable + small ; native Tool Use API is sufficient and aligns with
existing claude-runner subprocess contract. v2 could migrate to MCP if
tool count grows beyond ~15.

### D — Use only server tools (web_search + web_fetch), skip client tools

**Rejected**. Loses `query_db` (most-used per pass-mapping above) and
`calc` (deterministic math the model otherwise has to do in chain-of-
thought, slower + less reliable).

### E — Implement client handlers immediately, defer JSON schema definition

**Rejected**. Schemas first because they form the contract with
claude-runner. Without them the wiring PR cannot start without rework.

### F — Embed tools registry in `apps/api/` instead of `packages/ichor_brain/`

**Rejected**. `ichor_brain` owns the orchestrator that will invoke tools ;
registry belongs there. `apps/api/` provides per-tool service implementations
(e.g. `tool_query_db.py` future).

## Implementation

Shipped in PR #51 (wave 13). Files :

- `packages/ichor_brain/src/ichor_brain/tools_registry.py` (NEW, ~280 LOC)
- `packages/ichor_brain/tests/test_tools_registry.py` (NEW, ~22 test cases)
- `docs/decisions/ADR-050-capability-5-tools-runtime.md` (this file)

No catalog change. No Hetzner deploy required (scaffold is import-only).
The 4-pass orchestrator is unchanged in this PR.

## Phase D.0 wiring TODO list (out of scope this PR)

1. **`apps/api/src/ichor_api/services/tool_query_db.py`** — SQL whitelist
   parser (sqlglot ?) + audit log + 6-table allowlist enforcement
2. **`apps/api/src/ichor_api/services/tool_calc.py`** — stdlib math/statistics
   dispatcher matching the 9 enumerated operations
3. **`packages/ichor_brain/src/ichor_brain/orchestrator.py`** — agentic
   loop : while `stop_reason == "tool_use"`, execute tool handler, send
   back `tool_result`, continue. Handle parallel tool calls.
4. **`packages/ichor_brain/src/ichor_brain/runner_client.py`** — extend
   payload to include `tools=[to_anthropic_tool_param(t) for t in
tools_for_pass(n)]`. Add `cache_control` for tool definitions.
5. **`apps/claude-runner/`** (Win11) — accept `tools` field in
   `/v1/structured-prompt` request. Forward to claude API. Stream
   `tool_use` blocks back. Loop on `tool_result` exchanges.
6. **Integration tests** — end-to-end test invoking a tool through the
   full Ichor → claude-runner → Anthropic API → handler → result chain.
7. **Audit log table** — add `tool_call_audit` table (migration 0029)
   for MiFID-grade traceability per ADR-029.

## Related

- ADR-009 — Voie D (claude-runner subprocess, no SDK paid consumption)
- ADR-017 — Living Macro Entity boundary (no BUY/SELL leak — preserved
  per-tool above)
- ADR-029 — EU AI Act §50 + AMF DOC-2008-23 (audit log MiFID-grade)
- ADR-031 — Single source of truth pattern (registry as SoT for tools)
- Anthropic Tool Use API 2026 docs (server vs client tools, agentic loop)
- Anthropic Advanced Tool Use 2026 (Tool Search Tool, Programmatic Tool
  Calling, Tool Use Examples)
- Tetlock Superforecaster invalidation framework (rag_historical
  pattern-matching guardrail)

## Followups

- **Phase D.0 wiring PR** (next big strategic move) — see TODO list above
- **`analogue_episodes` table** (Phase D.6) → unblocks `rag_historical`
- **Tool Search Tool migration** (Anthropic 2026) — adopt if tool count
  grows beyond ~15
- **MCP migration consideration** — re-evaluate when Ichor tool count is
  stable + fits MCP server pattern
