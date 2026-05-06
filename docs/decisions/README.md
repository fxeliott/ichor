# Architecture Decision Records (ADR)

> Format: lightly adapted from [Michael Nygard's template](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
> One file per decision, immutable once `Status: Accepted`. To revise, write a
> new ADR that supersedes the older one.

## Index

| ADR                                                      | Status   | Title                                                         | Date       |
| -------------------------------------------------------- | -------- | ------------------------------------------------------------- | ---------- |
| [001](ADR-001-stack-versions-2026-05-02.md)              | Accepted | Lock stack versions verified 2026-05-02                       | 2026-05-02 |
| [002](ADR-002-domain-deferred.md)                        | Accepted | Defer `ichor.app` domain purchase to Phase 1+                 | 2026-05-02 |
| [003](ADR-003-cleanup-vs-wipe.md)                        | Accepted | Hetzner: chirurgical cleanup instead of full wipe             | 2026-05-02 |
| [004](ADR-004-node-22-not-20.md)                         | Accepted | Use Node 22 LTS instead of plan's Node 20                     | 2026-05-02 |
| [005](ADR-005-apache-age-built-from-source.md)           | Accepted | Apache AGE built from source (no Ubuntu apt package)          | 2026-05-02 |
| [006](ADR-006-pnpm-via-official-installer.md)            | Accepted | pnpm via official Win installer (Corepack fails)              | 2026-05-02 |
| [007](ADR-007-ansible-bootstrap-from-hetzner.md)         | Accepted | Run Ansible from Hetzner itself, not local Win11              | 2026-05-02 |
| [008](ADR-008-redis-8-not-7.md)                          | Accepted | Accept Redis 8.x (apt repo serves 8, not 7)                   | 2026-05-02 |
| [009](ADR-009-voie-d-no-api-consumption.md)              | Accepted | Voie D — no API consumption, $200/mo flat                     | 2026-05-02 |
| [010](ADR-010-claude-cli-org-403.md)                     | Accepted | Claude CLI org access 403 — workaround                        | 2026-05-02 |
| [011](ADR-011-cloudflare-tunnel-needs-domain-or-warp.md) | Accepted | Cloudflare Tunnel needs domain or WARP                        | 2026-05-02 |
| [012](ADR-012-market-data-stooq-yfinance.md)             | Accepted | Market data: Stooq + yfinance fallback                        | 2026-05-03 |
| [013](ADR-013-rich-briefing-context-feature-flag.md)     | Accepted | Rich briefing context as feature flag                         | 2026-05-03 |
| ~~014~~ to ~~016~~                                       | Archived | Pre-reset Phase 1 decisions (superseded by ADR-017)           | 2026-05-03 |
| [017](ADR-017-reset-phase1-living-macro-entity.md)       | Accepted | Reset Phase 1 — Living Macro Entity (CONTRACTUAL)             | 2026-05-03 |
| [018](ADR-018-frontend-rebuild-phase-2.md)               | Accepted | Frontend rebuild from-scratch in `apps/web2/` (Phase 2)       | 2026-05-04 |
| [019](ADR-019-pgvector-hnsw-not-ivfflat.md)              | Accepted | pgvector index = HNSW (not IVFFlat) `m=16 ef_construction=64` | 2026-05-04 |
| [020](ADR-020-rag-embeddings-bge-small.md)               | Accepted | RAG embeddings = `bge-small-en-v1.5` self-host CPU            | 2026-05-04 |
| [021](ADR-021-couche2-via-claude-not-fallback.md)        | Accepted | Couche-2 via Claude (Cerebras/Groq fallback only)             | 2026-05-04 |
| [022](ADR-022-probability-bias-models-reinstated.md)     | Accepted | Probability-only bias models reinstated under Critic gate     | 2026-05-05 |
| [023](ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md) | Accepted | Couche-2 → Claude Haiku low (CF Free 100s tunnel cap)     | 2026-05-06 |
| [024](ADR-024-session-cards-five-bug-fix.md)             | Accepted | session-cards 4-pass — five-bug fix and ny_mid/ny_close enable | 2026-05-06 |
| [025](ADR-025-brier-optimizer-v2-projected-sgd.md)       | Accepted | Brier optimizer V2 — projected SGD on per-factor drivers matrix | 2026-05-06 |

> **Note**: SPEC_V2_HARDENING.md §4 originally referred to "ADR-008 to
> ADR-011 prévus" for Phase 2 decisions. Those numbers were already taken
> by Accepted ADRs from 2026-05-02 (Redis 8, Voie D, Claude CLI 403, CF
> Tunnel). Phase 2 ADRs are renumbered **018–021** above; SPEC_V2_HARDENING
> will be resync'd in Phase D documentation pass.

## How to write a new ADR

1. Copy the template below into `ADR-NNN-short-slug.md` (NNN = next number).
2. Fill in Context / Decision / Consequences (concrete, not abstract).
3. Set `Status: Proposed` while drafting; flip to `Accepted` once Eliot agrees.
4. Update the index above (in alphabetical-then-chronological order).
5. Commit alongside the code change that the decision affects.

```markdown
# ADR-NNN: <decision title>

- **Status**: Proposed | Accepted | Superseded by [ADR-XXX](...)
- **Date**: YYYY-MM-DD
- **Decider**: Eliot (validated <date>)

## Context

<What's the situation? What constraints / forces are at play?>

## Decision

<The decision in one sentence. Then specifics.>

## Consequences

<What becomes easier? Harder? What did we trade off?>

## Alternatives considered

<List 1-3 alternatives with one-line reason for rejection.>

## References

<Links to specs, audits, RFCs, vendor docs.>
```
