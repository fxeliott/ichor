# ICHOR — Architecture-of-record (AS-BUILT)

> **Session 02/09 deliverable — the technical socle made explicit.**
> Created 2026-06-05. This is the **canonical, current, verified map of the
> real system as it is built today** — not a target, not a plan.
>
> - **Supersedes** [`ARCHITECTURE_CIBLE.md`](ARCHITECTURE_CIBLE.md) (a _target_
>   from 2026-05-12, now partly stale — e.g. it says "Couche-2 Haiku low",
>   superseded by ADR-108 Opus low) and [`ARCHITECTURE_FINALE.md`](ARCHITECTURE_FINALE.md)
>   (the 2026-05-02 founding Voie-D decision). Keep those for archaeology;
>   read **this** for "how it actually fits together today".
> - **Strategy** lives in [`PLAN_DIRECTEUR.md`](PLAN_DIRECTEUR.md) (the 9-session
>   arc). This doc is the **structure** the plan operates on.
> - **Method**: built from a direct read of the code + two parallel read-only
>   audits (data-flow + 24h loops), 2026-06-05. Every claim is `file:line`-cited.
>   Counts marked ✓ were re-verified by tool this session; counts marked (§2.1)
>   are from PLAN_DIRECTEUR §2.1 (verified 2026-06-05, not re-run here).

---

## 0 · The one-paragraph truth

Ichor **is** already a large interconnected system — the spine
`collectors → data_pool (54 sections) → Couche-2 → 4-pass+Pass-6 brain →
session_card_audit → frontend` is real, mathematical, and runs 24h/24 on ~59
systemd timers. Two interconnections used to be open and made the product feel
like "isolated cards / 50-50"; **Session 04 closed the first**, one remains:

