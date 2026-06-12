# Architecture Decision Records (ADR)

> Format: lightly adapted from [Michael Nygard's template](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
> One file per decision, immutable once `Status: Accepted`. To revise, write a
> new ADR that supersedes the older one.

## Index

| ADR                                                                     | Status   | Title                                                                  | Date       |
| ----------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------- | ---------- |
| [001](ADR-001-stack-versions-2026-05-02.md)                             | Accepted | Lock stack versions verified 2026-05-02                                | 2026-05-02 |
| [002](ADR-002-domain-deferred.md)                                       | Accepted | Defer `ichor.app` domain purchase to Phase 1+                          | 2026-05-02 |
| [003](ADR-003-cleanup-vs-wipe.md)                                       | Accepted | Hetzner: chirurgical cleanup instead of full wipe                      | 2026-05-02 |
| [004](ADR-004-node-22-not-20.md)                                        | Accepted | Use Node 22 LTS instead of plan's Node 20                              | 2026-05-02 |
| [005](ADR-005-apache-age-built-from-source.md)                          | Accepted | Apache AGE built from source (no Ubuntu apt package)                   | 2026-05-02 |
| [006](ADR-006-pnpm-via-official-installer.md)                           | Accepted | pnpm via official Win installer (Corepack fails)                       | 2026-05-02 |
| [007](ADR-007-ansible-bootstrap-from-hetzner.md)                        | Accepted | Run Ansible from Hetzner itself, not local Win11                       | 2026-05-02 |
| [008](ADR-008-redis-8-not-7.md)                                         | Accepted | Accept Redis 8.x (apt repo serves 8, not 7)                            | 2026-05-02 |
| [009](ADR-009-voie-d-no-api-consumption.md)                             | Accepted | Voie D — no API consumption, $200/mo flat                              | 2026-05-02 |
| [010](ADR-010-claude-cli-org-access-403.md)                             | Accepted | Claude CLI org access 403 — workaround                                 | 2026-05-02 |
| [011](ADR-011-cloudflare-tunnel-needs-domain-or-warp.md)                | Accepted | Cloudflare Tunnel needs domain or WARP                                 | 2026-05-02 |
| [012](ADR-012-market-data-stooq-yfinance.md)                            | Accepted | Market data: Stooq + yfinance fallback                                 | 2026-05-03 |
| [013](ADR-013-rich-briefing-context-feature-flag.md)                    | Accepted | Rich briefing context as feature flag                                  | 2026-05-03 |
| ~~014~~ to ~~016~~                                                      | Archived | Pre-reset Phase 1 decisions (superseded by ADR-017)                    | 2026-05-03 |
| [017](ADR-017-reset-phase1-living-macro-entity.md)                      | Accepted | Reset Phase 1 — Living Macro Entity (CONTRACTUAL)                      | 2026-05-03 |
| [018](ADR-018-frontend-rebuild-phase-2.md)                              | Accepted | Frontend rebuild from-scratch in `apps/web2/` (Phase 2)                | 2026-05-04 |
| [019](ADR-019-pgvector-hnsw-not-ivfflat.md)                             | Accepted | pgvector index = HNSW (not IVFFlat) `m=16 ef_construction=64`          | 2026-05-04 |
| [020](ADR-020-rag-embeddings-bge-small.md)                              | Accepted | RAG embeddings = `bge-small-en-v1.5` self-host CPU                     | 2026-05-04 |
| [021](ADR-021-couche2-via-claude-not-fallback.md)                       | Accepted | Couche-2 via Claude (Cerebras/Groq fallback only)                      | 2026-05-04 |
| [022](ADR-022-probability-bias-models-reinstated.md)                    | Accepted | Probability-only bias models reinstated under Critic gate              | 2026-05-05 |
| [023](ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)            | Accepted | Couche-2 → Claude Haiku low (CF Free 100s tunnel cap)                  | 2026-05-06 |
| [024](ADR-024-session-cards-five-bug-fix.md)                            | Accepted | session-cards 4-pass — five-bug fix and ny_mid/ny_close enable         | 2026-05-06 |
| [025](ADR-025-brier-optimizer-v2-projected-sgd.md)                      | Accepted | Brier optimizer V2 — projected SGD on per-factor drivers matrix        | 2026-05-06 |
| [026](ADR-026-frontend-perfection-wcag22aa-lighthouse.md)               | Accepted | Frontend WCAG 2.2 AA + Lighthouse CI gates                             | 2026-05-07 |
| [027](ADR-027-playwright-golden-paths-axe-core.md)                      | Accepted | Playwright golden paths + axe-core a11y                                | 2026-05-07 |
| [028](ADR-028-wave5-ci-strategy-incremental.md)                         | Accepted | Wave 5 CI strategy — incremental ramp                                  | 2026-05-07 |
| [029](ADR-029-eu-ai-act-50-amf-doc-2008-23-disclosure.md)               | Accepted | EU AI Act §50 + AMF DOC-2008-23 disclosure surface                     | 2026-05-07 |
| [030](ADR-030-resolvecron-protection-post-incident.md)                  | Accepted | register-cron-\*.sh canonical protection (post-incident)               | 2026-05-07 |
| [031](ADR-031-sessiontype-single-source-via-get-args.md)                | Accepted | SessionType single source via `get_args(SessionType)`                  | 2026-05-07 |
| [032](ADR-032-langfuse-observe-wiring.md)                               | Accepted | Langfuse @observe wiring (Phase A.4.c)                                 | 2026-05-07 |
| [033](ADR-033-data-surprise-z-alert.md)                                 | Accepted | DATA_SURPRISE_Z alert (Phase D.5)                                      | 2026-05-07 |
| [034](ADR-034-real-yield-gold-divergence-alert.md)                      | Accepted | REAL_YIELD_GOLD_DIVERGENCE alert                                       | 2026-05-07 |
| [035](ADR-035-quad-witching-opex-alerts.md)                             | Accepted | QUAD_WITCHING alert                                                    | 2026-05-07 |
| [036](ADR-036-geopol-flash-alert.md)                                    | Accepted | GEOPOL_FLASH_EVENT alert                                               | 2026-05-07 |
| [037](ADR-037-tariff-shock-alert.md)                                    | Accepted | TARIFF_SHOCK alert                                                     | 2026-05-07 |
| [038](ADR-038-megacap-earnings-t1-alert.md)                             | Accepted | MEGACAP_EARNINGS_WINDOW alert                                          | 2026-05-07 |
| [039](ADR-039-geopol-regime-structural-alert.md)                        | Accepted | GEOPOL_REGIME_STRUCTURAL alert                                         | 2026-05-07 |
| [040](ADR-040-boe-boj-tone-shift-alerts.md)                             | Accepted | Multi-CB tone foundation (FED + ECB + BoE + BoJ)                       | 2026-05-07 |
| [041](ADR-041-term-premium-repricing-alert.md)                          | Accepted | TERM_PREMIUM_REPRICING alert                                           | 2026-05-07 |
| [042](ADR-042-macro-quartet-stress-alert.md)                            | Accepted | MACRO_QUARTET_STRESS alert (4-of-4 composite)                          | 2026-05-07 |
| [043](ADR-043-dollar-smile-break-alert.md)                              | Accepted | DOLLAR_SMILE_BREAK alert (Stephen Jen 2025-26 thesis)                  | 2026-05-07 |
| [044](ADR-044-vix-term-inversion-alert.md)                              | Accepted | VIX_TERM_INVERSION alert                                               | 2026-05-07 |
| [045](ADR-045-term-premium-structural-252d-alert.md)                    | Accepted | TERM_PREMIUM_STRUCTURAL_252D alert                                     | 2026-05-07 |
| [046](ADR-046-yield-curve-inversion-deep-alert.md)                      | Accepted | YIELD_CURVE_INVERSION_DEEP alert                                       | 2026-05-07 |
| [047](ADR-047-yield-curve-un-inversion-event-alert.md)                  | Accepted | YIELD_CURVE_UN_INVERSION_EVENT alert                                   | 2026-05-07 |
| [048](ADR-048-treasury-vol-spike-alert.md)                              | Accepted | TREASURY_VOL_SPIKE alert                                               | 2026-05-07 |
| [049](ADR-049-hy-ig-spread-divergence-alert.md)                         | Accepted | HY_IG_SPREAD_DIVERGENCE alert                                          | 2026-05-07 |
| [050](ADR-050-capability-5-tools-runtime.md)                            | Accepted | Capability 5 tools runtime scaffold (wiring deferred Phase D.0)        | 2026-05-08 |
| [051](ADR-051-macro-quintet-stress-alert.md)                            | Accepted | MACRO_QUINTET_STRESS alert (5-dim composite)                           | 2026-05-08 |
| [052](ADR-052-term-premium-intraday-30d-alert.md)                       | Accepted | TERM_PREMIUM_INTRADAY_30D alert                                        | 2026-05-08 |
| [053](ADR-053-claude-runner-async-polling-refactor.md)                  | Accepted | claude-runner async + polling (CF 100s edge timeout fix)               | 2026-05-08 |
| [054](ADR-054-claude-runner-stdin-pipe-windows-argv-limit.md)           | Accepted | claude-runner stdin pipe (Windows argv 32K limit BLOCKER #2)           | 2026-05-08 |
| [055](ADR-055-dollar-smile-break-skew-extension.md)                     | Accepted | DOLLAR_SMILE_BREAK extended with SKEW (4-of-4 → 5-of-5)                | 2026-05-08 |
| [067](ADR-067-couche2-async-polling-migration.md)                       | Accepted | Couche-2 async polling migration (CF 100s structural fix)              | 2026-05-09 |
| [068](ADR-068-cb-nlp-prompt-redesign-content-refusal.md)                | Accepted | cb_nlp prompt redesign — Claude content refusal fix                    | 2026-05-09 |
| [069](ADR-069-nyfed-mct-collector-replaces-uig.md)                      | Accepted | NY Fed MCT collector replaces discontinued FRED UIGFULL                | 2026-05-09 |
| [070](ADR-070-cleveland-fed-nowcast-collector.md)                       | Accepted | Cleveland Fed Inflation Nowcast collector (4×3 daily surface)          | 2026-05-09 |
| [071](ADR-071-capability-5-deferral-client-tools-only.md)               | Accepted | Capability 5 — defer wiring, restrict to client tools                  | 2026-05-09 |
| [072](ADR-072-ansible-ichor-packages-role.md)                           | Accepted | Ansible ichor_packages role — sync packages-staging declaratively      | 2026-05-09 |
| [073](ADR-073-nfib-sbet-pdf-collector.md)                               | Accepted | NFIB SBET PDF collector (SBOI + Uncertainty Index)                     | 2026-05-09 |
| [074](ADR-074-myfxbook-replaces-oanda-orderbook.md)                     | Accepted | MyFXBook Community Outlook replaces discontinued OANDA orderbook       | 2026-05-09 |
| [075](ADR-075-cross-asset-matrix-v2.md)                                 | Accepted | Cross-asset matrix v2 — 6-dim macro state + per-asset bias tags        | 2026-05-09 |
| [076](ADR-076-frontend-mock-fallback-pattern.md)                        | Accepted | Frontend MOCK\_\* are graceful fallbacks — keep the pattern            | 2026-05-09 |
| [077](ADR-077-capability-5-mcp-server-wire.md)                          | Accepted | Capability 5 STEP-3 — MCP server (Win11 → apps/api tools)              | 2026-05-09 |
| [078](ADR-078-cap5-query-db-excludes-trader-notes.md)                   | Accepted | Capability 5 `query_db` allowlist excludes `trader_notes`              | 2026-05-09 |
| [079](ADR-079-eu-ai-act-50-2-watermark-middleware.md)                   | Accepted | EU AI Act §50 deployer disclosure — watermark middleware               | 2026-05-09 |
| [080](ADR-080-disclosure-surface-contract.md)                           | Accepted | Disclosure surface contract (ai-disclosure + methodology + well-known) | 2026-05-09 |
| [081](ADR-081-doctrinal-invariant-ci-guards.md)                         | Accepted | Doctrinal invariant CI guards                                          | 2026-05-09 |
| [082](ADR-082-w101-calibration-w102-cf-access-strategic-pivot.md)       | Accepted | W101 calibration scoreboard + W102 CF Access + strategic pivot         | 2026-05-11 |
| [083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md)       | Accepted | Ichor v2 trader-grade manifesto + gap-closure roadmap                  | 2026-05-11 |
| [084](ADR-084-searxng-self-hosted-web-research.md)                      | Accepted | SearXNG self-host replaces Perplexity (Couche-2 web research)          | 2026-05-11 |
| [085](ADR-085-pass-6-scenario-decompose-taxonomy.md)                    | Accepted | Pass 6 `scenario_decompose` — 7-bucket stratified taxonomy             | 2026-05-11 |
| [086](ADR-086-rag-layer-past-only-bge-small.md)                         | Accepted | RAG layer — past-only + bge-small Voie D + Cap5 exclusion              | 2026-05-12 |
| [087](ADR-087-phase-d-auto-improvement-loops.md)                        | Accepted | Phase D auto-improvement loops (4-loop + W116c + W117a)                | 2026-05-13 |
| [088](ADR-088-w115c-confluence-engine-pocket-read.md)                   | Accepted | W115c pocket-skill reader (close Phase D measure→act loop)             | 2026-05-13 |
| [089](ADR-089-spx500-spy-etf-proxy.md)                                  | Accepted | `SPX500_USD` → SPY ETF proxy (Polygon Indices 403 mitigation)          | 2026-05-13 |
| [090](ADR-090-eur-usd-data-pool-extension.md)                           | Accepted | `EUR_USD` data-pool extension (close Vovk W115 anti-skill)             | 2026-05-13 |
| [091](ADR-091-w117b-gepa-prompt-optimization.md)                        | Accepted | W117b GEPA prompt-optimization wiring (DSPy 3.2 Voie-D)                | 2026-05-13 |
| [092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md)             | Accepted | GAP-D Asian-Pacific daily-proxy upstreams (JPY + AUD)                  | 2026-05-14 |
| [093](ADR-093-aud-commodity-surface-degraded-explicit.md)               | Accepted | AUD commodity surface degraded explicit (GAP-A 5/5)                    | 2026-05-14 |
| [094](ADR-094-boj-jgb-daily-collector.md)                               | Accepted | BoJ Time-Series JGB 10Y daily collector (Tier 2 GAP-D)                 | 2026-05-14 |
| [095](ADR-095-estat-mof-fx-intervention-collector.md)                   | Accepted | e-Stat MoF FX intervention monthly collector (Tier 2 GAP-D)            | 2026-05-14 |
| [096](ADR-096-rba-f-series-rate-collector.md)                           | Accepted | RBA F-series rate collector (Tier 2 GAP-D)                             | 2026-05-14 |
| [097](ADR-097-fred-liveness-nightly-ci-guard.md)                        | Accepted | Nightly FRED-DB liveness CI guard (R53 codified)                       | 2026-05-15 |
| [098](ADR-098-coverage-gate-triple-drift-reconciliation.md)             | Proposed | Coverage gate triple-drift reconciliation (ADR-028)                    | 2026-05-15 |
| [099](ADR-099-north-star-architecture-and-staged-roadmap.md)            | Proposed | North-star architecture & staged roadmap (5-asset surface)             | 2026-05-16 |
| [100](ADR-100-briefing-secrets-provisioning-align-api-env.md)           | Accepted | `ichor-briefing@` secrets — align with `api.env` mechanism             | 2026-05-16 |
| [101](ADR-101-gbp-specific-section-rate-differential-risk-premium.md)   | Accepted | GBP-specific section — UK-US rate-diff + sterling risk-premium         | 2026-05-17 |
| [102](ADR-102-confluence-source-independence-reweight.md)               | Accepted | Confluence re-weighted by source independence                          | 2026-05-17 |
| [103](ADR-103-runtime-fred-liveness-degraded-data-explicit-surface.md)  | Accepted | Runtime FRED-liveness degraded-data explicit surface                   | 2026-05-17 |
| [104](ADR-104-degraded-inputs-persisted-on-session-card.md)             | Accepted | Degraded-inputs persisted on the session card                          | 2026-05-17 |
| [105](ADR-105-market-closed-gate-session-card-generation.md)            | Accepted | Market-closed gate for session-card generation (ADR-099 §Tier-3)       | 2026-05-17 |
| [106](ADR-106-autonomous-living-system-and-session-verdict-contract.md) | Accepted | Autonomous living system + session-verdict contract                    | 2026-05-26 |
| [107](ADR-107-eia-supply-demand-theme-driver.md)                        | Accepted | EIA supply/demand theme driver                                         | 2026-05-29 |
| [108](ADR-108-full-opus-everywhere.md)                                  | Accepted | Full Opus everywhere (supersedes the ADR-023 model split)              | 2026-06-02 |
| [109](ADR-109-streaming-cadence-verdict-refresh.md)                     | Accepted | Streaming-cadence verdict refresh                                      | 2026-06-02 |
| [110](ADR-110-engine-opus48-max-effort-xhigh.md)                        | Accepted | Engine = Opus 4.8 max effort (xhigh), Fable-5 migration cancelled      | 2026-06-11 |
| [111](ADR-111-s03-proactive-data-freshness-and-collection-depth.md)     | Accepted | S03 proactive data freshness + collection depth                        | 2026-06-11 |
| [112](ADR-112-gdelt-tone-local-finbert-scoring.md)                      | Accepted | GDELT tone repaired via local FinBERT scoring                          | 2026-06-12 |
| [113](ADR-113-ichor-reads-the-chart-technical-methodology.md)           | Accepted | Ichor reads the chart — technical methodology module (S05/Chantier E)  | 2026-06-12 |

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
