# ADR-023: Couche-2 routes via Claude Haiku low effort, not Sonnet medium

- **Status**: Accepted
- **Date**: 2026-05-06
- **Decider**: Eliot (validated 2026-05-06 during the Couche-2 → Claude
  end-to-end activation sprint)
- **Supersedes**: partial supersede of [ADR-021](ADR-021-couche2-via-claude-not-fallback.md)
  §"Default Couche-2 mapping" (Sonnet 4.6 for CB-NLP/News-NLP/Macro,
  Haiku 4.5 for Sentiment/Positioning)

## Context

[ADR-021](ADR-021-couche2-via-claude-not-fallback.md) wired the five
Couche-2 agents to route through the local Win11 claude-runner. The
mapping it specified was:

| Agent       | Model      | Effort   |
| ----------- | ---------- | -------- |
| CB-NLP      | Sonnet 4.6 | medium   |
| News-NLP    | Sonnet 4.6 | medium   |
| Macro       | Sonnet 4.6 | medium   |
| Sentiment   | Haiku 4.5  | low      |
| Positioning | Haiku 4.5  | low      |

When the actual implementation landed (2026-05-06, [packages/agents/src/ichor_agents/claude_runner.py](../../packages/agents/src/ichor_agents/claude_runner.py)
+ [fallback.py](../../packages/agents/src/ichor_agents/fallback.py)),
end-to-end testing on Hetzner showed that the **Cloudflare Free tier
imposes a 100-second hard timeout on tunneled requests**. The
`claude-runner.fxmilyapp.com` tunnel sits on Free, and Sonnet medium
on a 5 KB Couche-2 prompt routinely runs 60-120 s — past the cutoff
~60 % of the time, surfacing as HTTP 524 from Cloudflare's edge.

Empirical numbers from the validation run (2026-05-06 01:43-01:55 UTC):

| Model+Effort     | Cold prompt 5 KB | Tunnel verdict |
| ---------------- | ---------------- | -------------- |
| Sonnet medium    | 60 s - 130 s     | 524 if > 100 s |
| Haiku low        | 18 s - 45 s      | always under   |

## Decision

**All five Couche-2 agents route via Claude Haiku 4.5, effort `low`.**

| Agent       | Model     | Effort | Why                                     |
| ----------- | --------- | ------ | --------------------------------------- |
| CB-NLP      | Haiku 4.5 | low    | 100 s tunnel cap                        |
| News-NLP    | Haiku 4.5 | low    | 100 s tunnel cap                        |
| Macro       | Haiku 4.5 | low    | 100 s tunnel cap                        |
| Sentiment   | Haiku 4.5 | low    | unchanged (was already this combo)      |
| Positioning | Haiku 4.5 | low    | unchanged (was already this combo)      |

Cerebras + Groq remain the transparent fallback per ADR-021.
[apps/claude-runner/src/ichor_claude_runner/main.py:255](../../apps/claude-runner/src/ichor_claude_runner/main.py:255)
exposes the new `POST /v1/agent-task` endpoint that handles these
calls.

## Consequences

**Easier**:

- Couche-2 batch latency drops from p95 ≈ 110 s to p95 ≈ 35 s.
- 524-driven AllProvidersFailed stops cluttering `couche2_outputs`.
- Quota footprint on Max 20x is meaningfully smaller — Haiku 4.5
  uses ~⅓ the tokens of Sonnet 4.6 for equivalent output.

**Harder**:

- Couche-2 quality ceiling drops slightly. Haiku 4.5 is excellent at
  structured extraction (CB rhetoric scoring, narrative tagging,
  positioning extremes) but trails Sonnet 4.6 on multi-step
  reasoning. For Couche-2's pattern (read → score → emit JSON), this
  gap is small and accepted.
- Re-introducing Sonnet for CB-NLP/News-NLP/Macro will require either
  upgrading the Cloudflare plan (Pro: 600 s; Enterprise: 6000 s) or
  switching the tunnel to a chunk-streaming protocol that resets
  Cloudflare's idle timer. Both are out of scope for now.

**Trade-offs**:

- ADR-021's "single LLM brain across Couche-1 and Couche-2" claim
  weakens slightly: Couche-1 stays on Opus/Sonnet for session cards
  while Couche-2 sits on Haiku. The provider chain is unchanged
  (Claude → Cerebras → Groq) — only the model knob inside the Claude
  call differs.

## Alternatives considered

- **Keep Sonnet medium and rely on retry**: rejected. The 100 s cap
  is a Cloudflare-side guarantee, not a transient failure. A retry
  hits the same 524 every time.
- **Add a `/v1/agent-task-async` poll endpoint**: deferred. Workable
  (return 202 + task_id, poll for result) but adds significant
  complexity to the runner, the FallbackChain adapter, and the
  Couche-2 CLI. Revisit if we need Sonnet quality and stay on Free.
- **Upgrade Cloudflare plan**: out of budget for now ($240/mo Pro).
  Will reconsider if Couche-2 quality on Haiku proves insufficient.
- **Self-host without tunnel**: rejected. Voie D constraint requires
  the `claude` binary to run on Eliot's Max 20x machine — we cannot
  expose a public origin from a residential IP, and the tunnel is
  what makes the architecture work.

## References

- [ADR-009 (Voie D)](ADR-009-voie-d-no-api-consumption.md)
- [ADR-021 (Couche-2 via Claude)](ADR-021-couche2-via-claude-not-fallback.md)
- [`packages/agents/src/ichor_agents/claude_runner.py`](../../packages/agents/src/ichor_agents/claude_runner.py)
- [`packages/agents/src/ichor_agents/fallback.py`](../../packages/agents/src/ichor_agents/fallback.py)
- [`apps/claude-runner/src/ichor_claude_runner/main.py`](../../apps/claude-runner/src/ichor_claude_runner/main.py)
- [Cloudflare 524 limits documentation](https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/troubleshooting-cloudflare-5xx-errors/#error-524-a-timeout-occurred)