1. **[CLOSED — Session 04]** The apex verdict conviction is now **FUSED** from
   the synthesis evidence (confluence lean + dominant-theme presence +
   cross-asset dollar consensus) frozen on the card at generation, via
   `conviction_fusion.fuse_conviction`. The legacy bare `max()` over Pass-6
   buckets + hard 0.15 cliff is replaced by an **evidence-weighted** conviction
   with a **graded** dead-zone (0.05 hard / 0.15 soft) and an explicit French
   grounding ("conviction X % parce que A et B confirment, D s'oppose"). When
   Pass-6 is dormant it still honestly returns `neutral / 0%` (doctrine #11),
   and on legacy / pre-0055 cards (NULL snapshots) it degrades to the
   bucket-only conviction. ADR-017 held — direction stays bucket-derived.
2. **Ichor measures its own skill but does not act on it** — the Vovk/Brier/
   ADWIN loops learn weights and persist them, but `pocket_skill_reader`
   (which would feed them back into card generation) is built and **not wired**.
   → **Session 05**.

Everything below makes those two facts precise, and names the exact seams the
next sessions plug into.

---

## 1 · Topology (verified counts, 2026-06-05)

| Layer                                     | Count                                                                               | Verified                                         |
| ----------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------ |
| API routers (`apps/api/.../routers/*.py`) | **~49**                                                                             | ✓ Glob                                           |
| Services (`.../services/*.py`)            | **104**                                                                             | (§2.1)                                           |
| `data_pool.py` `_section_*` builders      | **54**                                                                              | ✓ Grep `async def _section_`                     |
| Collectors (`.../collectors/*.py`)        | **47**                                                                              | (§2.1)                                           |
| CLI runners (`.../cli/*.py`)              | **58**                                                                              | (§2.1)                                           |
| Alembic migrations / head                 | **55 / `0055`**                                                                     | ✓ Glob (`0055_session_card_synthesis_snapshots`) |
| systemd cron register scripts             | **59**                                                                              | ✓ Glob `register-cron-*.sh`                      |
| Brain passes                              | **6** (Régime→Asset→Stress→Invalidation + Pass-5 counterfactual + Pass-6 scenarios) | (§2.2)                                           |
| Couche-2 agents                           | **5** (cb_nlp, news_nlp, sentiment, positioning, macro)                             | (§2.2)                                           |
| web2 routes / `/learn` pages              | **46 / 15**                                                                         | ✓ Glob `app/**/page.tsx`                         |
| Priority asset universe                   | **6** (EUR_USD, GBP_USD, USD_CAD, XAU_USD, SPX500_USD, NAS100_USD)                  | code                                             |

Stack: Turborepo + pnpm monorepo · FastAPI/Python 3.12 (async SQLAlchemy 2 +
Alembic) · Next.js 15 / React 19 / Tailwind v4 (OKLCH design system) ·
Postgres + TimescaleDB + Redis on Hetzner · **Voie D**: every LLM call routes
through the local Win11 `claude-runner` (Max 20x, zero Anthropic SDK).

---

## 2 · The interconnected system (data-flow, AS-BUILT)

```
 [COLLECTION]  47 collectors, ~59 cron timers (Voie D, source-stamped)
   fred / polygon / cftc_tff / cboe_skew / polymarket / forex_factory /
   central_bank_speeches / rss / eia_petroleum ...
        │  async fetch → persistence.py bulk-upsert → dedicated ORM tables
        ▼
 [WORLD-MEMORY]  data_pool.py — 54 `async def _section_*` builders
        │  each returns (markdown, sources);  build_data_pool() joins them
        │  → DataPool(markdown=...) frozen dataclass        [data_pool.py:233-251]
        │  ⚠ DataPool.markdown is the ONLY thing the brain consumes
        ▼
 [COUCHE-2]  5 agents (Opus low, ADR-108)  run_couche2_agent.py
        │  write → couche2_outputs (JSONB)  [models/couche2_output.py]
        └─ read back → render_couche2_block → a _section in data_pool [data_pool.py:5351]
        ▼
 [SYNTHESIS]  theme_classifier · confluence_engine(10 factors) · dollar_coherence
        │  (see §4 — these feed the PROMPT and the persisted card, but NOT the apex verdict)
        ▼
 [BRAIN]  Orchestrator.run()  [packages/ichor_brain/.../orchestrator.py:222]
        │  Pass-1 Régime → Pass-2 Asset → Pass-3 Stress → Pass-4 Invalidation
        │  (+ Pass-5 counterfactual) → Pass-6 Scenarios (enable_scenarios=live :367)
        │  → Critic gate → SessionCard [:433]
        ▼
 [PERSISTENCE]  to_audit_row()  [persistence.py:20]
        │  conviction_pct = card.stress.revised_conviction_pct [persistence.py:37]
        │  scenarios = card.scenarios (7 buckets JSONB)        [persistence.py:62]
        │  → session_card_audit  (run_session_card.py:437-438)
        ▼
 [VERDICT]  build_session_verdict()  [session_verdict_builder.py:448]
        │  reads card.scenarios ONLY → conviction = max(buckets)*100  ← §4 THE GAP
        ▼
 [FRONTEND]  46 routes · /briefing/[asset] apex (freshness-gated) · coach-FR SSOT
```

**Real Pydantic / function contracts between stages** (the "tout communique"):
`DataPool` (frozen dataclass) → `Orchestrator.run(data_pool=markdown)`
(`run_session_card.py:101`) → `RunnerCall` → (Voie-D runner) → per-pass parsed
models → `SessionCard` → `to_audit_row` → `SessionCardAudit` ORM →
`/v1/sessions` + `/v1/verdict/session-ny/{asset}` → web2.

---

## 3 · The 24h/24 heartbeat (real-time liveness)

The "vivant 24h/24" is **59 systemd timers** on Hetzner. The load-bearing ones:

| Loop                                                | Schedule (Paris)      | Runs                                                                                                                                                                | Status                                                                               |
| --------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Briefings                                           | 06/12/17/22           | `run_briefing` (1 Claude call, feeds cards)                                                                                                                         | LIVE                                                                                 |
| **Session-cards batch**                             | 06/12/17/22           | `run_session_cards_batch --live` (6 assets × 5-pass : Régime→Asset→Stress→Invalidation + Pass-6 ; Pass-5 counterfactual is on-demand, not in the synchronous batch) | LIVE                                                                                 |
| Couche-2 (×5)                                       | staggered 00–06/4h    | `run_couche2_agent` (Opus low NLP)                                                                                                                                  | LIVE                                                                                 |
| **Streaming refresh**                               | every **12 min**      | `run_streaming_refresh` — regen ONE asset on a NEW strong event since its last card (`streaming_refresh.py:201-208`); cooldown 45 min, cap 3/fire                   | flag `streaming_refresh_enabled` (fail-closed); **live ON-state unverified in repo** |
| Auto-invalidation                                   | 6×/day 00..20         | `run_scenario_invalidation_check` — flips a Pass-6 scenario to invalidated + alert (`scenario_invalidation_monitor.py:34-90`)                                       | flag default **False → almost certainly DORMANT**                                    |
| Phase-D measure (Vovk/Brier/drift/ADWIN/reconciler) | 02:00–05:00 nightly   | persist weights to DB                                                                                                                                               | **LIVE-by-cron** (no flag gate)                                                      |
| Phase-D act (`pocket_skill_reader`)                 | —                     | would feed weights into Pass-3                                                                                                                                      | **BUILT, NOT WIRED** (§5)                                                            |
| ML (HAR-RV, HMM, VPIN) + ~35 collector/alert checks | nightly / `*:0/5..30` | macro/vol/geopol alert engine                                                                                                                                       | LIVE                                                                                 |
| Notifications                                       | event-driven          | `alerts_runner._maybe_notify` → critical-only web-push (`alerts_runner.py:161`, `push.py` VAPID/Redis)                                                              | LIVE                                                                                 |

This is genuinely a living organism on the _collection + generation + alerting_
side. The **reactive intra-session** edge (streaming refresh) exists at 12-min
cadence; the **auto-invalidation** edge is built but flag-dormant.

---

## 4 · The two convictions & the "50/50" (CLOSED — Session 04)

Historically there were **two distinct conviction numbers** that disagreed by
design; **Session 04 fused them**. For the record:

**(A) Persisted card conviction** — `session_card_audit.conviction_pct`
= `card.stress.revised_conviction_pct` (`persistence.py:37`), mathematically
touched by the synthesis: `confluence_engine.assess_confluence`
→ `card.drivers` (`run_session_card.py:416-432`) → `card_coherence.reconcile_coherence`
(`run_session_card.py:453-476`) which can **demote-only** (bias→neutral / shave
conviction) → writes `row.conviction_pct`.

**(B) Frontend apex verdict conviction** — `SessionVerdict.conviction_pct`
from `build_session_verdict()` — **was** a bare `max(bullish_mass,
bearish_mass) * 100` over the Pass-6 buckets, with a hard `spread < 0.15 →
neutral` cliff, disconnected from (A) and from every synthesis layer.
**That** was the "50/50".

**What Session 04 changed (the fix, AS-BUILT):**

- At generation, `run_session_card._capture_synthesis_snapshots` freezes three
  reads onto the card: `confluence_snapshot` (confluence_engine dominant
  direction + scores), `theme_snapshot` (theme_classifier presence —
  non-directional), `dollar_snapshot` (cross_asset_dollar_coherence consensus +
  strength). Persisted as 3 nullable JSONB columns (migration **0055**);
  NULL = "synthesis not captured at generation".
- `build_session_verdict` reads them via `_extract_synthesis_primitives(card)`
  and passes the primitives to `_derive_direction_and_conviction(...)`
  (`session_verdict_builder.py:110`), which now **delegates to**
  `conviction_fusion.fuse_conviction`.
- `conviction = base_bucket_mass × soft_zone_scale × agreement_factor`, clamped
  to 95 (ADR-022); direction stays **bucket-derived** (ADR-017 — evidence scales
  magnitude, never sign); a **graded** dead-zone (hard 0.05 / soft 0.15)
  replaces the legacy hard 0.15 cliff. The fuser emits an explicit French
  grounding (`rationale_fr`) surfaced inside `coach_explanation`.
- On NULL snapshots (legacy / pre-0055 / capture-failure) the fuser degrades to
  the bucket-only conviction with the graded dead-zone still applied — never a
  fabricated neutral (doctrine #11).
- When Pass-6 is dormant / `scenarios=[]` → honest `neutral / 0% / uncertain`
  fallback (`session_verdict_builder.py:546-565`), unchanged.

> **The Ferrari engine (the evidence) now drives the apex.**
> `cross_asset_dollar_coherence` is no longer an orphan w.r.t. the verdict — it
> feeds the apex conviction through the `dollar_snapshot` seam. The remaining
> open interconnection is the **learning loop** (§5). ADR-017 held throughout
> (bias + probability, never an order).

---

## 5 · The learning loop (measures, does not yet act)

- **Measurement loops are live-by-cron** (no flag gate): Vovk aggregator
  (`run_brier_aggregator`, → `brier_aggregator_weights`), ADWIN concept-drift
  (`run_concept_drift`, needs ≥30 scored cards), Brier optimizer/drift,
  prediction-outlier, DTW. The nightly `reconcile_outcomes` computes
  `brier_contribution`. → Ichor **records** its per-pocket skill.
- **The act-on-learning loop is OPEN**: `pocket_skill_reader` (W115c, flag
  `phase_d_w115c_confluence_enabled`, `pocket_skill_reader.py:47`) would inject
  the learned weights into Pass-3. The orchestrator **accepts** a
  `confluence_section` (`orchestrator.py:233,256-266`) **but `run_session_card.py`
  never calls `read_pocket` nor passes it** (grep = 0). → **Dormant regardless
  of the flag.**
- W116c LLM addendum generator: flag default False → dormant.

> **Session 05 = close the loop**: wire `pocket_skill_reader` → Pass-3 (or the
> §4 conviction fusion) so the measured weights actually change the next card.
> Then Ichor _learns_ instead of just _logging_.

---

## 6 · Dormant / orphan / unverified (honest gaps register)

| Item                            | State                                              | Evidence                                                                                      |
| ------------------------------- | -------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Apex verdict ↔ synthesis        | **WIRED (S04, mig 0055)**                          | `session_verdict_builder._extract_synthesis_primitives` → `conviction_fusion.fuse_conviction` |
| `pocket_skill_reader` → cards   | **built, not wired**                               | `run_session_card.py` (0 `read_pocket`/`confluence_section`)                                  |
| `cross_asset_dollar_coherence`  | **WIRED to verdict (S04)**                         | `run_session_card._capture_synthesis_snapshots` → `dollar_snapshot` → verdict fuser           |
| scenario-invalidation monitor   | **flag default False (dormant)**                   | `run_scenario_invalidation_check.py:91-100`                                                   |
| W116c LLM addendum              | **flag default False (dormant)**                   | `run_addendum_generator.py:10`                                                                |
| streaming-refresh live ON-state | **unverified in repo**                             | flag `streaming_refresh_enabled` fail-closed; live DB row not inspectable from repo           |
| Live pipeline freshness (today) | **unverified this session**                        | harness sandbox blocks network probes; only verifiable on the host / via the S02 watchdog     |
| Critic                          | **source-traceability only**, not factual-accuracy | PLAN_DIRECTEUR §2.2                                                                           |

---

## 7 · Persistence / memory layer (alembic head `0055`)

- `session_card_audit` — per-card 6-pass output + `scenarios`/`key_levels`/
  `drivers`/`brier_contribution`/`realized_*` (mig. 0026/0039/0045/0049/0050)
  - S04 synthesis snapshots `confluence_snapshot`/`theme_snapshot`/
    `dollar_snapshot` (mig. 0055, nullable — NULL = not captured at generation).
- `couche2_outputs` (0009) — the 5 Couche-2 agents' NLP JSON.
- `auto_improvement_log` (0042, immutable trigger) — Phase-D loop audit.
- `brier_aggregator_weights` (0043) — Vovk per-(asset,regime) expert weights.
- `pass3_addenda` (0044), `gepa_candidate_prompts` (0047), `feature_flags`
  (0018), `rag_chunks_index` (pgvector, 0040/0041 — historical analogues).
- Long-term memory = the RAG index (bge-small, nightly `embed_session_cards`
  03:00) — past macro states retrieved into Pass-1.

---

## 8 · The Voie-D engine & reliability substrate (Session 02)

All "Opus 4.8 in local, full performance" analysis routes through the Win11
`claude-runner` (`apps/claude-runner`): FastAPI wrapper around `claude -p`,
single slot (`max_concurrent_subprocess=1`, Max-20x single-user), async-polling
to dodge the Cloudflare 100s edge cap. The brain (`HttpRunnerClient`) and
Couche-2 (`call_agent_task_async`) are its two consumers.

**S02 hardening (commit `0eaf272`)** made this substrate **honest**: the runner
now fails loud on an empty/error envelope instead of reporting `success` with
no content; the brain client classifies runner failures (timeout / subprocess\_
error) instead of silently yielding `""`; the timeout hierarchy is ordered
(ADR-110: runner 900 < polls 960 < systemd walls 1200/3600/5400); a Win11 self-heal watchdog
(`scripts/windows/runner-watchdog.ps1`) restarts the runner / evicts a port
squatter. See [`SESSION_LOG_2026-06-05-session02-reliable-substrate.md`] +
[`RUNBOOK-014`](runbooks/RUNBOOK-014-claude-runner-win11-down.md).

---

## 9 · Anchor points for Sessions 03→08 (the seams)

The socle is "ready to receive the next engines" at these **exact** extension
points — each future session plugs into a named contract, not a rewrite:

| Session                                     | Plugs into (file / seam)                                                                                                                                                          | Contract to honour                                                                                                                             |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **03 Freshness & coherence**                | every web2 route + `SessionVerdict.expires_at_utc` / `last_updated_utc` (`session_verdict_builder.py:106,535`)                                                                    | never render stale-as-fresh; freshness gate on all surfaces                                                                                    |
| **04 Conviction fusion** ✅ DONE            | `session_verdict_builder._derive_direction_and_conviction` → `conviction_fusion.fuse_conviction` ; snapshots frozen by `run_session_card._capture_synthesis_snapshots` (mig 0055) | ✅ confluence+theme+dollar fused into the apex conviction; graded dead-zone (0.05/0.15) replaces the 0.15 cliff; ADR-017 (bias+prob only) held |
| **05 Close the learning loop**              | `pocket_skill_reader.read_pocket` → `orchestrator.run(confluence_section=...)` (`orchestrator.py:233,256-266`); flag `phase_d_w115c_confluence_enabled`                           | feed `brier_aggregator_weights` back into generation; flag fail-closed                                                                         |
| **06 Deeper coverage / 8-driver synthesis** | new `_section_*` in `data_pool.py` + `theme_classifier` drivers (`price_action_flow`, `fiscal_policy` baseline)                                                                   | source-stamp every numeric; Critic-verifiable                                                                                                  |
| **07 The "alive" strides**                  | `streaming_refresh.py` (12-min reactive) + `scenario_invalidation_monitor` (flag ON) + a new conviction-decay seam on `SessionVerdict`                                            | event-triggered targeted regen; ADR-106 Strides 2/5/6                                                                                          |
| **08 Pedagogy elevation**                   | web2 `/briefing/[asset]` + the 15 `/learn` pages + coach-FR SSOTs (`coachLabels.ts`, `fredLabels.ts`, `sessionVerdict.ts`)                                                        | explicit beginner coach; never touch the premium structure                                                                                     |

`/learn` (15 pages) is the pedagogy substrate; `coachLabels`/`fredLabels`/
`sessionVerdict` SSOTs are the FR-coach contract every new label must route
through.

---

## 10 · Invariants (every session, CI-guarded)

- **ADR-017** — never BUY/SELL (bias + probability only). `test_invariants_ichor.py`.
- **Voie D (ADR-009/108)** — zero `import anthropic`; all LLM via the Win11 runner.
- **Cap-95** conviction (ADR-022); **Couche-2 = Opus low** (ADR-108).
- **Source-stamping** — every numeric claim traceable (Critic).
- Watermark single-source-of-truth, pure-data routes excluded (ADR-079/080);
  feature flags fail-closed; audit logs immutable (ADR-029/077).

---

## References

- [`PLAN_DIRECTEUR.md`](PLAN_DIRECTEUR.md) — 9-session strategic arc (the _what/when_).
- [`ARCHITECTURE_CIBLE.md`](ARCHITECTURE_CIBLE.md) — **superseded** target (2026-05-12).
- [`ARCHITECTURE_FINALE.md`](ARCHITECTURE_FINALE.md) — founding Voie-D decision (2026-05-02).
- ADR-017 / ADR-106 (SessionVerdict + autonomy) / ADR-108 (Opus everywhere) /
  ADR-109 (streaming cadence) / ADR-087 (Phase-D loops).
