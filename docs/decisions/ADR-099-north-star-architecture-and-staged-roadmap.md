# ADR-099: North-star architecture & staged roadmap (5-asset pre-session intelligence system)

- **Status**: Proposed (round-72, 2026-05-16) — governing/organizing ADR. Authored from a 10-subagent exhaustive audit + recon wave under Eliot's explicit consolidated vision prompt (2026-05-16). Tier-0/Tier-1/Tier-3 execution proceeds under the standing "continue" autonomy mandate; the one doctrinal narrowing that needs explicit Eliot ratification (5-asset **surface** formalization, amending ADR-083 D1) is called out below.
- **Date**: 2026-05-16
- **Decider**: Claude r72 (proposal, audit-grounded) ; Eliot (vision mandate ; path ratify on universe narrowing)
- **Amends**: [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) §D1 (6-asset universe → 5-asset **briefing surface**, USD/CAD retained backend-side, not surfaced)
- **Supersedes**: none (organizing layer above existing ADRs ; no Accepted ADR is invalidated)

---

## Context

### The vision (Eliot, verbatim-grounded 2026-05-16)

Ichor must deliver, **every day in London & NY pre-session (Paris time)**, on a web app
that is "ultra design, ultra structured, ultra intuitive", a fully-explained pre-trade
intelligence briefing covering **exactly 5 assets** — **EUR/USD, GBP/USD, XAU/USD,
S&P 500, Nasdaq** — across **everything except technical analysis** (Eliot does TA
himself on TradingView):

1. Analyse fondamentale 2. Macro 3. Géopolitique 4. Corrélations 5. Volume
2. Sentiment marché 7. Ce que font les acteurs du marché (positioning)
3. Le point de vue raisonné de Claude

Plus: all scenarios & events, news, economic calendar, **and holiday/weekend
awareness to adapt the session accordingly**. Analyses run **full Claude local
(Voie D — no Anthropic API)**. The product must **self-update autonomously,
permanently**. Boundary unchanged: **never BUY/SELL** (ADR-017, contractual) —
directional lean + probability % + what can move it + key levels + risk posture +
structured-vs-momentum character only.

### Ground truth (10-subagent audit, 2026-05-16, empirically verified)

| Dimension                | Verified reality                                                                                                                                                                                                                  | Source                                           |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| Real working branch      | `claude/friendly-fermi-2fff71` @ `17d225a` (r71), **35 commits ahead origin/main, NO PR**                                                                                                                                         | `[git rev-list]` `[gh pr list]`                  |
| Prod Hetzner             | LIVE & healthy: alembic head **0049**, **98** `ichor-*` timers firing, `ichor-api` active, session-cards generated 2026-05-16 06:26, FRED fresh                                                                                   | `[ssh psql]` `[systemctl]`                       |
| Deploy method            | `/opt/ichor` is **not a git repo** — backend is **scp-deployed**, not git-pull. Merging a PR ≠ deploying                                                                                                                          | `[ssh git]`                                      |
| **Frontend `/briefing`** | **NOT deployed anywhere.** `ichor-web` serves the **legacy `@ichor/web`** app (frozen 2026-05-04) on port 3030 via a free quick tunnel `demonstrates-plc-ordering-attractive.trycloudflare.com`. `/briefing` → **404 everywhere** | `[ssh systemctl cat ichor-web]` `[curl]`         |
| 5-asset surface          | `apps/web2/components/briefing/assets.ts:22-26` = exactly `EUR_USD, GBP_USD, XAU_USD, SPX500_USD, NAS100_USD` — **matches the refined vision**. USD/CAD deliberately backend-only (`assets.ts:11-12`)                             | `[file:line]`                                    |
| Volume data              | **Already serveable**: `/v1/market/intraday/{asset}` returns OHLCV incl. `volume`; `polygon_intraday` table LIVE (140 931 rows, ~1-min refresh). Zero backend work for the volume layer                                           | `[ssh psql]` `[market.py:87,120]`                |
| Voie D                   | Confirmed: zero `import anthropic` in prod; routes via `HttpRunnerClient` → CF tunnel → Win11 `claude -p`                                                                                                                         | `[orchestrator.py:168]` `[runner_client.py:232]` |

