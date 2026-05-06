# ADR-021: Couche-2 agents route via Claude (Opus/Sonnet/Haiku); Cerebras/Groq are fallback only

- **Status**: Accepted
- **Date**: 2026-05-04
- **Decider**: Eliot (validated 2026-05-04, interview for SPEC.md §3.1)
- **Supersedes**: partial supersede of [ADR-009](ADR-009-voie-d-no-api-consumption.md) §"Couche 2 24/7"

## Context

Phase 1 Step 2 architecture (per ADR-009) routed:

- **Couche 1** (4 daily session cards) via Claude Max 20x.
- **Couche 2** (4 always-on agents — CB-NLP, News-NLP, Sentiment, Positioning)
  via Cerebras free 30 RPM + Groq free 1000 RPD.

In the 2026-05-04 interview Eliot reconsidered: he wants Couche-2 quality
at parity with Couche-1, not a downgrade. His exact phrasing: "Claude est
le meilleur, exploite-le au maximum". Cerebras Llama 3.3-70B and Groq
Mixtral are good but not at Opus 4.7 / Sonnet 4.6 levels for the macro/
sentiment/positioning tasks Couche-2 handles.

Cadencement budget calculated in [`SPEC.md §3.2`](../../SPEC.md):

| Cadence quotidienne       | Calls/day | Model         |
| ------------------------- | --------- | ------------- |
| 4 × session cards × 8     | 32        | Opus + Sonnet |
| Couche-2 CB-NLP (4h)      | 6         | Sonnet 4.6    |
| Couche-2 News-NLP (4h)    | 6         | Sonnet 4.6    |
| Couche-2 Sentiment (6h)   | 4         | Haiku 4.5     |
| Couche-2 Positioning (6h) | 4         | Haiku 4.5     |
| Counterfactual Pass 5     | ~8        | Opus 4.7      |
| Weekly post-mortem        | ~0.14     | Opus 4.7      |
| Bi-monthly meta-prompt    | ~0.07     | Opus 4.7      |

**Total ≈ 60-80 Claude calls/day**, well below the empirical "ordinary
individual use" threshold of Max 20x flat.

## Decision

**All agents (Couche-1 and Couche-2) route via Claude Max 20x through
the local Win11 runner.** Cerebras + Groq remain installed and warm but
**fire only as fallback** — triggered when:

- `claude -p` returns 429 / suspended / 403 for >30 min sustained, OR
- the local runner is down for >5 min (network / process crash), OR
- the runbook in [RUNBOOK-008](../runbooks/RUNBOOK-008-anthropic-key-revoked.md)
  is manually activated.

Default Couche-2 mapping:

| Agent       | Model      | Cadence  | Fallback target |
| ----------- | ---------- | -------- | --------------- |
| CB-NLP      | Sonnet 4.6 | every 4h | Groq Mixtral    |
| News-NLP    | Sonnet 4.6 | every 4h | Groq Mixtral    |
| Sentiment   | Haiku 4.5  | every 6h | Cerebras 70B    |
| Positioning | Haiku 4.5  | every 6h | Cerebras 70B    |

Risk of Anthropic Max 20x ban is **explicitly accepted** by Eliot (already
flagged in [`docs/ARCHITECTURE_FINALE.md`](../ARCHITECTURE_FINALE.md):14-25);
this ADR re-affirms after a second-order risk review of the new
calibration.

## Consequences

**Easier**:

- Single LLM brain across all qualitative analysis layers; no quality
  fragmentation between Couche-1 and Couche-2 outputs.
- Operational simplicity: one runtime, one auth, one ratelimit envelope.
- Cost stays at $200/mo flat (Voie D unchanged).

**Harder**:

- Slightly higher load on the local runner; cron schedule must avoid
  bursts (staggered start times in
  [`scripts/hetzner/register-cron-couche2.sh`](../../scripts/hetzner/) — to
  be created in Phase B).
- Ban risk still present. RUNBOOK-008 + RUNBOOK-013 must be drilled.

**Trade-offs**:

- Couche-2 latency goes up vs Cerebras (Cerebras p50 ≈ 200 ms, Claude p50
  ≈ 2-3 s). Acceptable: Couche-2 is async batch, not interactive.
- We commit harder to Voie D — if banned, fallback chain is a real
  step-down in quality, not just availability.

## Alternatives considered

- **Keep Cerebras/Groq as primary** (status quo per original ADR-009):
  rejected. Eliot prefers consistent Opus/Sonnet/Haiku quality even at
  the cost of higher ban risk surface.
- **Mixed primary** (Couche-1 = Claude, Couche-2 = Cerebras/Groq with
  occasional Claude bursts): rejected. Operational complexity, two prompt
  engineering surfaces to maintain.
- **Claude API direct** (paid): rejected by ADR-009 (no API consumption,
  no surprise costs).

## References

- [`SPEC.md §3.1, §3.2, §3.13`](../../SPEC.md)
- [`docs/ARCHITECTURE_FINALE.md`](../ARCHITECTURE_FINALE.md)
- [ADR-009 (Voie D)](ADR-009-voie-d-no-api-consumption.md)
- [RUNBOOK-008](../runbooks/RUNBOOK-008-anthropic-key-revoked.md)
- [RUNBOOK-013](../runbooks/RUNBOOK-013-claude-max-quota-saturated.md) (companion)
