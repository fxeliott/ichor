# ADR-106 — Autonomous living-system architecture & SessionVerdict contract

**Status** : Accepted (r161)
**Date** : 2026-05-26
**Supersedes** : none
**Superseded by** : none
**Cross-refs** : ADR-017 (no BUY/SELL boundary), ADR-022 (cap-95 conviction), ADR-085 (Pass-6 scenario_decompose), ADR-099 (north-star roadmap), ADR-104 (degraded-inputs persistence), ADR-105 (market-closed gate)

---

## Context — Eliot's r161 directive (verbatim core)

Eliot crystallised the system's finality in two paragraphs of the r161 directive that supersede every prior ambiguity about Ichor's ultimate output shape :

> **Mon style de trading.** Mon objectif est de profiter du volume de la session de New York pour capter le mouvement — haussier ou baissier — à l'open ou en pré-session. Je prends position entre 14h et 16h, et je coupe tout à 20h. C'est ma fenêtre, c'est mon mode opératoire.

> **Le verdict attendu.** Le but d'Ichor est donc, par son analyse, de me délivrer un verdict exact — le plus parfait possible, le plus anticipateur possible, le plus en direct possible, le plus autonome et automatique possible. Concrètement, Ichor doit me dire, sur 100 %, dans quel sens va aller la session et avec quelle conviction : par exemple « hausse sur la session à 85 %, de façon structurée » ou « en momentum », etc. — avec un pourcentage de conviction clair et la nature précise du mouvement attendu.

> **L'écosystème vivant.** Ichor doit être un système ultra autonome, interconnecté au monde et à tout, en permanence, 24h/24. Les analyses ne doivent JAMAIS être statiques — elles doivent être continues, vivantes, en mouvement perpétuel, avec les invalidations et les déclencheurs de scénarios intégrés automatiquement au fil du temps réel.

Until r161, Ichor produced **session-cards** (Pass-1..6 emissions persisted to `session_card_audit`) and pre-event briefings (`<EventAnticipationPanel>`) that aggregated to ~13 components per `/briefing/[asset]` page — a rich but **passive** read. The trader had to **synthesise the 7 buckets + the event-anticipation drivers + the conviction grounding + the recent-actuals + the polymarket overlay + the cross-asset matrix into a single mental verdict for the 14h-20h window**. That synthesis work is exactly what Eliot's r161 directive offloads onto Ichor itself.

ADR-106 is the architectural locus where the system commits to delivering **one canonical verdict per (asset, NY session day)** with a precise shape, refreshed in real-time as triggers fire and scenarios invalidate.

---

## Decision

### D1 — `SessionVerdict` contract (the final-output shape)

A new Pydantic model `SessionVerdict` (canonical home : `packages/ichor_brain/src/ichor_brain/session_verdict.py`) carries the trader-facing verdict for one (asset, NY session day) tuple. Its fields are the **minimum sufficient set** to answer Eliot's verbatim spec :