### Coverage of the 8 layers on the shipped `/briefing` (verified)

| #   | Layer            | Backend exists?                   | On `/briefing`?                 | Verdict     |
| --- | ---------------- | --------------------------------- | ------------------------------- | ----------- |
| 1   | Fondamentale     | yes (`_section_*_specific`)       | NarrativeBlocks Pass-2          | **COVERED** |
| 2   | Macro            | yes (`_section_macro_trinity`)    | cockpit macro tiles             | **COVERED** |
| 3   | **Géopolitique** | yes (`_section_geopolitics:3772`) | **no panel**                    | **ABSENT**  |
| 4   | Corrélations     | yes (`_section_correlations`)     | CorrelationsStrip, conditional  | **PARTIAL** |
| 5   | **Volume**       | yes (`/v1/market/intraday`)       | **no panel**                    | **ABSENT**  |
| 6   | Sentiment        | yes (`_section_aaii`)             | news-tone proxy only            | **PARTIAL** |
| 7   | Positioning      | yes (TFF/COT/MyFXBook)            | retail-only; **SPX/NAS dark**   | **PARTIAL** |
| 8   | Claude's view    | yes                               | NarrativeBlocks + VerdictBanner | **COVERED** |

Events / Pass-6 scenarios / news / calendar = COVERED. **Holiday/weekend = NOT
handled** (backend timers fire 365 d/yr; frontend `SessionStatus.tsx` is a crude
DST-naive UTC heuristic with zero holiday calendar) — an explicit unmet requirement.

### Synthesis-quality & robustness findings (world-class trading + autonomy review)

- `lib/verdict.ts` **never reads `correlations_snapshot`** → 5 verdicts presented as
  independent are really ~2.5 bets (SPX≈NAS ~0.9, EUR/GBP co-move). No net-exposure lens.
- Confluence = unweighted 2–3 vote tally → correlated-evidence overconfidence; `scenarioSkew`
  not independent of `biasSign`; `tightestInvalidation` is actually `invalidations[0]`.
- ADWIN drift (W114) + Vovk pocket-skill (W115) are LIVE but **never surfaced** to the user.
- **`_section_gbp_specific` does not exist** — the #2 asset is structurally the thinnest.
- **ADR-097 FRED-liveness CI is NON-FUNCTIONAL**: workflow references
  `scripts/ci/fred_liveness_check.py` which **does not exist** in the worktree
  (ADR-097:3 "code shipped" is inaccurate — empirically refuted). Dead-series guard does not run.
  **[r92 CORRECTION — this r72-epoch audit finding is STALE at HEAD: the script + workflow were
  actually shipped r61 and have existed since (the r72 audit checked a state ~56 commits old).
  They were however non-functional via 2 latent defects ; r92 fixed both (registry extracted to
  the dep-free `services/fred_age_registry.py` ; workflow `pip install httpx structlog` +
  secret-gate). The guard is now genuinely functional — see ADR-097 §Amendment (r92).]**
- Silent-skip chain (`fred.py:95` + `data_pool` `return "",[]` + `run_session_card.py:316`
  broad except) degrades the briefing with no human-visible alert.
- Couche-2 CLI docstring describes Cerebras→Groq primary — a description-vs-doctrine
  divergence vs ADR-023 "Claude Haiku low" / Eliot's "full Claude only" (needs deep trace).

### Stale doctrine to correct (anti-hallucination)

- CLAUDE.md/pickup say alembic **0048** → real head is **0049**.
- CLAUDE.md topology counts stale: real **40 routers / 47 collectors / ~80 services /
  60+ data_pool sections** (vs 35/44/66/42 claimed).
