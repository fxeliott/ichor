# Architecture Decision Records (ADR)

> Format: lightly adapted from [Michael Nygard's template](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
> One file per decision, immutable once `Status: Accepted`. To revise, write a
> new ADR that supersedes the older one.

## Index

| ADR | Status | Title | Date |
|-----|--------|-------|------|
| [001](ADR-001-stack-versions-2026-05-02.md) | Accepted | Lock stack versions verified 2026-05-02 | 2026-05-02 |
| [002](ADR-002-domain-deferred.md) | Accepted | Defer `ichor.app` domain purchase to Phase 1+ | 2026-05-02 |
| [003](ADR-003-cleanup-vs-wipe.md) | Accepted | Hetzner: chirurgical cleanup instead of full wipe | 2026-05-02 |
| [004](ADR-004-node-22-not-20.md) | Accepted | Use Node 22 LTS instead of plan's Node 20 | 2026-05-02 |
| [005](ADR-005-apache-age-built-from-source.md) | Accepted | Apache AGE built from source (no Ubuntu apt package) | 2026-05-02 |
| [006](ADR-006-pnpm-via-official-installer.md) | Accepted | pnpm via official Win installer (Corepack fails) | 2026-05-02 |
| [007](ADR-007-ansible-bootstrap-from-hetzner.md) | Accepted | Run Ansible from Hetzner itself, not local Win11 | 2026-05-02 |

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