| Field                          | Type                                | Meaning                                                                                                                               |
| ------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `asset`                        | `PriorityAsset` Literal             | One of the 5 frontend-shipped assets (EUR_USD, GBP_USD, XAU_USD, SPX500_USD, NAS100_USD)                                              |
| `session_window`               | Literal `"ny_14h_to_20h_paris"`     | Eliot's canonical window stamp (prend position 14h-16h, coupe tout 20h Paris)                                                         |
| `direction`                    | `VerdictDirection` Literal          | `up`, `down`, or `neutral` (neutral is a **legitimate** doctrine #11 calibrated-honesty output)                                       |
| `conviction_pct`               | float `[0, CAP_95*100]`             | 0..95 percent. Cap-95 per ADR-022, tracked through `CAP_95` constant from `scenarios.py`                                              |
| `nature`                       | `VerdictNature` Literal             | `structured`, `momentum`, `range_bound`, or `uncertain`                                                                               |
| `derived_from_scenarios`       | bool                                | True if aggregated from Pass-6 emission ; False = downgraded fallback (`conviction_pct` capped at 50, `nature` forced to `uncertain`) |
| `scenario_decomposition_id`    | str \| None                         | UUID pointer to source `session_card_audit.scenarios` row for drill-down                                                              |
| `invalidation_state`           | `ScenarioInvalidationState` \| None | Hard/soft/note invalidation buckets at refresh time (r161 Strand A `Scenario.invalidations`-driven)                                   |
| `live_triggers`                | list[`LiveTrigger`] (≤10)           | Real-time events that fired since emission, ordered most-recent-first                                                                 |
| `coach_explanation`            | str (80..800 chars)                 | Plain-French beginner-friendly WHY explanation. ADR-017 regex-checked                                                                 |
| `ne_pas_actionner_avant_paris` | datetime                            | Typically 14h00 Paris (window start)                                                                                                  |
| `couper_au_plus_tard_paris`    | datetime                            | Typically 20h00 Paris (window close)                                                                                                  |
| `last_updated_utc`             | datetime                            | Wall-clock of last verdict refresh                                                                                                    |
| `expires_at_utc`               | datetime                            | Verdict stale-after timestamp ; UI banner switches to "verdict expiré" past this                                                      |

ADR-017 boundary applied via `_FORBIDDEN_VERDICT_TOKENS_RE` mirror regex on `coach_explanation` + every `LiveTrigger.description`. Cap-95 enforced via Pydantic `Field(le=CAP_95 * 100.0)` — if `CAP_95` ever changes in `scenarios.py`, the verdict cap follows automatically.

### D2 — Derivation from 7-bucket `ScenarioDecomposition`

The verdict is **DERIVED**, never independently generated. The aggregation rule :

```
bullish_mass  = mild_bull.p + strong_bull.p + melt_up.p
bearish_mass  = mild_bear.p + strong_bear.p + crash_flush.p
neutral_mass  = base.p

direction =
  "up"      if  bullish_mass - bearish_mass >= 0.15
  "down"    if  bearish_mass - bullish_mass >= 0.15
  "neutral" otherwise   # doctrine #11 calibrated honesty

conviction_pct = max(bullish_mass, bearish_mass) * 100  # capped at CAP_95*100

tail_mass = melt_up.p + crash_flush.p
mid_mass  = mild_bull.p + mild_bear.p

nature =
  "momentum"     if  tail_mass / (tail_mass + mid_mass + 1e-9) >= 0.55
  "structured"   if  mid_mass / (tail_mass + mid_mass + 1e-9) >= 0.55
  "range_bound"  if  neutral_mass >= 0.45
  "uncertain"    otherwise
```

The 0.15 directional threshold + 0.55 nature threshold + 0.45 range threshold are intentional **dead-zones** that prevent oscillation noise. They are not free parameters : they are anchored to ADR-022 cap-95 (no individual bucket can cross 0.95, so 0.15 spread = a meaningful asymmetry, not a coin-flip) and ADR-085 §"The 7 buckets" stratification (`base` carries the median ~30% in calibration, so 0.45 = `base` dominates).

These thresholds are intentionally **not configurable** at r161 — they will be calibrated empirically against realized session outcomes in r162+ via the Phase D Brier feedback loop (ADR-087 W116 PBS).

### D3 — Live invalidation + trigger refresh cycle

Once a `SessionVerdict` is emitted (pre-NY, ~13h00 Paris), it refreshes on three events :

1. **`scenario_invalidation_monitor` poll fires** (r161 Strand D, cadence 6×/jour Paris : 00, 04, 08, 12, 16, 20). The monitor polls each `Scenario.invalidations[*]` condition against current data ; when a `hard` invalidation breaches, the offending bucket's `p` is set to 0 and `cap_and_normalize` re-distributes mass. The verdict re-derives, `last_updated_utc` bumps.

2. **LIVE trigger fires** (r161 Strands E-F, real-time via existing `alerts_runner.check_metric()` quadruplet pattern). News-headline / economic-release / polymarket-shift triggers append to `verdict.live_triggers` with an `impact` field. Conviction shifts proportionally to impact intensity.

3. **Pass-6 re-emission** (any 4-pass orchestrator cycle that re-emits scenarios). New `scenario_decomposition_id`, verdict re-derived from scratch.

The verdict's `last_updated_utc` is the **freshness clock** the frontend reads to render "updated 2 min ago" labels. Past `expires_at_utc` (typically `couper_au_plus_tard_paris` + 15 min buffer = 20h15 Paris), the frontend banner switches to "verdict expiré, attente nouvelle session" and the endpoint returns HTTP 410 Gone.

### D4 — Frontend surface (r161 Strand G + r162 Stride 7 carry-forward)

The verdict surfaces in the frontend via a new `<SessionVerdictPanel>` component rendered prominently at the TOP of `/briefing/[asset]`, above the existing `<EventAnticipationPanel>` (r152). The panel shows :

```
EUR/USD — Session NY mardi 26 mai 2026

  ▲ HAUSSE        conviction 73%        structurée
  fenêtre : 14h00 → 20h00 Paris (coupe tout 20h00)

  Pourquoi : (coach_explanation 80-800 chars FR débutant)

  Déclencheurs live (3) :
    • 14:00 — CB Consumer Confidence sortie 95.2 vs 91.9 attendu (confirme)
    • 14:30 — Polymarket Fed cuts 2026 passé 66% → 58% (test)
    • 15:15 — Bund 10Y break 3.20% (confirme)

  Scenarios invalidés :
    🛑 crash_flush invalidé (hard) : VIX < 16 vs seuil 25
    ⚠️ strong_bear partiellement invalidé (soft) : DXY break 99.5
```

No "méthodologie" sub-section — the panel is **self-explanatory** by virtue of how the data is structured + the `coach_explanation` paragraph. Eliot's r161 directive verbatim : _"je ne veux pas de section méthodologie ni de bloc explicatif ajouté à part. Cette clarté doit passer directement par la manière de structurer l'information"_.

Initial implementation polls `GET /v1/verdict/session-ny/{asset}` every 30 s while tab is visible (Page Visibility API ; pause on hidden). r162+ Stride 7 upgrades this to WebSocket/SSE push so the verdict refresh is instantaneous on trigger fire instead of 30 s polling latency.

### D5 — Endpoint contract

```
GET /v1/verdict/session-ny/{asset}

  Path params :
    asset : PriorityAsset (EUR_USD | GBP_USD | XAU_USD | SPX500_USD | NAS100_USD)

  Query params (optional) :
    since : ISO-8601 datetime — return 304 Not Modified if last_updated_utc <= since
    explain : bool — if false, omit coach_explanation field (slim response for mobile)

  Responses :
    200 OK         → SessionVerdict JSON
    304 Not Modified → since param matched freshness clock
    404 Not Found  → no verdict emitted yet for this (asset, today)
    410 Gone       → verdict past expires_at_utc, await new session
    422 Unprocessable Entity → asset path param not in PriorityAsset whitelist

  Cache-Control : private, no-store (verdict is LIVE state, never cache at intermediate proxy)
  X-Ichor-AI-Generated : true (ADR-079 §50.2 watermark middleware)
```

### D6 — Doctrine alignment summary

| Doctrine                            | Compliance                                                                                                                                                        |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ADR-017 (no BUY/SELL)               | `coach_explanation` + `LiveTrigger.description` regex-checked ; verdict is directional bias + nature, never order                                                 |
| ADR-022 (cap-95)                    | `conviction_pct` capped at `CAP_95 * 100.0` via Pydantic Field constraint, traced through scenarios.py constant                                                   |
| ADR-023 (Couche-2 Haiku low)        | No new Couche-2 agent ; verdict derives from existing Pass-6 (Sonnet medium via Voie D claude-runner)                                                             |
| ADR-085 (Pass-6 7 buckets)          | Verdict aggregates the canonical 7 buckets ; no new bucket, no override                                                                                           |
| Voie D (zero Anthropic SDK)         | Verdict is a pure aggregation layer over existing Pass-6 emission ; no LLM call of its own                                                                        |
| Doctrine #2 strict scope            | r161 Strand A (Scenario.invalidations) + Strand H (this ADR + SessionVerdict schema) ship ; Strands C-G land in subsequent commits                                |
| Doctrine #4 SSOT                    | `BUCKET_LABELS` + `CAP_95` + `INVALIDATION_METRIC_NAMES` re-used verbatim, no duplication                                                                         |
| Doctrine #11 calibrated honesty     | `direction="neutral"` + `conviction_pct=0` + `nature="uncertain"` are legitimate outputs ; system refuses to fabricate a verdict to fill the void                 |
| Doctrine #17 negative-result-anchor | The "verdict downgrade" mechanism (when Pass-6 fails or invalidations cascade) mirrors the Pattern #17 honesty pattern — ship a degraded read rather than no read |

---

## The 7-stride roadmap to the living system

ADR-106 codifies a **7-stride architecture** to evolve Ichor from its r161 baseline (static daily briefings) to the fully autonomous living system Eliot demands. Each stride is shippable atomically (doctrine #2 strict scope), and they compose into the auto-invalidating ecosystem.

| Stride | Title                                                                                                                                                                                   | Status                                                                                               | Effort           |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------- |
| **1**  | **Scenario Invalidation Engine** : `Scenario.invalidations` field + monitor + alerts integration + frontend chip                                                                        | A shipped r161 `8c94d4b`, H shipped r161 (this ADR + SessionVerdict), C-G in r161/r162 carry-forward | M (5-7 sessions) |
| 2      | **Real-time news feed 5min** : Reuters / Bloomberg / Mastodon-Truth-Social / X institutional list polled every 5-10 min with relevance scoring per asset                                | not started                                                                                          | L (3-4 sessions) |
| 3      | **News-driven re-analysis trigger** : when a breaking news fires high-relevance, immediate partial 4-pass re-run on affected asset                                                      | depends on Stride 2                                                                                  | M (2-3 sessions) |
| 4      | **Post-event auto re-analysis** : when a HIGH-impact event passes (e.g., FOMC delivery), immediate post-event session_card re-emission with actual data + scenario invalidation re-eval | depends on Stride 1 + actuals reconciler (r144 ALFRED carry-forward)                                 | M (2-3 sessions) |
| 5      | **Conviction decay function** : each scenario has a half-life ; conviction auto-degrades without refresh, recovers on confirming data                                                   | depends on Stride 1                                                                                  | S (1-2 sessions) |
| 6      | **Cross-asset cascading** : DXY tick 0.3% → re-eval 5 assets simultaneously via `cross_asset_matrix` (r79 already exists as static section ; Stride 6 makes it event-driven)            | depends on Stride 1 + Stride 2                                                                       | M (2-3 sessions) |
| 7      | **WebSocket/SSE push frontend** : replace 30s polling with server-push when verdict refreshes ; latency from refresh-to-render goes from ~15s avg to <500ms                             | independent                                                                                          | M (2-3 sessions) |

**Total estimated effort** : 17-25 sessions (~6-9 months at the current ~3 sessions/week cadence). Each stride is independent and atomically shippable ; the order is informed by dependency chains, not by Eliot's priority (he can re-order).

**Critical observation for future continues** : Stride 1 is the foundational stride that unlocks Strides 4, 5, and 6 (all depend on `Scenario.invalidations` being populated by Pass-6 + monitored by the daemon). Therefore Stride 1 completion (Strands C-G) is the highest-leverage next move.

---

## Consequences

### Positive

- **Eliot's verdict directive verbatim materialised** : the `SessionVerdict` schema gives the system a precise output target instead of an open-ended "produce analyses" goal
- **Doctrine #4 SSOT extended** : `INVALIDATION_METRIC_NAMES` + `BUCKET_LABELS` + `CAP_95` + new `PriorityAsset` literal are all single-source-of-truth across `ichor_brain` and `ichor_api`
- **Phase D auto-learning unblocked** : the Brier feedback loop (ADR-087 W116) can now score the **verdict** (a single direction + nature decision per session) instead of having to score 7 separate bucket probabilities ; sample size grows ~7x for the same calendar window
- **Frontend surface clarified** : the trader gets ONE prominent verdict panel instead of having to synthesise 13 panels into a mental verdict
- **Zero behaviour change at r161 commit time** : the verdict schema ships but the verdict aggregator service + endpoint + frontend panel are r161 carry-forward — same architecture-first scoping discipline that r160 Dukascopy MVP followed

### Negative

- **r161 ships incomplete** : Strands C-G of Stride 1 are not in this commit. The verdict schema is dormant until the aggregator + endpoint + panel land. Mitigation : Strand A + this ADR + SessionVerdict schema are the FOUNDATION ; same r160-FOUNDATION pattern that worked for the Dukascopy migration 0053.
- **Verdict thresholds are not yet empirically calibrated** : the 0.15 / 0.55 / 0.45 thresholds in D2 are anchored to ADR-022 + ADR-085 priors, not to realized session outcomes. r162+ calibration via Phase D Brier feedback will refine them.
- **Pass-6 still gated `enable_scenarios=False`** (per the researcher audit on commit `8c94d4b`). The verdict cannot derive from scenarios until that flag flips. Mitigation : `derived_from_scenarios=False` fallback path is built into the schema — verdict still emits (capped at conviction 50, nature=uncertain) when Pass-6 is gated off.

### Risks tracked

- **Pattern #15 R59 risk on Stride 2 (real-time news feed)** : Reuters / Bloomberg paid, Truth-Social rate-limited, X institutional list scraping ToU-fragile. Same risk class as Dukascopy r161 R59 RED + FXStreet/Investing.com forecast-range R59 RED. Mitigation : Stride 2 will be preceded by a dedicated R59 Phase 0 verification round (per the now-stable Pattern #15 discipline, 10 applications).
- **WebSocket/SSE infrastructure debt** : Stride 7 requires either Cloudflare Tunnel SSE support (verified compatible per [Cloudflare docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/tunnel-with-firewall/)) or a websocket gateway. The Hetzner deploy currently uses a tunnel that supports SSE natively, so no infrastructure change is needed for r162+ Stride 7.

---

## Implementation (r161)

**Committed** :

- `8c94d4b` — Strand A : `Scenario.invalidations: list[InvalidationCondition] = Field(default_factory=list, max_length=5)` + `InvalidationCondition` Pydantic class + `INVALIDATION_METRIC_NAMES` frozenset (33 canonical metric names) + ADR-017 boundary mirror regex on `description`
- this commit — Strand H : `SessionVerdict` Pydantic class + `LiveTrigger` + `ScenarioInvalidationState` + ADR-017 boundary regex on `coach_explanation` + cap-95 traced through `CAP_95 * 100.0` constant + apps/api re-export ; this ADR-106

**Carry-forward (r161 continues or r162)** :

- Strand C : Pass-6 system prompt update (`packages/ichor_brain/src/ichor_brain/passes/scenarios.py:39-122`) to generate `invalidations` per scenario
- Strand D : NEW `apps/api/src/ichor_api/services/scenario_invalidation_monitor.py` polling each invalidation condition against current data, persisting to `Alert` ORM via `alerts_runner.check_metric()`
- Strand E : alerts catalog entries for the 33 metric names + their evaluator functions in `alerts/evaluator.py`
- Strand F : NEW `cli/run_scenario_invalidation_check.py` + `register-cron-scenario-invalidation-check.sh` (6×/jour Paris)
- Strand G : NEW `services/session_verdict_builder.py` (the aggregator) + NEW router `apps/api/src/ichor_api/routers/verdict.py` (the `GET /v1/verdict/session-ny/{asset}` endpoint) + NEW frontend `<SessionVerdictPanel>` component

**Build gate (LOCAL MEASURED, this commit)** :

- `pytest tests/test_invariants_ichor.py tests/test_scenarios.py` → 80/80 pass (Pass-6 invariants + ADR-017 source-inspection + Brier 12-factor lockstep all preserved)
- 5/5 SessionVerdict smoke tests pass (minimal verdict + invalidation_state + 2 triggers + ADR-017 boundary + cap-95 + priority-5 whitelist)

**Reviewer concordance** : DEFERRED to r161+ continues per doctrine #17 (FOUNDATION-only ship, no production behaviour change ; full concordance when Strands C-G land and the verdict surface goes live in prod).

---

## Self-review

- ADR-017 boundary CI-guarded by `test_invariants_ichor.py` extension r161+ : pending — defensive `_FORBIDDEN_VERDICT_TOKENS_RE` regex enforces at construction time, CI source-inspection regex extension in next continue
- Pattern #15 R59 applied : YES — Agent researcher GREEN verdict on `8c94d4b` confirmed `session_card_audit.scenarios` JSONB free-form absorbs new shape without migration
- Pattern #13 citation-identity : not applicable (no academic citation in this ADR ; the 0.15/0.55/0.45 thresholds are doctrinally derived from ADR-022/085, not from a paper)
- Voie D : preserved (zero Anthropic SDK consumption ; verdict derives from existing Pass-6 emission)
- Doctrine #2 strict scope : RESPECTED — only Strand A (committed `8c94d4b`) + Strand H (this commit) ship at r161 ; Strands C-G carry-forward

**End ADR-106.**