- `SESSION_LOG_2026-05-15/16` claimed "in git, verified" → **not in git**.
- "4-pass + Pass 5 counterfactual" conflates inline (Pass 1-4 + optional Pass-6 + Critic)
  vs the separate weekly counterfactual batch.

## Decision

### D-1 — Five-asset briefing surface, formalized (amends ADR-083 §D1)

The **briefing surface** (`/briefing`, cockpit, verdict synthesis) is **exactly 5
assets**: `EUR_USD, GBP_USD, XAU_USD, SPX500_USD, NAS100_USD`. USD/CAD is **retained
backend-side** (pipeline, correlations, calibration) as a deprioritized,
non-surfaced asset — **not ripped out** (removal = regression/churn for zero user
value; keeping it is free and reversible). JPY/AUD remain deprioritized backend-side.
This amends ADR-083 §D1's "6-asset universe" to "6 backend / **5 surfaced**".
_This is the one item requiring explicit Eliot ratification before it is Accepted._

### D-2 — The global system contract (the "north star")

Ichor is **one autonomous daily pre-session intelligence system**, defined by an
explicit **coverage contract**: for each of the 5 assets, each of the 8 layers is
either **COVERED** (surfaced with real data + uncertainty) or **explicitly DEGRADED**
(ADR-093 "degraded explicit" pattern — never silently absent). Holiday/weekend
state is a **first-class backend signal**, not a frontend heuristic. The product is
judged "marche exactement" only when the coverage contract is satisfied for a real
pre-session, end-to-end, on a URL Eliot can open.

### D-3 — Staged roadmap (no accumulation, no regression, one coherent increment per round)

Work continues on `claude/friendly-fermi-2fff71` (round chain preserved — building
elsewhere = mixing/regression). Each stage = announce → inspect (R59) → build →
TS+lint → deploy-if-backend → real-data verify → SESSION_LOG → single-step commit →
push. Tiers are executed in order; within a tier, highest value/effort first.

**Tier 0 — Make it real (unblocks the core objective).**

- T0.1 **Deploy `/briefing` to Hetzner** (web2, additive: new service + quick tunnel,
  mirroring the proven `ichor-web` pattern; reversible <30 s; no Eliot secret needed).
  _Without this, nothing else is visible — highest priority._
- T0.2 Prepare externally-gated items to one-command readiness + step-by-step runbooks
  (PR for the 35 commits; CF Pages secrets; `ICHOR_CI_FRED_API_KEY`; credential
  rotation for the FRED/CF secrets leaked in journald; PAT revoke). **Claude prepares;
  Eliot performs the final irreversible/shared-state gesture.**

**Tier 1 — Close the explicit vision-coverage gaps.**

- T1.1 Volume panel (backend ready — pure frontend; SVG microchart).
- T1.2 Géopolitique panel (`_section_geopolitics` exists — surface it).
- T1.3 Holiday/weekend as a backend signal via `pandas_market_calendars`
  (DST-correct Paris session opens; skip/annotate on holidays).
- T1.4 Dedicated Sentiment panel + institutional positioning (CFTC TFF/COT;
  fill SPX/NAS positioning gap).
- T1.5 Correlations panel unconditional (fallback to `_section_correlations`).

**Tier 2 — Analytical depth (innovate / surprise, world-class).**

- T2.1 Cross-asset net-exposure / confluence lens in `verdict.ts` (data already on card).
- T2.2 Confluence re-weighted by source independence (fix overconfidence trap).
- T2.3 Pocket-skill honesty badge (surface LIVE Vovk/ADWIN calibration).
- T2.4 Event-priced-vs-surprise gauge (Polymarket already in key_levels).
- T2.5 `_section_gbp_specific` (SONIA + Gilt 10Y + BoE–Fed differential).

**Tier 3 — Autonomy hardening.**

- T3.1 Ship the missing `scripts/ci/fred_liveness_check.py` (make ADR-097 real).
  **[r92 DONE — the script existed since r61 but was broken by 2 latent defects ; r92 fixed
  both + added the first unit test. ADR-097 §Amendment (r92). Residual Eliot gesture:
  `gh secret set ICHOR_CI_FRED_API_KEY` (RUNBOOK-019) — the guard auto-activates then.]**
