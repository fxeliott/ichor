# ADR-108 — §11 full-Opus everywhere (supersedes ADR-023 model choice)

**Status** : Accepted (2026-06-02)

**Supersedes** : ADR-023 (Couche-2 Haiku-not-Sonnet) — only its _model
choice_. ADR-023's reasoning about the Cloudflare Free 100 s edge cap on the
legacy sync endpoint remains historically valid; it is simply no longer
binding because Wave 67 moved Couche-2 to the CF-edge-immune async path.

## Context

Eliot's Prompt_Ichor §11 is explicit and non-negotiable: **every local Claude
call must run on Opus 4.8 at full performance — no exceptions.** Before this
ADR, Ichor's model assignment was mixed:

- 4-pass session-card analysis : **Opus 4.8 high** ✓ (already compliant — the
  deep analysis that produces the verdict)
- Pass-6 scenario decomposition : Sonnet medium
- Macro briefings (`run_briefing`) : Sonnet (except weekly/crisis = Opus)
- Couche-2 extraction agents (cb_nlp, news_nlp, sentiment, positioning,
  macro) : Haiku low (ADR-023)

ADR-023 pinned Couche-2 to Haiku because Sonnet medium exceeded the
Cloudflare Free tunnel's 100 s edge timeout on the **legacy synchronous**
`/v1/agent-task` endpoint (60-130 s observed). **Wave 67 (ADR-067) added the
async-polling endpoint** (`/v1/agent-task/async` + `call_agent_task_async`),
and `FallbackChain.use_async_endpoint` defaults to `True`. Each poll returns
in <1 s, so the subprocess wall-time is no longer bounded by the CF edge cap.
The original blocker for non-Haiku models on Couche-2 is therefore gone.

## Decision

Run **Opus 4.8 everywhere**:

| Surface              | Before          | After                     |
| -------------------- | --------------- | ------------------------- |
| 4-pass analysis      | opus high       | opus high (unchanged)     |
| Pass-6 scenarios     | sonnet medium   | **opus high**             |
| Macro briefings      | sonnet (mostly) | **opus high (all types)** |
| Couche-2 agents (×5) | haiku low       | **opus low**              |

`effort` stays `low` for the Couche-2 agents because they are
structured-extraction tasks (tone / themes / positioning → JSON), not deep
reasoning; `high` would only add latency and budget with no quality gain.
The four reasoning surfaces (4-pass, Pass-6, briefings) run `high`.

## Consequences

- **Voie D held**: same Max 20x flat subscription, zero Anthropic API spend.
- **Budget / rate**: Opus everywhere ~doubles Ichor's Opus footprint. The
  Max 20x has a rolling 5 h cap shared with Eliot's interactive Claude Code
  usage. Under heavy concurrent load the runner throttles (slower / occasional
  empty responses). This degrades **gracefully**: the orchestrator retries
  once on a parse/empty error, and a card/briefing that still fails is simply
  not refreshed — the honest freshness banner surfaces it as "not up to date"
  rather than crashing. No silent corruption.
- **Reversible**: each surface is a one-line model string
  (`orchestrator.scenarios_model`, `run_briefing` payload model,
  `ClaudeRunnerConfig.model`). Roll back to the lighter model if the budget
  proves insufficient in sustained production.
- **CI guards updated** (`test_invariants_ichor.py`): `sonnet` remains
  forbidden on Couche-2; the positive guard now asserts `"opus"` is
  referenced (was `"haiku"`).

## Invariant (CI-guarded)

Couche-2 agent modules MUST NOT hard-code `"sonnet"` and MUST reference
`"opus"`. The async path (`use_async_endpoint=True`) is the precondition that
makes non-Haiku models safe on the CF tunnel.
