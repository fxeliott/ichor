# ADR-071: Capability 5 — defer wiring, restrict to client tools, sequence pre-requisites

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes (sequencing only)**: ADR-050 § "Phase D.0 7-step wiring"
- **Related**: ADR-009 (Voie D), ADR-017 (research-only),
  ADR-029 (EU AI Act §50 + AMF DOC-2008-23 audit), ADR-050 (scaffold ratified)

## Context

ADR-050 ratified Capability 5 — Claude tools at runtime — as a
**scaffold only**. The registry (`packages/ichor_brain/.../tools_registry.py`,
410 LOC + 22 passing tests) declares 5 tools: `web_search`, `web_fetch`
(server-side, Anthropic-hosted) and `query_db`, `calc`, `rag_historical`
(client-side, Ichor-hosted handlers). Phase D.0 promised a 7-step wiring
to make them callable from inside the 4-pass orchestrator.

W73 audit (2026-05-09) reconciled the scaffold against:

1. **What `claude -p` actually supports in 2026** —
   verified via context7 + WebSearch on the live CLI reference. The
   CLI accepts `--mcp-config <path|json>`, `--strict-mcp-config`,
   `--allowedTools "<pattern>" ...`, and `--disallowedTools "<pattern>" ...`.
   MCP tools follow the naming pattern `mcp__<server-name>__<tool-name>`,
   wildcards supported. Output is structured via `--output-format json`,
   which returns the full content blocks including `tool_use` /
   `tool_result` envelopes. **Conclusion**: technically feasible without
   the Anthropic Python SDK — Voie D-compatible mechanism exists.

2. **How server tools are billed in 2026** —
   verified via Anthropic's public pricing page. Server-side tools are
   **billed separately** from token usage. `web_search` = $10 per 1 000
   searches charged on top of the per-token rates. This is true even on
   Pro and Max plans (Anthropic explicitly carved out server-tool usage
   from flat-rate subscriptions in April 2026). **Conclusion**:
   wiring `web_search` or `web_fetch` from inside Ichor would re-introduce
   metered Anthropic consumption — direct violation of ADR-009 Voie D.

3. **Hetzner / Win11 / Cloudflare Tunnel attack surface** — the
   `claude-runner.fxmilyapp.com` tunnel currently runs with
   `require_cf_access=false`, no auth at the edge. If the agentic loop
   wires `query_db` and forwards through this tunnel, the tunnel becomes
   an unauthenticated SQL gateway. Even with a strict allowlist, an
   adversary who reaches the tunnel could enumerate schema. CF Access
   service-token wiring (Phase A.7 partial — RUNBOOK-014/015 shipped,
   actual token wiring pending) is the gating pre-requisite.

4. **Audit trail gap** — migration `0028` made `audit_log` immutable,
   but **no `tool_call_audit` table exists yet**. ADR-029 MiFID
   compliance requires an immutable record per tool invocation. Without
   this table, every tool call goes unobserved by the regulator-facing
   audit surface — unacceptable per ADR-029.

5. **`query_db` whitelist enforcement is description-only** —
   `tools_registry.py` declares the 6-table allowlist as a Markdown
   string in the tool description. Without an `sqlglot`-based parser
   that rejects any SELECT touching another table, the whitelist is
   advisory and a sufficiently-prompted Claude could request
   `SELECT * FROM api_keys`.

6. **Prompt-injection / ADR-017 boundary** — even after dropping
   server tools, `rag_historical` returns historical analogues + their
   realised P&L. Claude could regress toward "this exact setup worked
   before, conviction = 100 %" → conviction-cap violation. Tetlock
   invalidation guardrail (documented in registry as advisory text)
   needs machine enforcement post-tool-result.

## Decision

Defer Phase D.0 wiring to a structured 6-step sequence rather than
the original 7-step plan. The new sequence excludes server tools and
gates execution behind two infrastructure pre-requisites:

### Scope restriction (immutable, encoded in the registry)

- **`web_search` and `web_fetch` are NOT wired**. They violate ADR-009
  Voie D (per-call $10/1000 metered usage). They remain in the
  registry as `_disabled_in_voie_d=True` (constant flag added at
  wiring time) and are never advertised in the `--allowedTools`
  list passed to `claude -p`.
- **Only `query_db`, `calc`, and `rag_historical` are candidates** for
  Capability 5 at runtime. All three execute on Ichor-side handlers
  via an Ichor-hosted MCP server. Zero metered Anthropic API usage.

### Pre-requisites (must complete before any wiring lands)

1. **PRE-1 CF Access service token** wired on
   `claude-runner.fxmilyapp.com`. The agentic loop necessarily
   broadcasts tool requests/results across the tunnel; the tunnel
   must require an Ichor-issued service token. Tracked under Phase A.7
   completion. Without this, `query_db` becomes an unauthenticated
   public SQL gateway.
2. **PRE-2 Migration NNNN_tool_call_audit** — table with the same
   immutable trigger pattern as migration `0028` (audit_log).
   Schema: `id UUID PK, ran_at timestamptz, agent_kind, pass_index,
tool_name, tool_input JSONB, tool_output JSONB, duration_ms,
error TEXT, session_card_id FK`. ADR-029 MiFID compliance.

### Wiring sequence (after PRE-1 + PRE-2)

3. **STEP-1** — `apps/api/src/ichor_api/services/tool_query_db.py`:
   `sqlglot`-based SELECT parser + 6-table whitelist enforcement +
   `tool_call_audit` insert.
4. **STEP-2** — `apps/api/src/ichor_api/services/tool_calc.py`:
   stdlib dispatcher matching the 9 ops in
   `tools_registry.CALC.input_schema.properties.operation.enum`.
   `rag_historical` deferred to STEP-2b — depends on a hot
   pgvector embedding workflow that doesn't yet exist (ADR-050
   already marked `rag_historical.in_scope_v1=False`, deferred Phase D.6).
5. **STEP-3** — Ichor MCP server (`apps/ichor-mcp/`) — small FastAPI
   stdio server exposing the 3 client tools per the MCP spec.
   Runs on Win11 alongside `claude-runner`, reaches Hetzner Postgres
   via tailscale or SSH-tunnelled libpq. Bundled into the standalone
   uvicorn startup.
6. **STEP-4** — `RunnerCall.tools: list[dict] | None` plumbing in
   `packages/ichor_brain/.../runner_client.py` and matching field
   in `apps/claude-runner/.../models.py` (BriefingTaskRequest +
   AgentTaskRequest). `RunnerResponse` exposes `stop_reason` and
   structured `content` blocks. `subprocess_runner.py` adds
   `--mcp-config <path>` and `--allowedTools "<exact-pattern>" ...`
   forwarding.
7. **STEP-5** — agentic loop in `orchestrator.py` Pass 1..4 wraps
   each `runner.run(call)` in a `while resp.stop_reason ==
"tool_use"` loop. Use `tools_for_pass(n)` to scope per pass.
   On every iteration, post-filter the assistant content for ADR-017
   trade-recommendation patterns and reset to `neutral` if a literal
   "buy"/"sell" surfaces in the augmented narrative.
8. **STEP-6** — integration test exercising the full chain.

### Step-7 of the original plan is dropped

The original ADR-050 STEP-7 was "tool_call_audit migration". That's
PRE-2 in the new sequence — pre-requirement, not last step. Original
ADR-050 is updated by reference (this ADR) to reflect the
re-sequenced plan; no superseding because the scaffolding (registry +
tests) remains unchanged.

## Consequences

### Positive

- **Voie D preserved**. No metered server-tool usage. Max 20x flat
  remains the only Anthropic spend.