- T3.2 Human-visible degraded-data alert (break the silent-skip chain).
- T3.3 Enforce briefing/session-card ordering (`After=`) + batch-success watchdog.
- T3.4 Trace & resolve the Couche-2 Claude-vs-Cerebras/Groq doctrine divergence.

**Tier 4 — Premium UI system (the visual perfection mandate).**

- T4.1 Design-token foundation: Tailwind v4 OKLCH 3-layer tokens, tabular-nums,
  dark-default, motion tokens, server-rendered SVG microchart primitives
  (sparkline / probability ladder / correlation heat strip / regime timeline) —
  zero charting dep, RSC-clean.
- T4.2 Uncertainty-always (band/range, calibration note), explicit degraded/empty
  states, motion = function only (`reducedMotion="user"`), no theatrics/truncated axes.
- T4.3 Responsive/mobile pass + entrance-animation choreography refinement.

### D-4 — Autonomy boundary (calibrated)

Claude executes autonomously everything local/reversible/additive (code, additive
Hetzner deploy with rollback, ADRs, tests, SESSION_LOGs, commits, push to the
working branch). Claude does **not**, even under broad authorization: fabricate
secret values, rotate live credentials, merge 35 commits to `main`, or revoke a
PAT — these are irreversible/shared-state and are **prepared to one-command
readiness with step-by-step runbooks**; Eliot performs the final gesture. This is
not a refusal — it is the honest blast-radius boundary, announced not asked.

## Consequences

**Positive** — One governing artifact survives context compaction; "where we are /
what's done / where we go" is unambiguous; ADR-avant-code honored; the coverage
contract makes "done" measurable; T0.1 finally satisfies the literal core objective.

**Negative / trade-offs** — This is a multi-session program (Eliot answers
"continue" per stage, by design). USD/CAD retained backend creates a 6-vs-5 surface
asymmetry (documented, intentional, cheap). Tier ordering defers visual polish
(original r72 Option A) behind making the product reachable and complete — a
deliberate value reordering vs the r71-announced default, justified by the audit
finding that the dashboard is not deployed at all.

**Neutral** — No Voie D / ADR-017 risk introduced; existing prod untouched (Tier 0
is additive); all existing Accepted ADRs remain valid.

## Alternatives considered

- **Execute r72 Option A (visual polish) first, as announced r71** — rejected: the
  audit proved `/briefing` is deployed nowhere; polishing an invisible dashboard is
  zero user value. Reordered, not abandoned (Tier 4).
- **Rip USD/CAD out of the backend for a clean 5** — rejected: pure regression/churn
  risk, zero user value, violates "ne régresse pas / pas de double travail".
- **Merge the 35 commits to main now** — rejected for autonomous execution:
  irreversible shared-state, beyond safe scope even under broad authorization
  (D-4); prepared as a runbook instead.
- **One big refactor round** — rejected: violates "n'empile pas / position sizing /
  1 commit = 1 trade atomic"; staged tiers instead.

## References

- 10-subagent audit + recon wave, 2026-05-16 (memory arc / backend / frontend /
  ADRs / git+Hetzner ; vision-gap / deploy-reality / world-class web research /
  autonomy / trading review). Findings cited `[file:line]` / `[tool-output]` inline.
- [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) (§D1 amended),
  [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary),
  [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D),
  [ADR-093](ADR-093-aud-commodity-surface-degraded-explicit.md) (degraded-explicit pattern),
  [ADR-097](ADR-097-fred-liveness-nightly-ci-guard.md) (non-functional — T3.1 completes it),
  [ADR-098](ADR-098-coverage-gate-triple-drift-reconciliation.md) (Eliot path A/B/C pending).
- Web research sources (premium dashboard / SSR SVG microcharts / `pandas_market_calendars`
  / free data sources) captured in the r72 SESSION_LOG.
