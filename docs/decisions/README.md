# Architecture Decision Records (ADR)

> Format: lightly adapted from [Michael Nygard's template](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
> One file per decision, immutable once `Status: Accepted`. To revise, write a
> new ADR that supersedes the older one.

## Index

| ADR                                                          | Status   | Title                                                           | Date       |
| ------------------------------------------------------------ | -------- | --------------------------------------------------------------- | ---------- |
| [001](ADR-001-stack-versions-2026-05-02.md)                  | Accepted | Lock stack versions verified 2026-05-02                         | 2026-05-02 |
| [002](ADR-002-domain-deferred.md)                            | Accepted | Defer `ichor.app` domain purchase to Phase 1+                   | 2026-05-02 |
| [003](ADR-003-cleanup-vs-wipe.md)                            | Accepted | Hetzner: chirurgical cleanup instead of full wipe               | 2026-05-02 |
| [004](ADR-004-node-22-not-20.md)                             | Accepted | Use Node 22 LTS instead of plan's Node 20                       | 2026-05-02 |
| [005](ADR-005-apache-age-built-from-source.md)               | Accepted | Apache AGE built from source (no Ubuntu apt package)            | 2026-05-02 |
| [006](ADR-006-pnpm-via-official-installer.md)                | Accepted | pnpm via official Win installer (Corepack fails)                | 2026-05-02 |
| [007](ADR-007-ansible-bootstrap-from-hetzner.md)             | Accepted | Run Ansible from Hetzner itself, not local Win11                | 2026-05-02 |
| [008](ADR-008-redis-8-not-7.md)                              | Accepted | Accept Redis 8.x (apt repo serves 8, not 7)                     | 2026-05-02 |
| [009](ADR-009-voie-d-no-api-consumption.md)                  | Accepted | Voie D — no API consumption, $200/mo flat                       | 2026-05-02 |
| [010](ADR-010-claude-cli-org-403.md)                         | Accepted | Claude CLI org access 403 — workaround                          | 2026-05-02 |
| [011](ADR-011-cloudflare-tunnel-needs-domain-or-warp.md)     | Accepted | Cloudflare Tunnel needs domain or WARP                          | 2026-05-02 |
| [012](ADR-012-market-data-stooq-yfinance.md)                 | Accepted | Market data: Stooq + yfinance fallback                          | 2026-05-03 |
| [013](ADR-013-rich-briefing-context-feature-flag.md)         | Accepted | Rich briefing context as feature flag                           | 2026-05-03 |
| ~~014~~ to ~~016~~                                           | Archived | Pre-reset Phase 1 decisions (superseded by ADR-017)             | 2026-05-03 |
| [017](ADR-017-reset-phase1-living-macro-entity.md)           | Accepted | Reset Phase 1 — Living Macro Entity (CONTRACTUAL)               | 2026-05-03 |
| [018](ADR-018-frontend-rebuild-phase-2.md)                   | Accepted | Frontend rebuild from-scratch in `apps/web2/` (Phase 2)         | 2026-05-04 |
| [019](ADR-019-pgvector-hnsw-not-ivfflat.md)                  | Accepted | pgvector index = HNSW (not IVFFlat) `m=16 ef_construction=64`   | 2026-05-04 |
| [020](ADR-020-rag-embeddings-bge-small.md)                   | Accepted | RAG embeddings = `bge-small-en-v1.5` self-host CPU              | 2026-05-04 |
| [021](ADR-021-couche2-via-claude-not-fallback.md)            | Accepted | Couche-2 via Claude (Cerebras/Groq fallback only)               | 2026-05-04 |
| [022](ADR-022-probability-bias-models-reinstated.md)         | Accepted | Probability-only bias models reinstated under Critic gate       | 2026-05-05 |
| [023](ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md) | Accepted | Couche-2 → Claude Haiku low (CF Free 100s tunnel cap)           | 2026-05-06 |
| [024](ADR-024-session-cards-five-bug-fix.md)                 | Accepted | session-cards 4-pass — five-bug fix and ny_mid/ny_close enable  | 2026-05-06 |
| [025](ADR-025-brier-optimizer-v2-projected-sgd.md)           | Accepted | Brier optimizer V2 — projected SGD on per-factor drivers matrix | 2026-05-06 |
| [026](ADR-026-frontend-perfection-wcag22aa-lighthouse.md)    | Accepted | Frontend WCAG 2.2 AA + Lighthouse CI gates                      | 2026-05-07 |
| [027](ADR-027-playwright-golden-paths-axe-core.md)           | Accepted | Playwright golden paths + axe-core a11y                         | 2026-05-07 |
| [028](ADR-028-wave5-ci-strategy-incremental.md)              | Accepted | Wave 5 CI strategy — incremental ramp                           | 2026-05-07 |
| [029](ADR-029-eu-ai-act-50-amf-doc-2008-23-disclosure.md)    | Accepted | EU AI Act §50 + AMF DOC-2008-23 disclosure surface              | 2026-05-07 |
| [030](ADR-030-resolvecron-protection-post-incident.md)       | Accepted | register-cron-*.sh canonical protection (post-incident)         | 2026-05-07 |
| [031](ADR-031-sessiontype-single-source-via-get-args.md)     | Accepted | SessionType single source via `get_args(SessionType)`           | 2026-05-07 |
| [032](ADR-032-langfuse-observe-wiring.md)                    | Accepted | Langfuse @observe wiring (Phase A.4.c)                          | 2026-05-07 |
| [033](ADR-033-data-surprise-z-alert.md)                      | Accepted | DATA_SURPRISE_Z alert (Phase D.5)                               | 2026-05-07 |
| [034](ADR-034-real-yield-gold-divergence-alert.md)           | Accepted | REAL_YIELD_GOLD_DIVERGENCE alert                                | 2026-05-07 |
| [035](ADR-035-quad-witching-alert.md)                        | Accepted | QUAD_WITCHING alert                                             | 2026-05-07 |
| [036](ADR-036-geopol-flash-event-alert.md)                   | Accepted | GEOPOL_FLASH_EVENT alert                                        | 2026-05-07 |
| [037](ADR-037-tariff-shock-alert.md)                         | Accepted | TARIFF_SHOCK alert                                              | 2026-05-07 |
| [038](ADR-038-megacap-earnings-window-alert.md)              | Accepted | MEGACAP_EARNINGS_WINDOW alert                                   | 2026-05-07 |
| [039](ADR-039-geopol-regime-structural-alert.md)             | Accepted | GEOPOL_REGIME_STRUCTURAL alert                                  | 2026-05-07 |
| [040](ADR-040-multi-cb-tone-foundation.md)                   | Accepted | Multi-CB tone foundation (FED + ECB + BoE + BoJ)                | 2026-05-07 |
| [041](ADR-041-term-premium-repricing-alert.md)               | Accepted | TERM_PREMIUM_REPRICING alert                                    | 2026-05-07 |
| [042](ADR-042-macro-quartet-stress-alert.md)                 | Accepted | MACRO_QUARTET_STRESS alert (4-of-4 composite)                   | 2026-05-07 |
| [043](ADR-043-dollar-smile-break-alert.md)                   | Accepted | DOLLAR_SMILE_BREAK alert (Stephen Jen 2025-26 thesis)           | 2026-05-07 |
| [044](ADR-044-vix-term-inversion-alert.md)                   | Accepted | VIX_TERM_INVERSION alert                                        | 2026-05-07 |
| [045](ADR-045-term-premium-structural-252d-alert.md)         | Accepted | TERM_PREMIUM_STRUCTURAL_252D alert                              | 2026-05-07 |
| [046](ADR-046-yield-curve-inversion-deep-alert.md)           | Accepted | YIELD_CURVE_INVERSION_DEEP alert                                | 2026-05-07 |
| [047](ADR-047-yield-curve-un-inversion-event-alert.md)       | Accepted | YIELD_CURVE_UN_INVERSION_EVENT alert                            | 2026-05-07 |
| [048](ADR-048-treasury-vol-spike-alert.md)                   | Accepted | TREASURY_VOL_SPIKE alert                                        | 2026-05-07 |
| [049](ADR-049-hy-ig-spread-divergence-alert.md)              | Accepted | HY_IG_SPREAD_DIVERGENCE alert                                   | 2026-05-07 |
| [050](ADR-050-capability-5-tools-runtime.md)                 | Accepted | Capability 5 tools runtime scaffold (wiring deferred Phase D.0) | 2026-05-08 |
| [051](ADR-051-macro-quintet-stress-alert.md)                 | Accepted | MACRO_QUINTET_STRESS alert (5-dim composite)                    | 2026-05-08 |
| [052](ADR-052-term-premium-intraday-30d-alert.md)            | Accepted | TERM_PREMIUM_INTRADAY_30D alert                                 | 2026-05-08 |
| [053](ADR-053-claude-runner-async-polling-refactor.md)       | Accepted | claude-runner async + polling (CF 100s edge timeout fix)        | 2026-05-08 |
| [054](ADR-054-claude-runner-stdin-pipe-windows-argv-limit.md) | Accepted | claude-runner stdin pipe (Windows argv 32K limit BLOCKER #2)    | 2026-05-08 |
| [055](ADR-055-dollar-smile-break-skew-extension.md)          | Accepted | DOLLAR_SMILE_BREAK extended with SKEW (4-of-4 → 5-of-5)         | 2026-05-08 |
| [067](ADR-067-couche2-async-polling-migration.md)            | Accepted | Couche-2 async polling migration (CF 100s structural fix)       | 2026-05-09 |
| [068](ADR-068-cb-nlp-prompt-redesign-content-refusal.md)     | Accepted | cb_nlp prompt redesign — Claude content refusal fix             | 2026-05-09 |
| [069](ADR-069-nyfed-mct-collector-replaces-uig.md)           | Accepted | NY Fed MCT collector replaces discontinued FRED UIGFULL         | 2026-05-09 |
| [070](ADR-070-cleveland-fed-nowcast-collector.md)            | Accepted | Cleveland Fed Inflation Nowcast collector (4×3 daily surface)   | 2026-05-09 |
| [071](ADR-071-capability-5-deferral-client-tools-only.md)    | Accepted | Capability 5 — defer wiring, restrict to client tools           | 2026-05-09 |
| [072](ADR-072-ansible-ichor-packages-role.md)                | Accepted | Ansible ichor_packages role — sync packages-staging declaratively | 2026-05-09 |
| [073](ADR-073-nfib-sbet-pdf-collector.md)                    | Accepted | NFIB SBET PDF collector (SBOI + Uncertainty Index)              | 2026-05-09 |
| [074](ADR-074-myfxbook-replaces-oanda-orderbook.md)          | Accepted | MyFXBook Community Outlook replaces discontinued OANDA orderbook | 2026-05-09 |
| [071](ADR-071-capability-5-deferral-client-tools-only.md)    | Accepted | Capability 5 deferral — client tools only, sequence pre-reqs    | 2026-05-09 |

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