- **Defense-in-depth on `query_db`**. Three independent layers
  must fail before an arbitrary SELECT ships: (a) MCP server
  registration restricting to `mcp__ichor_db__query_db`, (b)
  `--allowedTools` exact pattern, (c) sqlglot parser enforcing
  the table whitelist. The current scaffold relied on layer (b)
  alone via description text.
- **Audit-first**. `tool_call_audit` exists before the first
  tool call lands. ADR-029 MiFID compliance is preserved by
  construction.
- **CF Access pre-required**. The tunnel is no longer an
  unauthenticated SQL surface. Closes the "drainable public
  endpoint" line item from CLAUDE.md "Subtly broken" list.
- **`rag_historical` deferral re-confirmed**. Phase D.6 still
  out of scope — keeps Capability 5 v1 to a 2-tool surface
  (`query_db` + `calc`), much smaller blast radius for first
  agentic iteration.

### Negative

- **Capability 5 is on hold**. Pass 1..4 still receives a
  pre-compiled text-only `data_pool` and cannot fetch arbitrary
  context mid-flight. The doctrinal gap noted in CLAUDE.md
  ("Capability 5 ADR-017 absente") persists.
- **Sequencing cost**: PRE-1 (CF Access) is a separate wave
  (Phase A.7 completion). Until that wave lands, even client-tool
  wiring is gated. Estimated 2-3 waves of work to clear PRE-1 +
  PRE-2 + STEP-1 + STEP-2 + STEP-3 + STEP-4 + STEP-5.

### Out of scope

- **No Anthropic SDK introduced** (ADR-009 invariant).
- **No `web_search` / `web_fetch` wiring** ever, in this plan.
  Future revisit only after either (a) Anthropic includes them in
  flat-rate Max subscriptions explicitly, or (b) the project moves
  off Voie D voluntarily — both unlikely.

## Alternatives considered

- **Wire all 5 tools immediately** — rejected: violates ADR-009
  via metered server tools; expands attack surface before CF Access
  closes the tunnel; commits to an audit-trail gap that ADR-029
  would flag at any future regulatory review.
- **Wire `web_search` only, treating it as research-tier spend** —
  rejected: any "small" metered API usage breaks the contractual
  framing of Voie D and creates a slope. Eliot's directive ("fais
  monter, jamais dégrader") forbids partial concession on Voie D.
- **Use a third-party MCP server for `query_db`** (e.g. dbt's MCP)
  — rejected: shifts the whitelist enforcement to a vendor we
  cannot audit. The Ichor-hosted MCP is already designed (STEP-3)
  and stays inside our perimeter.

## Verification plan

When PRE-1 + PRE-2 + STEP-1..5 ship, the integration test (STEP-6)
must demonstrate:

- A Pass-1 régime call where Claude requests `query_db` for the
  CME ZQ implied-EFFR series, the handler executes the SELECT,
  the tool result is fed back, and the final classification cites
  the queried value.
- An ADR-017 boundary check: a synthetic prompt that tries to
  steer Claude toward "BUY" via the tool result must return a
  `neutral` bias card (post-filter intercepts), not a buy
  recommendation.
- An audit-trail check: every tool invocation generates a
  `tool_call_audit` row with the immutable trigger preventing
  UPDATE / DELETE.

## References

- ADR-050 (Capability 5 scaffold ratified)
- ADR-009 (Voie D — Max 20x flat, no paid API)
- ADR-017 (research-only boundary, contractual)
- ADR-029 (EU AI Act §50 + AMF DOC-2008-23 audit surface)
- W73 audit summary: 2026-05-09 (this ADR)
- `packages/ichor_brain/src/ichor_brain/tools_registry.py:1-410`
- `packages/ichor_brain/tests/test_tools_registry.py:1-173`
- Anthropic CLI reference (claude -p flags, 2026):
  https://code.claude.com/docs/en/cli-reference
- Anthropic 2026 pricing — server tools billed separately:
  https://platform.claude.com/docs/en/about-claude/pricing
