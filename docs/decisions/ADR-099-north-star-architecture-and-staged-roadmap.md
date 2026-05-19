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
**[r78/r79 + r98 + r99 + r100 DONE — this gap is now closed END-TO-END: the
FRONTEND signal side (r78 `services/market_session.py` DST-correct +
NYSE-holiday engine + r79 `SessionStatus.tsx` rewired off the
DST-naive heuristic, §T1.3) ; the BACKEND card-gen-gate side (r98
[ADR-105](ADR-105-market-closed-gate-session-card-generation.md) — the
`run_session_cards_batch` per-asset pure-Python gate, FAIL-OPEN,
feature-flag OFF, ZERO systemd/register-cron) ; the BACKEND
BRIEFING-gate side (r99 ADR-105 §Implementation(r99) — the
`run_briefing` market-wide gate ; `weekly`/`crisis` EXEMPT as
intentional market-closed-time artefacts ; weekend-skip only [US
holidays keep the briefing — FX/XAU trade] ; distinct flag, FAIL-OPEN,
ships OFF) ; the IN-BRIEFING closed-market CAVEAT side (r100 ADR-105
§Implementation(r100) — NEW pure SSOT `briefing_market_caveat`
threaded into `_assemble_context`'s preamble on BOTH assembler paths ;
US-equity-holiday caveat surfaces `holiday_name` so SPX 500 / Nasdaq
sections are not read as a live US-equity session, AND the sibling
weekend-flag-OFF generated-daily-briefing caveat ; `weekly`/`crisis`
EXEMPT — same `_DAILY_BRIEFING_TYPES` gate). The **weekend-skip**
holiday-gate (session-cards r98 + briefing r99) AND the **in-briefing
closed-market caveat** (r100, closes the r99 YELLOW-1 caveat half) are
now complete — no *weekend* residual, no *caveat* residual ; the sole
remaining explicitly-deferred increment is the **US-holiday
fused-briefing asset-PRUNE** (mid-flow `assets` mutation, ~10
US-holidays/yr, YAGNI per ADR-105 §Implementation(r99)) — flagged
precisely, NOT rounded up to "holiday-gate fully done".]**

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
  **[r93→r97 DONE — silent-skip chain broken end-to-end : r93 ADR-103
  runtime FRED-liveness surface (LLM-input `_section_data_integrity` +
  operator `/v1/data-pool.degraded_inputs`) ; r94 ADR-092 §r94
  recalibration (the r93 surface exposed a latent false-DEGRADED
  mis-calibration it then fixed) ; r95 ADR-104 persisted
  `SessionCard.degraded_inputs` on the card (migration 0050,
  point-in-time honest) ; r96 ADR-104 §Implementation end-user
  `/briefing` `DataIntegrityBadge` (tri-state, ADR-017 footer) ; r97
  CI-gated the r96 `deriveDataIntegrity` + r91 `deriveVerdict` SSOT
  regression harnesses (vite/vitest peer-skew realign — they were
  CI-invisible before, the chain could silently drift). The alert is
  now explicit at every layer AND regression-protected.]**
- T3.3 Enforce briefing/session-card ordering (`After=`) + batch-success watchdog.
- T3.4 Trace & resolve the Couche-2 Claude-vs-Cerebras/Groq doctrine divergence.

**Tier 4 — Premium UI system (the visual perfection mandate).**

- T4.1 Design-token foundation: Tailwind v4 OKLCH 3-layer tokens, tabular-nums,
  dark-default, motion tokens, server-rendered SVG microchart primitives
  (sparkline / probability ladder / correlation heat strip / regime timeline) —
  zero charting dep, RSC-clean.
  **[r104 — OKLCH 3-layer token migration DONE. `apps/web2/app/globals.css`
  palette restructured into Layer 1 primitives (`:root --p-<family>-<step>`,
  raw semantic-free OKLCH ramp, ordinal value-decoupled steps) → Layer 2
  semantic (`@theme inline --color-*`, names byte-identical, now
  `var(--p-*)`) → Layer 3 compat aliases. All 22 hex/rgba palette tokens →
  exact-equivalent `oklch()` (CSS Color 4 reference conversion ; round-trip
  ΔsRGB = 0 on every token, 28/28 semantic = zero visual regression by
  construction, doctrine #9). tabular-nums + dark-default + motion tokens
  were ALREADY shipped pre-r104 (R59-verified by token, NOT re-claimed,
  lesson #11). Review trio 0 RED / 0 MUST-FIX, all findings applied. Deferred
  (full list in §Implementation r104): SSR SVG microchart primitives = r105 ;
  SSOT-dedup of palette-duplicating literals (glow-shadows / regime tints /
  selection / scrollbar) ; perceptual re-tuning ; severity-as-ramp ;
  pre-existing border-α §1.4.11 recalibration. See `## Implementation (r104,
  2026-05-18)`.]**
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

## Implementation (r104, 2026-05-18) — Tier 4 increment 1: OKLCH 3-layer token migration

The first T4.1 increment, scoped to the design-token foundation only (the SSR
SVG microchart primitives clause of T4.1 is a distinct component-building task,
deferred to r105 — honest non-atomic split, lesson #11). This dated note closes
the OKLCH-migration sub-item; ADR-099 §D-3 Tier 4 **is** the specification (no
new ADR — doctrine #9, the §T3.1 / §T3.2 / ADR-104 §Implementation(r96) /
ADR-105 §Implementation(r99,r100) immutable-append precedent).

**R59 reshaped the plan (doctrine #3).** The r104 R59 sweep (web2 code-map +
direct read of `apps/web2/app/globals.css`) found the token _infrastructure_
already mature and the specific OKLCH work already explicitly self-flagged:

- The pre-r104 `globals.css` palette header carried a verbatim deferral
  _"Full OKLCH palette migration deferred — needs a dedicated session with
  visual diff review per route, not a code-only flip."_ (in the Borders
  comment block of the parent commit's `globals.css`; r104 rewrote that
  region so the string no longer exists — line-pins intentionally dropped,
  see `git show <parent>:apps/web2/app/globals.css`). r104 **is** that
  dedicated session.
- `tabular-nums` (the `.font-mono,code,[data-numeric]`
  `font-feature-settings:"tnum","zero"` rule), dark-default (single dark
  surface system, no light mode), and the motion tokens (`--duration-*` /
  `--ease-*`) were **already shipped** pre-r104 (verified in the r104 R59
  read — referenced by token, not line, since the migration shifts line
  numbers). They are part of the T4.1 wording but were NOT re-implemented
  and are NOT claimed as r104 work (lesson #11 — name what is already done
  rather than rounding "T4.1 complete").

**What r104 implemented.** `apps/web2/app/globals.css` palette (the ~22 color
tokens at the former lines 32-93) restructured into the ADR-099-mandated
3 layers, all in OKLCH:

1. **Layer 1 — primitives** (`:root`): a raw, semantic-free OKLCH ramp,
   `--p-<family>-<step>` (e.g. `--p-ink-950`, `--p-emerald-400`,
   `--p-cobalt-600`). The suffix is an **ordinal Tailwind-style step
   (50 lightest … 950 darkest within the family), DECOUPLED from the literal
   OKLCH lightness** — applied per the ui-designer r104 review so that the
   named next increment (perceptual ramp re-tuning) changes a primitive's
   _value_ only, never its _name_: no Layer-2 rename cascade, and two
   near-lightness primitives can never collide on a rounded suffix. One
   primitive per real color in use — no fabricated unused ramp steps
   (anti-accumulation #9 / YAGNI).
2. **Layer 2 — semantic** (plain `@theme` — the exact pre-r104 structural
   placement): the existing `--color-*` names **unchanged**, value rewritten
   `hex → var(--p-*)`. Pure-white-alpha borders and the ink-alpha overlay
   expressed as direct `oklch(L C H / α)` (alpha application of their
   primitive — no relative-color dependency, lossless ; a future
   relative-color cleanup so they track the primitive on re-tune is flagged
   in the file, deferred to the dedup pass). (A first pass used `@theme
inline` per a context7 reading; the deploy-witness disproved that choice —
   see "Deploy-witness investigation" below — and it was reverted to plain
   `@theme`, the pre-r104 structure.)
3. **Layer 3 — compat aliases** (plain `@theme`): `--color-ichor-deep`,
   `--color-bg-deep`, `--color-border` — unchanged var-references (already a
   component-compat layer).

**Zero visual regression by construction.** Each hex/rgba → its exact CSS
Color 4 OKLCH equivalent (not a re-tuned ramp). A round-trip check
(sRGB→OKLCH→sRGB at the shipped 4-decimal precision) returned ΔsRGB = 0 byte
for all 22 tokens. Because every Layer-2 semantic name is byte-identical and
every consumer uses the arbitrary `[--color-*]` form, no component changes; the
rendered pixels are provably unchanged. Perceptual _re-tuning_ within OKLCH
(smoother ramps, gamut-aware chroma) is a separately-verifiable future value-add,
deliberately NOT bundled here (position-sizing — one atomic, provable increment).

**Deploy-witness investigation (honest record — lesson #11 / #13 / process>outcome).**
The real-prod browser witness (deployed `/briefing`, `getComputedStyle` +
canvas sRGB readback) surfaced that **4 semantic tokens with ZERO web2
consumers — `--color-ichor-deep`, `--color-bull-deep`, `--color-bear-deep`,
`--color-accent-cobalt-deep` — are absent from the compiled `:root`**, even
though the green build + HTTP 200 + the file-level ΔsRGB=0 proof had all
passed (precisely why we witness — "marche exactement ≠ ça marche"). Two
hypotheses were formed and **empirically falsified, not assumed**: (H1)
"`@theme inline` tree-shakes them" — falsified: moving Layer 2/3 to plain
`@theme` and re-deploying left the _same_ 4 absent; (H2) "an r104 regression"
— **falsified by a decisive control**: building the pre-r104 `globals.css`
(`git show HEAD:…`) and grepping its compiled CSS shows the _identical_ 4
tokens absent there too, while consumed var-refs (`--color-bg-deep`,
`--color-accent-cobalt-bright`) are present in both. **Verified root cause:**
Tailwind v4's production build tree-shakes theme tokens with zero references
— identical pre/post-r104 and in both `@theme` modes; the discriminant is
consumer-count, not the migration. **This is pre-existing, by-design, and
zero functional impact** (nothing reads an unemitted variable that nothing
consumes; the first component to reference `[--color-bull-deep]` makes
Tailwind emit it). **Disposition: ACCEPT** — forcing emission via `@theme
static` would ship dead CSS for 0-consumer tokens (the accumulation this
project forbids; depth-variants are on-demand by design, ui-designer r104).
The source definitions stay as the documented palette contract. Net: the
r104 migration is **emission-neutral and contrast-neutral** vs pre-r104 — the
exact same 24 consumed tokens are emitted, now in OKLCH at ΔsRGB=0; the
correct success criterion is "24/24 consumed tokens render sRGB-exact",
proven on real prod, NOT "28/28 source tokens in `:root`".

**Deliberately out of scope (honest residuals, lesson #11 — enumerated in the
`globals.css` header §1–§6, surfaced by the r104 review trio).**
(a) spacing / radius / shadow / motion / z-index tokens (not palette —
byte-identical); (b) **SSOT-dedup** of base-CSS literal colors that still
duplicate the Layer-1 palette: `--shadow-glow-bull/-bear/-cobalt`
(ui-designer r104 — an unlisted orphan, now tracked), the
`html[data-regime=*]` ambient tints, `::selection`, scrollbar — all
byte-identical this round; (c) **SSR SVG microchart primitives = r105** —
must add NEW `--p-chart-*` sequential/diverging ramps, not overload the
semantic accents (ui-designer r104); (d) **perceptual ramp re-tuning** —
values are exact ports today, not yet a designed perceptual ramp; (e)
**severity is four unrelated hues**, not a coherent info→warn→alert→critical
scale — rebuild during re-tuning (ui-designer r104); (f) **border-alpha
recalibration** — accessibility-reviewer r104 measured the subtle/default
border alphas at **1.84:1 / 2.87:1** composited over `--color-bg-surface`,
_below_ the WCAG 2.2 §1.4.11 3:1 floor (only `strong` = 4.98:1 clears). This
is a **pre-existing** miscalibration (the 2026-05-06 raise computed the
endpoint ratio, not the α-over-backdrop ratio) — r104 carries the values
**byte-identical (ΔsRGB=0, NOT an r104 regression — the migration is
contrast-neutral by construction)** and only corrects the now-false
`globals.css` comment to the true ratios (lesson #11 — do not re-affirm a
false WCAG claim); the real α fix (subtle ≈ 0.34, default ≈ 0.46 over
`#0B1220`) is a visual change owed to the dedup/recalibration pass; (g) no
`@media (forced-colors: active)` / `prefers-contrast` (pre-existing gap,
backlog — accessibility-reviewer r104 ADVISORY-2).

**Tailwind v4 correctness** verified via context7 (authoritative
`/tailwindlabs/tailwindcss.com`): `oklch()` in `@theme` is the canonical v4
pattern (the default Tailwind palette itself is oklch-in-`@theme`); a theme
color referencing another CSS variable is the documented `var()`-value pattern
(empirically proven in this file's pre-r104 `--color-border: var(--color-border-default)`
and `@theme inline` font block, live 30+ rounds); the arbitrary opacity modifier
`bg-[--color-*]/N` emits `color-mix(in oklab, var(--color-*) N%, transparent)`,
oklch-safe.

**Verification.** A name-agnostic parser resolved all 28 Layer-2 semantic
tokens through the Layer-1 primitives back to sRGB(+α): **ΔsRGB = 0, ΔA = 0,
28/28, name-set identical** (the migration's safety proof, re-run after the
review fixes — values are byte-unchanged, only primitive names + comments
changed). web2 build gate (`pnpm --filter @ichor/web2` typecheck +
`eslint --max-warnings 0` + `vitest run` 68/68 + `next build`) green.
**Review trio — 0 RED / 0 MUST-FIX, all findings applied pre-merge:**
ichor-trader R28 (ADR-017 frontend boundary GREEN — a token migration carries
no signal; framework axes N/A-confirmed; 2 doc-only YELLOW = the stale
`globals.css` self-citation de-pinned + `ROADMAP_2026-05-06.md:518` annotated
`[r104 DONE]`); ui-designer (architecture "sound, ship it"; 6 findings — the
primitive ordinal-step rename + 5 deferred-residual / comment notes — applied);
accessibility-reviewer (WCAG 2.2 AA — **the crux claim rigorously confirmed:
exact OKLCH equivalence with ΔsRGB=0 preserves every contrast ratio
identically, by definition, since WCAG luminance is a pure function of sRGB
and OKLCH is never an input; spot-checks text-muted 5.33:1 / primary 17.08:1 /
focus-ring 10.50:1 all PASS**; the one substantive item — sub-3:1 subtle/
default borders — is **pre-existing, not an r104 regression**, and r104's only
obligation, met, was to stop the migrated comment re-affirming the false
ratio). Real-prod render witnessed by Playwright directly against the **deployed**
`/briefing` (the Tier-0 quick-tunnel URL is public-by-design — this witnesses
the actual deployed artifact, stronger than a local re-render): the
`--color-* → var(--p-*) → oklch()` chain resolves in a real browser, body/H1
render the exact computed OKLCH, page is styled (not the unstyled fallback a
broken emission would give), and a canvas sRGB readback of every consumed
token reproduces the exact pre-r104 hex byte (ΔsRGB=0 at render). The
witness also surfaced the pre-existing 0-consumer tree-shake (see Deploy-
witness investigation). Voie D + ADR-017 held; additive web2-only deploy;
zero backend / zero migration.

## Implementation (r105, 2026-05-18) — Tier 4 increment 2: the microchart SSOT foundation

T4.1's "server-rendered SVG microchart primitives" clause, scoped to the
**reusable foundation only** — honest non-atomic split (the 4 primitives +
the `--p-chart-*` ramp are subsequent consumer-backed increments). ADR-099
§D-3 Tier 4 **is** the spec — dated append, no new ADR (doctrine #9).

**Context-frugal scope (lesson #17).** The r104 close recommended `/clear`;
Eliot replied `continue` (override — his prerogative). Per the r101
precedent: honor it context-frugally, scope to the **R53-safe** slice, do
NOT re-propose `/clear`. The R53-safe slice = a pure-function extraction
provably byte-identical (zero token/data/visual hallucination surface),
NOT a multi-primitive build in a deep session.

**R59 reshaped the plan (doctrine #3).** The anti-doublon navigator found:
(1) **no shared microchart SSOT exists** — the SVG coordinate math is
hand-rolled and DUPLICATED three times (`VolumePanel` slot/volH,
`app/confluence/history` xAt/yAt, `components/ui/regime-quadrant`
pathFromHistory) = the exact doctrine-#9 accumulation; (2) `CorrelationsStrip`
(r82) already renders a diverging bar strip and `ScenariosPanel` already a
probability ladder → those primitives must **EXTEND** in place, never
duplicate; (3) the "RSC-clean" wording is half-true — the existing panels
are `"use client"` (motion); the correct reading is a **pure plain module**
(server-safe math) consumed by client panels (doctrine #5 split).

**What r105 implemented.**

1. **NEW `apps/web2/lib/microchart.ts`** — a pure, RSC-safe, zero-dependency
   SSOT: `svgCoord` (the 1-dp formatting authority), `linScale` /
   `xLinear` (the canonical linear-scale base — see Review fixes C1),
   `bandLayout`, `barFromBaseline` (0-baseline, no truncated axis — design
   invariant, **fail-loud** enforced, see I2), `bandSeriesPolyline` (the
   band-coupled VolumePanel helper — see N4). Distilled from `VolumePanel`'s
   proven pattern. No `"use client"`, no React, only `Math`/string (the
   `lib/verdict.ts` / `eventSurprise.ts` / `dataIntegrity.ts` house idiom).
2. **`VolumePanel.tsx` refactored** onto the SSOT — render **byte-identical**
   (the now-unused `pMin/pMax/pSpan` removed; geometry → `bandLayout` /
   `bandSeriesPolyline`; bar map → `barFromBaseline`).
3. **NEW `__tests__/microchart.test.ts`** — the byte-identical proof
   (doctrine #9 / the r71 lib/verdict.ts pattern, sharpened): the test
   embeds the **verbatim** pre-r105 `VolumePanel` inline expressions and
   asserts exact string / deep equality over realistic + edge fixtures
   (equal-closes span-fallback, n=2, large values) + specs pinning the
   `linScale`/`xLinear` scale primitives and the `barFromBaseline` guard.
   All green, CI-gated since r97. Proof is exact-string, > DOM-length.
4. **`components/ui/regime-quadrant.tsx:14-15`** stale "Phase A peut migrer
   sur d3" tech-debt note retired — r105's zero-dependency mandate
   forecloses the d3 path; replaced with the SSOT-migration pointer
   (prompt-decomposer item; navigator flag #3).

**Review fixes applied pre-merge (consolidated, single pass).** ichor-trader
R28: 4 GREEN (ADR-017/Voie-D N/A, framework axes N/A, over-claim GREEN,
byte-identical three-way agreement verified) + **YELLOW-1** applied — the
`lib/microchart.ts` header now past-tense ("the math **was** DUPLICATED in
three places; r105 migrates `VolumePanel` onto this SSOT, the remaining two
follow") since r105's own change made VolumePanel no longer a duplicate (2
still-inline, not 3 ; the ADR R59-finding text below is correctly historic).
ui-designer: **C1 (Critical) applied** — added `linScale` (canonical
domain→range) + `xLinear` (point-index x): a VolumePanel-only helper set is
not a genuine SSOT; the announced r106 consumers (`confluence/history`
xAt/yAt, sparkline, regime timeline, proportional ladder/heat-strip
scalars) need a linear scale, so omitting it would force an r106 SSOT
retrofit = the doctrine-#9 outcome to forbid (non-speculative — 3+ named
consumers, the correct base). **I2 applied** — `barFromBaseline` now throws
`RangeError` on `value < 0`/`maxValue <= 0` so a truncated-axis attempt
fails loud at the SSOT, not silently at pixels (VolumePanel inputs —
`volume >= 0` filtered, `maxVol = max(...,1)` — never trip it ⇒
byte-identical preserved). **N4 applied** — `seriesPolyline` →
`bandSeriesPolyline` (band coupling in the name; frees the generic name for
the future linear polyline ; impl byte-identical, only the symbol renamed).
accessibility-reviewer: **N/A-with-reason** — the VolumePanel render is
proven byte-identical, so DOM/colours/contrast are definitionally
unchanged ; a11y becomes MANDATORY at the r106 heat-strip's new
colour-encoding.

**Verification.** web2 build gate GREEN (re-run on the post-review
consolidated shape — doctrine #14): `tsc --noEmit` 0 + `eslint
--max-warnings 0` 0 + **vitest 6 files / 84 tests** (r104 baseline 5/68 +
`microchart.test.ts` 16 = 9 verbatim-embedded byte-identical assertions
[unchanged-green on the renamed `bandSeriesPolyline` ⇒ the consolidated
review fixes preserved byte-identity] + 7 `linScale`/`xLinear`/guard specs)

- `next build` OK. Review trio
  (ichor-trader R28 ADR-017/over-claim/cross-file-drift + ui-designer SSOT
  design ; accessibility-reviewer N/A-with-reason — the `VolumePanel` render
  is proven byte-identical, so DOM/colours/contrast are definitionally
  unchanged ; a11y becomes MANDATORY when the heat-strip ships actual new
  colour-encoding in r106). Real-prod render witnessed by Playwright on the
  deployed `/briefing/[asset]`: `VolumePanel` SVG pixel-identical to pre-r105.

**Deliberately deferred — consumer-backed, announced (r104 tree-shake
lesson applied PROACTIVELY: no token without its consumer).** The
`--p-chart-*` OKLCH sequential/diverging ramp ships **with** its first
consumer (the correlation heat-strip), NOT alone (it would be tree-shaken
dead — the verified r104 finding). Subsequent verified increments:
correlation heat-strip = **extend** `CorrelationsStrip` + the
`--p-chart-div-*` ramp it consumes ; probability ladder = **extend**
`ScenariosPanel` onto the SSOT ; sparkline = extract `VolumePanel`'s
polyline as a `<Sparkline>` on the SSOT ; regime timeline = NEW (reuse
`regime-quadrant`'s `RegimeId`/`QUADRANTS` colour map, no redefinition) ;
`confluence/history` + `regime-quadrant` migrated onto the SSOT (completes
the doctrine-#9 de-accumulation). Real prod data for all four is R59-
verified live this round (`/v1/correlations` 8×8 matrix · `/v1/scenarios/{a}`
3 scenarios · `/v1/market/intraday/{a}` 479 OHLCV bars · `/v1/sessions/{a}`
20-card regime history) — zero backend work needed.

**I3 (ui-designer, deferred with reason).** `bandSeriesPolyline` should
eventually _compose_ `linScale` rather than re-implement min..max
normalization. NOT done in r105: re-expressing the proven byte-identical
formula atop `linScale` changes float-operation order = a byte-identical
_risk_ for zero r105 consumer benefit (no caller composes it this round).
It is done at the `confluence/history` migration (r106+), where the
linear-polyline path is built and the `bandSeriesPolyline` ≡ `linScale`
composition is re-proven byte-identical against the embedded verbatim
fixtures — the correct round to absorb that risk with a test gate.

Voie D + ADR-017 held; additive web2-only deploy; zero backend / zero
migration.

## Implementation (r106, 2026-05-18) — Tier 4 increment 3: the correlation heat-strip

T4.1's "correlation heat strip" microchart primitive, shipped as the
**first consumer of the r105 SSOT and the first consumer-backed
`--p-chart-*` ramp** (the r104 tree-shake lesson applied PROACTIVELY: the
diverging ramp ships _with_ its consumer, never alone). ADR-099 §D-3
Tier 4 **is** the spec — dated append, no new ADR (doctrine #9 ; the
§T3.1 / §T3.2 / ADR-104 §Implementation(r96) / ADR-105 §Implementation(r99,
r100) / §Implementation(r104,r105) immutable-append precedent). The
r105-close binding default executed verbatim (doctrine #10, no pivot).

**R59 reshaped the plan (doctrine #3 — inspected the real shapes, not the
memory).** Direct file:line read (no sub-agent hypothesis layer — the
strongest R59): (1) `CorrelationsStrip.tsx` (r82) is `"use client"`
(motion), props `{ snapshot: unknown }` → a flat `Record<string,number>`
(NOT the 8×8 `CorrelationMatrix`; the page derives a compact per-asset row
via `deriveCorrelationRow`, precedence `card.correlations_snapshot` ?? live
`/v1/correlations`) → **EXTEND in place, never a new file** (anti-doublon
#9, the binding default's explicit constraint) ; (2) it already carries
label + magnitude-as-bar-length + `+`/`−` sign + `.toFixed(2)` value but a
**binary** `--color-bull`/`--color-bear` fill — and **only `+`/`−`, NO
`▲`/`▼`**, a pre-existing SPEC §14-row3 non-compliance (the mandatory
`+/−` _AND_ `▲/▼` redundancy on 100 % of numeric displays) that the new
colour-encoding round is the correct moment to close (the mandatory
accessibility-reviewer would flag it regardless — fixed proactively) ;
(3) `microchart.ts` (r105) header lines 14-15 literally name
"proportional ladder/**heat-strip** scalars" as `linScale`'s announced
consumers → consuming `linScale` here **fulfils the r105 SSOT's stated
purpose**, the cleanest possible doctrine-#9 alignment (not accumulation —
the announced consumer arriving) ; (4) `app/briefing/page.tsx` (cockpit)
does NOT mount it — only `app/briefing/[asset]/page.tsx:358-375` (detail),
so the blast radius is one route's one section.

**What r106 implemented.**

1. **NEW `--p-chartdiv-*` Layer-1 OKLCH diverging primitives + Layer-2
   `--color-chart-div-*` semantic tokens** in `globals.css` (r104's exact
   two-layer convention: `:root` ordinal slots re-tune-stable, `@theme`
   semantic names the component consumes). A 7-stop perceptually-uniform
   diverging scale: `neg-strong/-mid/-weak` (bear, H 25°) ·
   `neutral` (near-achromatic slate, H 256.79°) · `pos-weak/-mid/-strong`
   (bull, H 163.22°). **Constant lightness L = 0.72** across all 7 stops by
   design — correlation magnitude reads via _chroma + hue_, never
   lightness, so the heat encoding does not confound the bar-LENGTH
   signal it sits beside (accessibility-reviewer r106 explicitly upheld
   this constant-L choice — 0 must-fix). **Symmetric |C| both poles**
   (ui-designer r106 UD-2 applied): `C_STRONG = 0.155` is the maximum
   chroma in sRGB gamut common to BOTH H 25° and H 163.22° at L 0.72
   (emerald cannot hold the bear's 0.168 there) — so a symmetric |ρ|
   reads EQUAL intensity on either hue; mid/weak keep the 0.115/0.062-
   over-0.168 proven ratios (→ 0.1061 / 0.0572). Every value is the exact
   CSS Color 4 OKLCH spec coordinate (pure-Python Ottosson reference
   transform, the r104 methodology done dependency-free; **self-checked**
   — the transform round-trips r104's already-ΔsRGB=0-verified `#F87171`
   to `oklch(0.7106 0.1661 22.22)` exactly, proving the matrices ARE the
   CSS Color 4 reference, ichor-trader r106 IT-a): all 7 verified **in
   sRGB gamut** and **round-trip ΔsRGB = 0** at the shipped precision (a
   _designed_ ramp, not a port). Hues anchored to the established palette
   poles (`--p-red-400` ≈ #F87171 bear hue, `--p-slate-400` ≈ #94A3B8
   slate-hue neutral, `--p-emerald-400` ≈ #34D399 bull hue) for
   cross-palette coherence. Every token is referenced by the heat-strip
   THIS round (no tree-shaken dead token — r104 verified finding applied
   proactively).
2. **`CorrelationsStrip.tsx` extended** (same file, same `<section>`, same
   data, anti-doublon): (a) a compact **SSR SVG heat-strip row** — one
   equal-width cell per correlated asset, geometry via the r105 SSOT
   (`bandLayout` columns + `svgCoord` 1-dp formatting), fill = ρ → discrete
   `--color-chart-div-*` stop via the r105 SSOT `linScale` in a
   **signed-offset symmetric** form — `linScale(0, 1, 0, _CENTER)` (where
   `_CENTER = (N−1)/2`, the token-count-derived centre, NOT a hard-coded
   literal — ichor-trader r106 IT-b) maps |ρ| onto the half-axis distance
   from the neutral centre, then the sign is applied (ρ=+x and ρ=−x land
   equidistant on opposite hues ; a naive `linScale(-1, 1, 0, N−1)` +
   `Math.round` is asymmetric — half-up sends ρ=+0.50→idx5 vs ρ=−0.50→idx2
   on the common 2-dp `deriveCorrelationRow` values — caught + fixed
   before commit). The `▲`/`▼`/`◆` direction glyphs are an **HTML
   overlay**, NOT SVG `<text>`: the strip SVG is `preserveAspectRatio=
"none"` (it stretches ~20× horizontally) which would smear `<text>`
   — the rects tolerate the stretch, glyphs must not (ui-designer r106
   UD-1) ; the overlay's `flex-1` cells align exactly to the rect column
   centres ((i+0.5)/n). The whole strip is **`aria-hidden` DECORATIVE**
   (accessibility-reviewer r106 ADV-1/ADV-2: it has no independent
   magnitude channel, and an SVG `aria-label` + the `<ul>` would
   double-announce to screen readers). (b) the labelled `<ul>` is the
   **single authoritative accessible source** — label + bar length + sign
   - glyph + value, all non-colour — its bar fill upgraded from the binary
     bull/bear to the same continuous ramp stop (slightly muted so the strip
     stays the focal gestalt, UD nit) ; (c) `▲`/`▼`/`◆` glyph added to the
     value cell (positive / negative / near-zero band) → SPEC §14-row3
     closed: every row now carries **colour + bar-length + sign + glyph +
     numeric value** (quintuple redundancy ; WCAG 1.4.1 satisfied by
     non-colour signals, the colour is decorative-redundant — the correct
     architecture for a red↔green diverging scale, inherently the CVD
     worst-case at constant L ; the strip↔list coupling is documented as a
     load-bearing invariant in the component docstring, ADV-1). ADR-017
     "contexte pré-trade — pas un ordre" disclaimer added in-component +
     the legend swatches re-pointed off the binary bull/bear onto the ramp
     endpoints so the legend matches the body (ichor-trader r106 IT-c).
3. **NEW `apps/web2/lib/correlationHeat.ts`** — the ρ→encoding brain as a
   PURE plain module (no `"use client"`, doctrine #5 + the `lib/verdict.ts`
   r71 / `eventSurprise.ts` r89 / `dataIntegrity.ts` r96 house idiom):
   `DIV_STOPS` (the 7 Layer-2 tokens, ordinal order), `divergingStop` (ρ →
   token, composing the r105 SSOT `linScale`, clamp [-1,1] defensive),
   `trendGlyph` (the §14 non-colour direction signal). It is NOT a
   speculative SSOT (r104 YAGNI) nor a fake-SSOT (r105) — concrete present
   consumer (the heat-strip) + concrete test consumer, the blessed r96
   `deriveDataIntegrity` shape ; the GENERAL primitive it composes
   (`linScale`) is the r105 microchart SSOT, this is its announced
   "heat-strip scalars" consumer (not a duplicate). `CorrelationsStrip`
   becomes the thin view importing it — so the mapping is unit-testable
   WITHOUT pulling `motion/react` into the node test (the r105 lesson).
4. **NEW `__tests__/correlationHeat.test.ts`** — pins the ρ → stop pure
   mapping (the r105 microchart-test pattern: −1 → `neg-strong`, +1 →
   `pos-strong`, 0 → `neutral`, monotone, symmetric, clamp beyond ±1, the
   SSOT `linScale` composition) + the glyph/near-zero-band contract,
   CI-gated since r97.

**Honest non-atomic split (lesson #11).** r106 = the heat-strip + its
consumer-backed ramp ONLY. The announced subsequent increments — probability
ladder (extend `ScenariosPanel`), sparkline (extract `VolumePanel`'s
polyline), regime timeline (NEW), and the `confluence/history` +
`regime-quadrant` SSOT migrations that complete the doctrine-#9
de-accumulation (with I3, `bandSeriesPolyline` ≡ `linScale` re-proven
byte-identical) — are explicitly DEFERRED, each its own verified increment.

**CVD note — adjudicated.** A red↔green diverging hue ramp at constant
lightness is the deuteranopia/protanopia worst case _for the colour channel
alone_. The mandatory accessibility-reviewer **upheld the constant-L choice
(0 must-fix / 0 should-fix, PASS)**: the colour is strictly redundant —
direction is also sign + `▲`/`▼` glyph, magnitude is also bar length, exact
is also the tabular numeric ; adding a lightness cue would (a) drop glyph
contrast asymmetrically toward the 4.5:1 floor and (b) re-confound the
adjacent bar-length signal. No information is lost on the colour channel for
a CVD user (the `<ul>` glyph+sign+value path is colour-free).

**Review fixes applied pre-merge (consolidated, single pass).** All three
mandatory reviews ran in parallel on the worktree shape; every finding was
applied (or N/A-with-reason) in one consolidated pass, re-verified on the
committed (post-prettier) shape (doctrine #14).

- **ichor-trader R28 — 0 RED / 3 YELLOW, all applied.**
  - _IT-a_ (the substantive one — "executed, not reworded"): the
    "round-trip ΔsRGB=0 / byte-exact hex" wording was asserted-not-verified
    (a web converter disagreed). Resolved empirically: the pure-Python
    Ottosson reference was self-checked against r104's already-verified
    `#F87171 → oklch(0.7106 0.1661 22.22)` = exact MATCH ⇒ the matrices ARE
    the CSS Color 4 reference, the web converter is the gamut-mapping
    outlier ; real per-stop numbers now in Verification below ; every
    `/* sRGB #hex */` provenance comment corrected to the round-tripped
    value.
  - _IT-b_ (doc drift): the `linScale(0,1,0,3)` / `(-1,1,0,6)` literals
    rephrased to track `_CENTER = (N−1)/2` (token-count-derived) in this
    ADR + `lib/correlationHeat.ts` + the component docstring.
  - _IT-c_ (cross-file visual drift my change introduced): the header
    legend still used the binary `--color-bear`/`--color-bull` while the
    body used the ramp → legend swatches re-pointed to
    `--color-chart-div-neg-strong` / `-neutral` / `-pos-strong` (the
    endpoints+centre the user actually sees ; contrast re-verified
    7.04 / 7.53 / 8.09:1 on the surface, all clear 1.4.3).
  - GREEN, recorded: ADR-017 boundary, economic soundness (symmetric
    diverging of Pearson ρ, near-zero band, |ρ| sort), Voie D/ADR-023 N/A
    (pure frontend), symmetry/monotonicity/clamp test-proven, anti-doublon
    (extended in place ; the page-wiring precedence fix below is a
    documented R59-reshape, NOT a silent byte-change), doctrine-#9 dated
    append.

**Real-prod witness reshaped scope (R59 / doctrine #3 ; lesson #1
forecast≠preuve / #2 SHIPPED≠FUNCTIONAL).** The Playwright witness on the
deployed dashboard caught that the heat-strip rendered on **zero** priority
assets: `/v1/correlations` is LIVE and rich (real 8×8, n=257) but **every
current prod card carries an EMPTY `{}` `correlations_snapshot`**, and the
pre-existing r82 page precedence `cardCorr ?? liveCorrRow` pinned that
truthy-but-empty object so `CorrelationsStrip` returned `null` everywhere.
This is a **pre-existing r82 data-precedence defect, not an r106
regression** (the same `entries.filter(typeof number)` existed in r82) —
but shipping a heat-strip a user never sees is the lesson-#2
SHIPPED≠FUNCTIONAL failure the mission forbids. The minimal additive fix
(`app/briefing/[asset]/page.tsx`): a card snapshot counts only if it has
≥1 numeric ρ entry, else it is treated as absent so the precedence falls
through to the rich live `deriveCorrelationRow` (the r69 "the live path
EXISTS but is dead — completing it IS the task, not scope creep" class ;
the `correlationSource` label then honestly reads "Live …"). ADR-017-neutral
(data-source precedence only, no signal change), additive, one route's data
wiring. The witness was re-run post-fix (below) — not forecast.

- **ui-designer — 3 Important + 2 nits, all applied.** _UD-1_ SVG `<text>`
  smeared by `preserveAspectRatio="none"` → glyphs moved to a non-scaled
  HTML `flex-1` overlay (rects stay in the SVG). _UD-2_ asymmetric pole
  chroma (0.168 vs 0.152) → symmetric `C_STRONG=0.155` (max common
  in-gamut, re-derived + re-verified). _UD-3_ label span → `truncate` +
  `title`. _Nits_: list bar `opacity-90` (strip is the focal gestalt) ;
  small-N layout assumption pinned in the docstring. Validated by the
  reviewer: constant-L correct, token naming r104-correct,
  `lib/correlationHeat.ts` extraction correct (no duplication), empty/null
  states clean, reduced-motion globally handled (`MotionConfig
reducedMotion="user"`).
- **accessibility-reviewer (MANDATORY, new colour-encoding) — 0 MUST-FIX /
  0 SHOULD-FIX, PASS, 3 ADVISORY.** _ADV-1_ strip↔list coupling documented
  as a load-bearing invariant in the docstring. _ADV-2_ SVG made
  `aria-hidden` decorative (removes the SVG↔`<ul>` double announcement ;
  the `<ul>` is the single SR source). _ADV-3_ (no `@media
(forced-colors)`) = pre-existing, out of r106 scope, already a tracked
  globals.css §6 backlog item — **N/A r106** (glyph+sign+value survive
  forced-colors regardless). 1.4.1 / CVD / 1.4.11 / 1.4.3 / 1.3.1 / 4.1.2
  / 2.3.3 all PASS with computed ratios (below).

**Verification (real in-repo numbers, not asserted).**

- **OKLCH self-check** (the IT-a resolution): pure-Python Ottosson
  reference, `#F87171 → oklch(0.7106 0.1661 22.22)` = exact MATCH vs the
  r104-shipped value ⇒ CSS Color 4 reference confirmed.
- **Ramp (final, symmetric)** — all in-gamut, round-trip ΔsRGB = 0 at the
  shipped 4-dp precision: `neg-strong oklch(0.72 0.155 25)→#F67972` ·
  `neg-mid 0.1061→#DF8A83` · `neg-weak 0.0572→#C69793` ·
  `neutral 0.019 256.79→#9DA5B1` · `pos-weak 0.0572 163.22→#84B09B` ·
  `pos-mid 0.1061→#5FBA92` · `pos-strong 0.155→#01C289`.
- **WCAG contrast** (sRGB relative luminance): glyph `#04070C` on every
  ramp stop = **worst 7.59:1** (neg-strong) … 8.72:1 (pos-strong) — clears
  1.4.3 (4.5:1) on all 7 ; list value `#E6EDF3`/surface = 15.85:1 ;
  re-pointed legend endpoints on surface = 7.04 / 7.53 / 8.09:1. All PASS.
- **web2 build gate** re-run on the post-review consolidated + prettier
  shape (doctrine #14): `tsc --noEmit` 0 · `eslint --max-warnings 0` 0 ·
  **vitest 7 files / 95 tests** (r105 baseline 6/84 + `correlationHeat`
  11 ; zero regression) · `next build` OK.
- **Real-prod witness** — Playwright on the deployed public dashboard URL
  (doctrine #7 zero-exposure ; the witness, not a forecast — it reshaped
  scope twice):
  - R53 `/v1/correlations` re-confirmed LIVE: 200, real 8×8 matrix, 8
    assets, `n_returns_used=257`, real floats.
  - **Witness #1 caught the SHIPPED≠FUNCTIONAL gap** (→ the page-wiring
    precedence fix above): pre-fix the heat-strip rendered on ZERO assets
    (all 5 priority cards carry an empty `{}` snapshot).
  - **Witness #2 caught a pre-existing app-wide defect** (the heat-strip
    _surfaced_ it, did not introduce it): the Tailwind-v4
    `text-[--color-*]` bracket-arbitrary class produces no working colour
    rule (verified on UNTOUCHED `page.tsx:242`/`:377` elements too) — the
    `:root` tokens are correctly defined, the bracket form just doesn't
    apply. r106's NEW colour-critical elements (overlay glyph, legend)
    were re-pointed to inline `style` `var()` — the mechanism empirically
    proven this round (rect `fill` / bar `backgroundColor` resolve to the
    exact OKLCH). The pre-existing app-wide issue is OUT OF r106 SCOPE
    (codebase-wide, touches the r104 token system, needs its own R59 +
    per-route visual-diff round) — flagged as a dedicated task, NOT
    silently rewritten, NOT claimed fixed (calibrated honesty #11).
  - **Final witness GREEN** (deployed, real live data, `EUR_USD`):
    `sourceLabel`="Live · fenêtre 30 j" (precedence fix works) ; 7 SVG
    rects fill = the live `--color-chart-div-*` resolving to exact OKLCH
    (`pos-mid oklch(0.72 0.1061 163.22)` etc., constant-L confirmed) ;
    HTML overlay glyphs `▲▲▲▼▼▲▲` in `--color-bg-base`
    `oklch(0.1268 0.0141 254.03)` (dark — the a11y-verified ≥7.59:1
    restored) ; SVG `aria-hidden=true`, `role`/`aria-label`=null (ADV-2) ;
    legend "−1 inverse"/"neutre"/"+1 ensemble" =
    `oklch(0.72 0.155 25)`/`(0.72 0.019 256.79)`/`(0.72 0.155 163.22)`
    (the ramp endpoints — IT-c achieved) ; 7 `<ul>` rows real correlations
    (GBP/USD +0.77 ▲ … SPX500 +0.28 ▲) sorted by |ρ|, each label +
    diverging bar (`opacity-90`) + glyph + signed tabular value
    (quintuple signal) ; ADR-017 disclaimer rendered ; console = only the
    pre-existing `404 favicon.ico`. Visual screenshot confirms the
    premium heat gestalt + non-smeared glyphs (UD-1).

Voie D + ADR-017 held; additive web2-only deploy; zero backend / zero
migration.

## Implementation (r107, 2026-05-18) — Tier 4 hygiene: app-wide Tailwind v4 `[var(--*)]` token-resolution fix

The r106 heat-strip's real-prod witness _surfaced_ (did not introduce) a
PRE-EXISTING, codebase-wide defect: web2 was authored Tailwind-v3-style
using the `prefix-[--token]` arbitrary-CSS-variable shorthand. **Tailwind
v4 removed the implicit `var()` wrap of bare-bracket custom properties**
(authoritative — official v4 upgrade guide via context7
`/tailwindlabs/tailwindcss.com`: _"In v3, CSS variables could be used as
arbitrary values without the `var()` function … v4 changes the syntax to
use parentheses … `bg-[--brand-color]` should be updated to
`bg-(--brand-color)`"_). On this build (`tailwindcss 4.2.4`, CSS-first
`@import "tailwindcss"` + `@tailwindcss/postcss`, no JS config) every
`prefix-[--color-*]` class therefore emitted NO rule and the element fell
back to the cascade — overwhelmingly the inherited `body` colour
(`--color-text-primary` slate-100), transparent backgrounds, absent
borders. The whole muted/secondary text hierarchy and every dimmed
surface/border had been rendering wrong for many rounds (subtle on the
dark theme → unnoticed). This is the r106-flagged dedicated task, not
scope-crept into r106 (calibrated honesty #11). ADR-099 §D-3 Tier 4 IS the
spec — dated append, NO new ADR (doctrine #9 ; the §Impl(r104,r105,r106) /
ADR-104 §Impl(r96) / ADR-105 §Impl(r99,r100) immutable-append precedent).

**R59 inspect-first (doctrine #3 — real shapes, not memory).** Direct
grep+read, no hypothesis layer: the broken form spans **494 occurrences,
10 prefixes** (`text-` 283 · `bg-` 97 · `border-` 84 · `border-l-` 10 ·
`divide-` 9 · `ring-` 4 · `via-`/`to-`/`from-` 2 each · `shadow-` 1),
**44 distinct `--color-*` tokens**, **21 `.tsx` files** under
`app/briefing/` + `components/briefing/`. The `:root` tokens themselves
were never the problem (r104 OKLCH system intact) — only the v3 class
_form_. The codebase already proved the working form **in this exact
deployed build**: the BEFORE Playwright witness found `text-[var(--color-
text-secondary)]` computing to `oklch(0.7446 0.0213 257.49)` (the exact
token) on the live page, while the sibling broken `text-[--color-text-
muted]` computed to `oklch(0.9425 0.0111 243.66)` (slate-100 inherit).

**Decision — `[var(--*)]`, not the v4 `(--*)` paren shorthand.** Both
compile byte-identically. `[var(--x)]` chosen because (1) it is the form
**empirically proven in this exact build** (the witnessed element above ;
the project anti-hallucination doctrine: in-build-proven > docs-theory) ;
(2) it converges the codebase to ONE form (the paren form had zero
occurrences ; adopting it would leave a 2nd coexisting form) ; (3)
mechanically unambiguous, per-file git-reversible, zero new syntax. The
config-shim alternative was rejected (v4 deliberately removed the
auto-`var()`; no restore flag exists per the upgrade guide) and the
base-CSS alternative rejected (defeats the token system; 494-surface).

**What r107 implemented.**

1. **Codemod** `prefix-[--color-X]` → `prefix-[var(--color-X)]` across the
   21 files (`perl -i -pe 's/-\[(--color-[a-z0-9-]+)\]/-[var($1)]/g'`,
   `--color-`-anchored so it cannot touch JS, non-`--color-` design tokens,
   already-correct `[var(…)]`, or the `text-[--color-*]` star-glob in
   prose). Verified: PRE 494 broken / 0 working → POST **0 broken / 494
   working / 0 double-`var(`**. The `/NN` opacity modifiers sit OUTSIDE
   the bracket (no inner-alpha `[--x/40]` form exists) — untouched, and
   now correctly resolve via `color-mix` (e.g. `bg-[var(--color-bg-
surface)]/40`). Applies uniformly in `className=`, cva-style string
   maps, ternaries and helper returns (pure token-shape rewrite).
2. **`BriefingHeader.tsx:88`** — the one element the restore made
   genuinely too-faint (ui-designer Important #1): a `·` separator at
   `text-[var(--color-text-muted)]/50` whose `/50` had been accidentally
   calibrated against the buggy bright-slate inherit ; muted #7A8492 @50%
   over the gradient is near-invisible. Minimal fix: drop `/50` (full
   muted ≈5.3:1, legible, matches its sibling status tokens). No
   structural/aria change (scope discipline).
3. **Three prose corrections** (anti-stale doctrine ; lesson #11 — never
   leave/CREATE a false claim): (a) `globals.css` opacity-modifier comment
   re-stated TRUE — the bare `bg-[--color-*]/N` v3 shorthand emits NO rule
   in v4, the working form is `bg-[var(--color-*)]/N`, with an explicit
   r107 pointer ; (b) `globals.css` tree-shake example `[--color-bull-
deep]` → `[var(--color-bull-deep)]` (the correct reference form) ; (c)
   `CorrelationsStrip.tsx` r106 "broken app-wide / flagged for its own
   round" note → past-tense "fixed codebase-wide in r107", and the one
   codemod-touched glyph comment de-falsified (`text-[var(--color-bg-
base)]` is NOT "broken"). An exhaustive repo scan confirms no other
   stale "the bracket form is broken" prose (the r106 SESSION_LOG + prior
   ADR-099 sections are intentional historical archaeology, untouched).

**Honest non-atomic scope (lesson #11 ; R59 anti-scope-creep).** r107 =
the token-resolution fix + the single restore-introduced faintness
(BriefingHeader:88) ONLY. Three latent issues the restore _surfaced_ but
did NOT introduce are explicitly DEFERRED, flagged not silently fixed:
(i) the WCAG 2.2 §1.4.11 border-α (subtle ≈1.84:1, default ≈2.87:1 < 3:1)
— the **pre-existing** `globals.css` header-§5 recalibration, convergent
across all 3 reviews, now visually live but **not load-bearing** in any
changed surface (assessed: `AssetSwitcher` tabs carry 5 redundant cues,
`EventSurpriseGauge` inactive ring is decorative) ; (ii) the
`SentimentPanel`↔`ScenariosPanel` empty-state text-tier inconsistency (a
cross-panel design-convention decision) ; (iii) `NarrativeBlocks` `/10`
warn-chip faint pill (ui-designer nit, WCAG-OK). Each is its own future
increment.

**Reviews (3 mandatory, parallel, consolidated single pass —
doctrine #14, re-verified on the post-prettier committed shape).**

- **ichor-trader R28 — 0 RED / 0 YELLOW-blocker, GREEN clear-to-merge.**
  ADR-017 boundary intact (pure CSS-class rewrite ; the only `BUY|SELL`
  hits are sanctioned boundary-disclaimer docstrings) ; Voie D/ADR-023
  N/A (zero LLM) ; doctrine #9 / anti-doublon / #3 R59 verified ; zero
  collateral (`\[var\(--(spacing|radius|z-|duration|…)` = 0 — codemod
  correctly `--color-`-scoped) ; the 3 prose corrections verified TRUE
  and not over-claiming. Substantive positive finding: the codemod
  _corrects_ a latent trading-surface degradation — `VerdictBanner`
  `bull`/`bear`/`warn`/conviction were broken no-ops inheriting bright
  slate-100 (semantic colour lost) ; post-fix they resolve to
  emerald/red correctly. One non-blocking YELLOW = deferred-flag the
  pre-existing border-α §1.4.11 (item (i) above) so it is not lost.
- **ui-designer — PROCEED.** The fix restores a coherent, intended
  3-tier hierarchy (primary→titles/values, secondary→prose,
  muted→labels/stamps) consistently applied ; no primary/value wrongly
  de-emphasised ; no `text-[var(--color-bg-*)]`-as-text misuse ; layered
  `bg-[var(--color-bg-base)]/40` insets + same-family gradients restore
  tasteful depth without fighting content. 1 Important applied
  (BriefingHeader:88, item 2) ; the other findings = the pre-existing
  deferred items (i)/(ii)/(iii).
- **accessibility-reviewer (MANDATORY — contrast hierarchy is the whole
  point) — PASS, 0 MUST-FIX / 0 SHOULD-FIX.** Full 1.4.3 matrix computed
  on the ΔsRGB=0 hex equivalents. The contrast _reduction_ vs the buggy
  status quo is real but every realized (token, surface) pair clears AA.
  Worst REAL combo = `text-[var(--color-text-muted)]` on the effective
  `bg-elevated/40` hover surface = **5.01:1** (≥ 4.5:1 normal-text floor,
  margin). Decisive insight: the translucent `/40` pills composite
  _toward_ the darker `--color-bg-base`, so they **raise** effective
  contrast — the "/40 lowers contrast" intuition is false here ; the
  theoretical opaque-`bg-elevated` floor (4.69:1) is **not realized**
  (grep: zero opaque `bg-elevated` panels in the 21 files — only `/40`,
  `/20`, `/30`, `hover:`). `text-secondary` 7.84–8.90:1, `text-tertiary`
  6.17–7.00:1 (unused in scope), `text-neutral` 6.93–7.87:1. 1.4.11
  border-α = ADVISORY/pre-existing/not-load-bearing (item (i)). Zero
  near-invisible token flips. 1.4.1 colour-alone: no regression
  (glyph+sign+text everywhere ; CorrelationsStrip SPEC §14 quintuple
  signal intact).

**Verification (real numbers — measured, not forecast ; lesson #1
forecast≠preuve / #2 SHIPPED≠FUNCTIONAL).**

- **Codemod**: PRE 494 broken `-[--color-*]` / 0 working → POST 0 / 494 /
  0 double-wrap ; residual broken across web2 `.tsx`/`.ts`/`.css` = **0**.
- **Build gate** (final post-prettier shape, doctrine #14):
  `pnpm --filter @ichor/web2` `tsc --noEmit` **0** · `eslint
--max-warnings 0` **0** · vitest **7 files / 95 tests pass** (r106
  baseline — zero regression ; the change is class-string-only, no test
  touches the bracket form) · `next build` **OK** (all routes compiled).
- **Deploy**: `scripts/hetzner/redeploy-web2.sh` (additive, port 3031,
  legacy `ichor-web` 3030 untouched, tunnel NOT restarted → public URL
  stable). RESULT local=200 public=200, `DEPLOY OK`.
- **Real-prod AFTER witness** — Playwright on the deployed public
  dashboard (doctrine #7 zero-exposure ; the stable URL, same as the
  BEFORE witness ; **3 routes**, not forecast):
  - `/briefing/EUR_USD` — the SAME element as the BEFORE witness, "Marché
    américain ouvert" span: class `text-[--color-text-muted]` →
    `text-[var(--color-text-muted)]`, computed colour
    `oklch(0.9425 0.0111 243.66)` (slate-100, WRONG) →
    **`oklch(0.6099 0.0243 256.77)` = `--color-text-muted` exact** ;
    `text-[var(--color-text-secondary)]` → **`oklch(0.7446 0.0213
257.49)` exact** ; the NY-session pill `bg-[var(--color-bg-surface)]
/40` background `rgba(0,0,0,0)` (transparent, WRONG) → **`oklab(0.1831
−0.00356 −0.03069 / 0.4)` = bg-surface @0.4 (resolved)**. Live DOM:
    broken `text-[--color-` 497 → **0** ; working `text-[var(--color-`
    34 → **531**.
  - `/briefing` cockpit (structurally different route): muted
    `0.6099`, secondary `0.7446`, **`text-[var(--color-bull)]`
    `oklch(0.7729 0.1535 163.22)` = emerald exact** (the trading-surface
    semantic ichor-trader flagged, restored) ; 0 broken in DOM.
  - `/briefing/XAU_USD` (2nd asset): muted/secondary exact, bg-surface
    `oklab … /0.4`, **0 broken / 759 working**.
  - **Console**: cold first-load (just-restarted service) showed the
    pre-existing `404 favicon.ico` + a transient
    `link-preload-not-used-within-a-few-seconds` CSS warning ; a warm
    reload = **0 errors / 0 warnings**. The warning was empirically
    confirmed a cold-server-restart timing artifact (a class-string
    codemod cannot affect preload timing ; the CSS chunk content-hash
    change is the EXPECTED recompiled-Tailwind output) — verified, not
    asserted.
  - Full-page screenshots captured for all 3 routes confirm the restored
    premium 3-tier hierarchy gestalt.

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend / zero
migration (alembic still 0050) ; doctrine #9 dated append, no new ADR.

## Implementation (r108, 2026-05-19) — Tier 4 increment 4: the probability ladder onto the r105 `linScale` SSOT

`ScenariosPanel` already renders the Pass-6 7-bucket outcome distribution
(ADR-085) as a diverging probability ladder (bear/base/bull-tinted rows,
`width ∝ p`, skew header, mechanism narrative, ADR-017 boundary docstring).
Tier 4 increment 4 is therefore **not** a visual rebuild — it is the
doctrine-#9 anti-accumulation step the r105 SSOT was explicitly built for:
the ladder's hand-rolled proportional bar-width scalar
`Math.max((s.p / maxP) * 100, 2)` is the THIRD hand-rolled coordinate-math
site (after `VolumePanel`, migrated r105, and `confluence-history` /
`regime-quadrant`, still pending). `lib/microchart.ts:13-15` names
"proportional ladder/heat-strip scalars" as an announced `linScale`
consumer — r108 makes the ladder consume it, validating the r105 foundation
across a SECOND independent consumer (the r105 lesson: a SSOT scoped to one
consumer is a fake-SSOT — proven not-fake here).

**R59 inspect-first (doctrine #3 — the prompt's anticipated trap did NOT
materialize; the design was reshaped by the real shapes, not memory).** The
r106-class SHIPPED≠FUNCTIONAL trap was the prime risk (the resume contract
anticipated an empty `card.scenarios` like r106's empty `{}`
`correlations_snapshot`, and instructed a live `/v1/scenarios/{a}`
fallback). Real-prod Playwright on the deployed dashboard
(`/v1/sessions/{a}?limit=1`) proved **all 5 priority assets carry a fully
populated 7-bucket `card.scenarios`** (EUR_USD `1750e73a` ny_mid,
GBP_USD `c7bdd81c` ny_mid, XAU_USD `96f36fad` pre_londres,
SPX500_USD `f544725b` ny_mid, NAS100_USD `61ee0bea` ny_mid — each
`scenarios.length === 7`, full `{label,p,magnitude_pips,mechanism}`
shape). The ladder is therefore ALREADY functional on every priority
asset via the existing `card.scenarios` path. Independently,
`/v1/scenarios/{a}` was confirmed to return the **shape-incompatible**
`ScenariosResponse.scenarios: ScenarioRow[]` 3-kind
(`continuation`/`reversal`/`sideways`, `probability`, `triggers[]`)
representation — NOT the 7-bucket Pass-6 distribution, and `api.ts`
wires no `getScenarios()` client at all. Bolting it on as a "fallback"
would be both unnecessary (no empty card to fall back from) AND a
data-misrepresentation (a different scenario model rendered as the Pass-6
ladder). **r108 ships NO live fallback** — the calibrated-honesty #11
call: do not add a shape-wrong, unneeded fallback to satisfy a
forecast-trap that the real data disproved (R59 reshape > prompt).

**Decision — consume `linScale`, numerically equivalent to full precision,
NOT bit-identical (disclosed).** `linScale(0, maxP, 0, 100)(p)` evaluates
(by the r105 SSOT's fixed `rangeMin + (v - domainMin) * k` form, with
`k = 100 / maxP`) to `p * (100 / maxP)`, whereas the pre-r108 inline was
`(p / maxP) * 100`. These are the SAME real number but a DIFFERENT IEEE754
multiply order — they agree to ≤ 1 ULP (≤ ~4e-14 absolute on the [0,100]
width domain, far below any sub-pixel / CSS-serialized threshold), they do
NOT agree bit-for-bit. This is precisely the "float-order risk" r105
flagged when it deferred the `bandSeriesPolyline`-atop-`linScale`
re-expression (the I3 item) "to avoid a float-order risk for no r105
consumer" — r108 is the first round with a genuine `linScale`-replaces-an-
existing-inline consumer, so the equivalence is re-proven HERE, at full
double precision, with the multiply-order delta explicitly disclosed
rather than over-claimed as "byte-identical" (lesson #1 forecast≠preuve /
#11 calibrated honesty ; the r105/r106 "byte-identical" precedent does NOT
transfer — those were same-order extractions, this is a scale-primitive
substitution).

**What r108 implemented.**

1. **`ScenariosPanel.tsx`** — `import { linScale } from "@/lib/microchart"`
   ; the scale closure is built ONCE per render
   (`const pWidth = linScale(0, maxP, 0, 100)`, the r106 `divergingStop`
   compose-linScale idiom) ; the per-row scalar becomes
   `Math.max(pWidth(s.p), 2)`. The `Math.max(_, 2)` min-visible-bar clamp
   (a presentation-integrity floor — a tiny-p bucket must still show a
   sliver, the analogue of `bandLayout`'s `Math.max(1, …)` and
   `barFromBaseline`'s `Math.max(minH, h)`) is kept verbatim at the call
   site, NOT folded into a new helper (a 1-line clamp is not accumulation
   — anti-over-extraction, the r96 reconcile-not-blindly lesson ; `pWidth`
   directly consumes the SSOT primitive, no derived module warranted —
   unlike r106 `correlationHeat.ts` whose `divergingStop` was a non-trivial
   signed-offset composition). `maxP = Math.max(…, 0.01)` floor unchanged
   (guarantees `linScale`'s span ≠ 0, so the degenerate-domain branch is
   never hit — equivalent guard).
2. **`__tests__/microchart.test.ts`** — a new describe block proves the
   substitution at the SSOT (the r105 embedded-verbatim idiom): the
   verbatim pre-r108 inline `(p / maxP) * 100` and the end-to-end
   `Math.max(…, 2)` composition are asserted equal to the `linScale`
   form to 9 decimal places (the ≤1-ULP multiply-order delta encoded
   honestly as `toBeCloseTo(_, 9)`, NOT `toBe`), with the exact-equality
   cases (`p = 0`) pinned `===`, across a realistic 7-bucket distribution
   - edges (`p = maxP`, tiny p triggering the clamp, the `maxP = 0.01`
     all-near-zero floor).
3. **Docstring** — the `ScenariosPanel` header records the r108 SSOT
   migration, the doctrine-#9 de-accumulation rationale, the
   numerically-equivalent-not-bit-identical disclosure, and the R59
   finding (card.scenarios populated on all 5 priority assets ⇒ no live
   fallback ; `/v1/scenarios` is the incompatible 3-kind shape).

**Honest non-atomic scope (lesson #11 ; R59 anti-scope-creep).** r108 =
the `linScale` SSOT migration of the ladder's proportional scalar ONLY.
Explicitly DEFERRED, flagged not silently absorbed: (i) **the remaining
Tier 4 SSOT-migration ledger, carried forward in full from r105 — NOT
thinned** (doctrine #11, no deferred item evaporates by omission): the
r105 **I3** `bandSeriesPolyline`-atop-`linScale` re-expression, the
`confluence-history` `xAt/yAt` site, and the `regime-quadrant`
`pathFromHistory` site — each its own future SSOT-migration increment
that MUST re-prove its equivalence at its own gate (the same float-order
discipline applied here). The non-Tier-4 r107-deferred items
(`globals.css` §5 border-α §1.4.11, `NarrativeBlocks` `/10` warn-chip)
are orthogonal to the ladder and remain tracked under §Impl(r107) /
ADR-099 residuals — out of r108 scope, not dropped ; (ii) any visual/structural ladder
redesign (the current ladder is a polished, ADR-017-clean presentation —
a rebuild would be accumulation/regression risk for marginal gain, not an
atomic increment) ; (iii) the `SentimentPanel`↔`ScenariosPanel`
empty-state text-tier inconsistency (the r107-deferred cross-panel
convention decision) — untouched, still its own increment.

**Reviews (consolidated single pass — doctrine #14, re-verified on the
post-prettier committed shape ; accessibility-reviewer N/A-with-reason:
the render is numerically/visually unchanged — no new colour encoding,
no DOM/aria change, the ladder already uses the post-r107 working
`[var(--color-*)]` form — exactly the r105 "byte-identical ⇒ a11y
definitionally unchanged" N/A reasoning ; ichor-trader R28 + ui-designer
mandatory).**

- **ui-designer — APPROVE, 0 Critical / 0 Important / 2 non-blocking
  nits (explicitly NOT applied — defensible per the not-bit-identical
  honesty doctrine + repo float-order-archaeology convention).** The
  once-per-render `pWidth = linScale(0, maxP, 0, 100)` closure + per-row
  `pWidth(s.p)` is confirmed the correct r106 `divergingStop`
  compose-linScale idiom (a declared consumer, not opportunistic reuse).
  Keeping `Math.max(_, 2)` inline confirmed correct: the 2 % min-visible
  clamp is a presentational concern (not coord math), single-call-site —
  extracting it would be the r96 anti-over-extraction anti-pattern, and
  the r105 C1 fake-SSOT lesson cuts the opposite way (`linScale` itself
  is the general primitive ; the clamp is not). Change confirmed
  visually inert (no numerically-equivalent path can cross a sub-pixel
  boundary on a CSS `%` width).
- **ichor-trader R28 — GREEN to merge, 0 RED, 2 YELLOW (both
  doc/comment-only, APPLIED pre-merge).** ADR-017 boundary intact (pure
  presentation refactor, no order/sizing/personalization) ; the
  numerical-honesty framing verified accurate & consistent across
  docstring / ADR / test ("the strongest part of this change —
  correctly refuses the byte-identical precedent and proves the ≤1-ULP
  delta at full precision") ; the math independently re-derived
  (`linScale` → `p*(100/maxP)` vs pre-r108 `(p/maxP)*100`, ≤1 ULP /
  ~1.4e-14 relative at value ≈100, sub-pixel) ; R59 honesty correctly
  scoped (verified-on-current-prod-cards, not "always populated" ;
  empty-state handles legacy `[]`) ; no cross-file drift (grep: zero
  stale production `(p/maxP)*100` outside the deliberately-verbatim
  test `old*` helpers). **YELLOW-1 APPLIED**: the `microchart.ts:13-17`
  citation (3×: docstring, inline comment, this ADR) tightened to
  `microchart.ts:13-15` (the linScale-consumer sentence ends line 15 ;
  16-17 describe `bandSeriesPolyline`/`barFromBaseline`). **YELLOW-2
  APPLIED**: the Deferred (i) reworded into an explicit
  "carried-forward-in-full-from-r105, NOT thinned" Tier 4 SSOT-migration
  ledger (I3 + `confluence-history` + `regime-quadrant`), with the
  non-Tier-4 r107-deferred items explicitly noted as orthogonal /
  still-tracked-under-§Impl(r107) — doctrine #11, no deferred item
  evaporates by omission.
- **accessibility-reviewer — N/A-with-reason (the r105 byte-identical
  precedent for the a11y N/A call).** No new colour encoding, no DOM /
  aria / role change, no contrast change — the ladder already used the
  post-r107 working `[var(--color-*)]` form and the render is
  numerically/visually unchanged (≤1 ULP, sub-pixel). A11y is
  definitionally unchanged ; a full WCAG pass would have been mandatory
  had r108 introduced a new colour/visual encoding (it did not — that
  was r106's heat-strip).

**Verification (real numbers — measured on deployed prod, not
forecast ; lesson #1 forecast≠preuve / #2 SHIPPED≠FUNCTIONAL).**

- **Build gate** (final post-prettier committed shape, doctrine #14 ;
  re-run GREEN after the 2 YELLOW doc fixes):
  `pnpm --filter @ichor/web2` `tsc --noEmit` **0** · `eslint
--max-warnings 0` (ScenariosPanel + microchart.test) **0** · vitest
  **7 files / 105 tests pass** (r107 baseline 95 + the new r108
  `linScale`-consumer describe block 10 = 105 ; zero regression) ·
  `next build` **OK** (all routes compiled).
- **Deploy**: `scripts/hetzner/redeploy-web2.sh` (additive — port 3031,
  legacy `ichor-web` 3030 untouched, tunnel NOT restarted → public URL
  stable). RESULT **local=200 public=200, `DEPLOY OK`** ; ONE
  consolidated SSH (no Step-4 throttle).
- **Real-prod witness** — Playwright on the deployed public dashboard
  (doctrine #7 zero-exposure ; the SHIPPED≠FUNCTIONAL gate — REAL
  7-bucket `card.scenarios` data on REAL priority assets, not a
  forecast), **2 distinct assets / distributions / windows**:
  - `/briefing/EUR_USD` (card `1750e73a`, ny_mid, maxP=0.30): 7 rows
    canonical order ; the new `linScale` path renders the EXACT
    proportional widths — Base `p=0.30` → 100 % (1046/1046 px), Baisse
    modérée `p=0.22` → 73.33 % (767.06 px), Forte baisse `p=0.18` →
    60 % (627.6 px), Crash `p=0.02` → 6.67 % (69.72 px) — every bar
    matches `p·(100/maxP)` to sub-pixel ; tones resolve to exact OKLCH
    (`bear oklch(0.7106 0.1661 22.22)`, `neutral oklch(0.7107 0.0351
256.79)`, `bull oklch(0.7729 0.1535 163.22)` — post-r107 working form,
    r107+r108 together) ; skew header "biais baissier (−14 pts)"
    arithmetically correct (bear 0.42 − bull 0.28).
  - `/briefing/XAU_USD` (card `96f36fad`, pre_londres — different
    window & distribution 2/12/22/34/20/8/2, maxP=0.34): all 7 rendered
    widths match the expected `max(p/maxP·100, 2)` to sub-pixel
    (programmatic check: every row `match:true`) ; skew "−6 pts"
    correct ; exact OKLCH tones.
  - **Console**: warm reload = **0 errors / 0 warnings** (cleaner than
    r107's documented cold-load 404-favicon + transient preload — r108
    introduces nothing ; a class-string-free scalar swap cannot).
  - Element screenshot of the EUR_USD ladder captured (the restored
    premium diverging-ladder gestalt, unchanged).

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend / zero
migration (alembic still 0050) ; doctrine #9 dated append, no new ADR.

## Implementation (r109, 2026-05-19) — Tier 4 increment 5: `confluence-history` `xAt`/`yAt` onto the r105 SSOT

The doctrine-#9 anti-accumulation continues. `microchart.ts:5-15` names
the THREE hand-rolled coord-math sites the r105 SSOT exists to absorb:
`VolumePanel` (migrated r105), `confluence-history` `xAt/yAt`,
`regime-quadrant` `pathFromHistory` — plus the r108 ladder scalar. r109
migrates the **`confluence-history` `xAt/yAt`** site (`app/confluence/
history/page.tsx` `TimelineSvg`), the explicitly-announced `xLinear` +
`linScale` consumer (`microchart.ts:14`: _"the primitive `confluence/
history` xAt/yAt … build on"_). One file, the r108 carried-forward ledger
honoured one increment at a time (lesson #11, NOT thinned).

**R59 inspect-first (doctrine #3 — real shapes, not memory).** Direct
read: `TimelineSvg` is rendered inside a **server component** (`page.tsx`
async, no `"use client"`) — the pure RSC-safe SSOT imports cleanly
(doctrine #5). The hand-rolled math, verbatim:
`xAt = (i) => padX + (i / Math.max(1, n - 1)) * innerW` with
`innerW = w - padX * 2` ; `yAt = (s) => padY + (1 - s / 100) * innerH`
with `innerH = h - padY * 2` ; the path uses `xAt(i).toFixed(1)` /
`yAt(p[key]).toFixed(1)`. The `TimelineSvg` is gated behind
`live && history.n_points >= 2` ⇒ **`n >= 2` is guaranteed** when the
math runs, so `Math.max(1, n - 1) === n - 1` always.

**Decision — `xAt`→`xLinear` is BIT-IDENTICAL ; `yAt`→`linScale` is
numerically-equivalent NOT bit-identical (disclosed) ; `.toFixed(1)`→
`svgCoord` is BIT-IDENTICAL.** (1) `xLinear(i, n, w, padX)` for `n >= 2`
= `padX + (i/(n-1)) * (w - 2*padX)`. `innerW = w - padX*2` and
`w - 2*padX` are bit-identical (IEEE754 multiplication is commutative:
`2*padX === padX*2` exactly), and the gate guarantees
`Math.max(1, n-1) === n-1` — so `xLinear` reproduces `xAt`'s exact
expression and operation order: **bit-identical** (provable `toBe`,
the r105 `VolumePanel` precedent applies cleanly here). (2)
`linScale(0, 100, padY+innerH, padY)(s)` = `(padY+innerH) +
s*(-innerH/100)` (the SSOT's fixed `rangeMin + (v-domainMin)*k` form),
whereas `yAt` = `padY + (1 - s/100)*innerH`. Same real number, different
IEEE754 multiply order → ≤ 1 ULP (sub-pixel on the 110-px viewBox),
**NOT bit-identical** — exactly the r108 / r105-flagged float-order, so
the equivalence is re-proven to full precision and the multiply-order
delta DISCLOSED, the byte-identical precedent refused (lesson #1 / #11 ;
the same discipline r108 set, applied consistently). (3)
`svgCoord(v) === v.toFixed(1)` by definition (`microchart.ts:43-45`,
the single formatting authority) — the path-string formatting is
**bit-identical** and de-accumulates the hand-rolled `.toFixed(1)`.

**What r109 implemented.**

1. **`app/confluence/history/page.tsx`** —
   `import { linScale, svgCoord, xLinear } from "@/lib/microchart"` ;
   `const xAt = (i: number) => xLinear(i, n, w, padX)` ;
   `const yAt = linScale(0, 100, padY + innerH, padY)` (the closure IS
   `yAt` — the r106 `divergingStop` / r108 `pWidth` build-scale-once
   idiom, signature `(s:number)=>number` matches exactly) ; the path
   formatter switches `xAt(i).toFixed(1)` / `yAt(p[key]).toFixed(1)` →
   `svgCoord(xAt(i))` / `svgCoord(yAt(p[key]))` (so the path-string
   coords are **bit-identical for the `xAt` component** and **≤1 ULP
   for the `yAt` component**). The gridline / axis-text / end-circle
   sites pass **raw numeric** `yAt(s)` / `xAt(n-1)` straight to SVG
   attributes (never `.toFixed(1)`-quantized, pre-r109 or post): there
   `xAt(n-1)` is bit-identical and `yAt(s)` is a genuine ≤1-ULP numeric
   shift (sub-pixel on the 110-px viewBox — invisible, but a real
   numeric shift on those decorative elements, NOT a formatting
   no-op ; disclosed for full symmetry with the path claim).
2. **`__tests__/microchart.test.ts`** — a new describe block (the r105/
   r108 embedded-verbatim idiom): the verbatim pre-r109 `oldXAt`
   asserted **`toBe`-exactly-equal** to `xLinear` (bit-identical) and
   the verbatim path formatting `toBe`-equal via `svgCoord`, across the
   real `w=360,h=110,padX=28,padY=6` geometry + `n` ∈ {2, 7, 30} and
   `s` ∈ {0,50,60,100, fractional}; the verbatim `oldYAt` asserted
   `toBeCloseTo(_, 9)` to `linScale` (the ≤1-ULP multiply-order, NOT
   `toBe` — honest), with the analytic exact pinned `toBe` (`s=0` →
   `padY+innerH`).
3. **Docstring** — `page.tsx` `TimelineSvg` records the r109 SSOT
   migration, the bit-identical (`xAt`,`svgCoord`) vs
   numerically-equivalent (`yAt`) split, the doctrine-#9 rationale.

**Honest non-atomic scope (lesson #11 ; carried-forward NOT thinned).**
r109 = the `confluence-history` `xAt/yAt`/format migration ONLY.
Explicitly DEFERRED (the Tier-4 SSOT-migration ledger, still NOT
thinned): (i) `regime-quadrant` `pathFromHistory` → SSOT (the LAST of
the three named hand-rolled sites) ; (ii) the r105 **I3**
`bandSeriesPolyline`-atop-`linScale` re-expression (a `microchart.ts`
internal change re-proving `VolumePanel` equivalence at its gate — a
distinct slice from this consumer migration) ; (iii) the additive NEW
components (sparkline extraction, regime-timeline) — "more coverage"
not "de-accumulation" (doctrine #8 distinction), each its own
increment ; (iv) the non-Tier-4 r107-deferred items (`globals.css` §5
border-α, `NarrativeBlocks` `/10` chip) remain tracked under
§Impl(r107)/residuals.

**Reviews (consolidated single pass — doctrine #14, re-verified on the
post-prettier committed shape ; accessibility-reviewer N/A-with-reason:
no new colour/encoding, no DOM/aria change, render numerically/visually
unchanged [`xAt`/format bit-identical, `yAt` ≤1-ULP sub-pixel] — the
r105/r108 a11y-N/A precedent ; ichor-trader R28 + ui-designer
mandatory).**

- **ui-designer — merge as-is, 0 Critical / 0 Important / 1
  non-blocking nit (explicitly NOT applied — doc density, matches the
  r-annotation precedent).** Confirmed `const yAt = linScale(0, 100,
padY + innerH, padY)` (closure-as-`yAt`) is the exact r108 `pWidth`
  build-scale-once idiom, and `const xAt = (i) => xLinear(i, n, w,
padX)` is the correct thin wrapper (xLinear non-curried ; preserves
  the 4 `xAt(…)` call-site shapes → minimal blast radius). Visually
  inert CONFIRMED (xAt + path-format bit-identical ; yAt ≤1 ULP
  sub-pixel — "no pixel can shift").
- **ichor-trader R28 — Approve for merge, 0 RED, 0 code-change YELLOW.**
  ADR-017 GREEN (score timeline, no order/sizing). The split-honesty
  surface independently re-derived and VERIFIED: (a) `xAt`≡`xLinear`
  bit-identical (the `n≥2` gate ⇒ `Math.max(1,n-1)===n-1` ;
  `2*padX===padX*2` IEEE754-commutative) ; (b) `svgCoord(v)===
v.toFixed(1)` by definition ; (c) `yAt`≡`linScale` ≤1-ULP
  multiply-order, consistently stated across all four surfaces
  (page.tsx docstring + inline comment + this §Impl + the test) ;
  the test uses `toBe` exactly where bit-identical and
  `toBeCloseTo(_,9)` exactly where ≤1-ULP — "no over/under-claim" ;
  the combined-string `toBe` is sound for the enumerated realistic
  inputs (the ".x5-tie" caveat honest, vitest-green empirically). No
  cross-file drift (dead `innerW` removal verified complete ; no other
  consumer ; the `microchart.ts:14` citation accurate). Deferred
  ledger carried forward INTACT vs the r108 append — doctrine #11
  honoured, not thinned. **YELLOW-1 (doc-only, optional) APPLIED**:
  sharpened item 1 to state explicitly that the path-string coords are
  bit-identical-`xAt` + ≤1-ULP-`yAt`, while the gridline/axis-text/
  end-circle sites pass RAW numeric `yAt(s)` (never `.toFixed(1)`-
  quantized) where the `yAt` ≤1-ULP delta is a genuine sub-pixel
  numeric shift on decorative elements, NOT a formatting no-op — full
  symmetry with the path claim (the witness empirically confirmed
  this: end-circle `cy` rendered as raw `54.216` / `53.333999…`, the
  path as 1-dp `svgCoord`).
- **accessibility-reviewer — N/A-with-reason** (the r105/r108
  byte-identical a11y-N/A precedent): no new colour/encoding, no
  DOM/aria change (the `<svg role="img" aria-label>` unchanged), the
  render is numerically/visually unchanged (xAt/format bit-identical,
  yAt ≤1-ULP sub-pixel). A11y definitionally unchanged.

**Verification (real numbers — measured on deployed prod, not
forecast ; the SHIPPED≠FUNCTIONAL gate satisfied).**

- **SHIPPED≠FUNCTIONAL pre-check** (live prod `/v1/confluence/{a}/
history?window_days=30`): ALL 8 assets `n_points = 61` (≥ 2, valid
  `{score_long,score_short,captured_at}`, 30-day window) — every
  `TimelineSvg` renders real data (no r106-class empty-upstream trap).
- **Build gate** (final post-prettier shape, doctrine #14 — re-GREEN
  after the dead-`innerW` removal that unblocked eslint, and after the
  YELLOW-1 markdown-only edit which is build-inert): `tsc --noEmit`
  **0** · `eslint --max-warnings 0` **0** · vitest **7 files / 111
  tests pass** (r108 baseline 105 + the new r109 describe block 6 =
  111 ; zero regression) · `next build` **OK**.
- **Deploy**: `scripts/hetzner/redeploy-web2.sh` (additive — port
  3031, legacy `ichor-web` 3030 + tunnel untouched → URL stable).
  RESULT **local=200 public=200, `DEPLOY OK`** ; ONE consolidated SSH.
- **Real-prod witness** — Playwright on the deployed public dashboard
  `/confluence/history` (doctrine #7 zero-exposure ; REAL data, REAL
  assets, not a forecast), **8/8 asset cards rendered**, the migrated
  `xLinear`/`linScale`/`svgCoord` coords arithmetically cross-checked
  on EUR_USD (score_long path): `M28.0 51.1` — `xAt(0)=xLinear(0,61,
360,28)=28.0` ✓, `xAt(1)=28+(1/60)·304=33.067→"33.1"` ✓,
  `xAt(60)=332.0` ✓ ; `yAt(54)=linScale(0,100,104,6)(54)=104−52.92=
51.08→"51.1"` ✓ ; **every path coord exactly 1-dp** (122 coords =
  61 pts × 2 ; `svgCoord≡.toFixed(1)` proven live), all in-viewBox
  (x∈[28,332], y∈[50.5,55] within [6,104]). End-circles render RAW
  numeric `cy=54.216 / 53.333999999999996` (the YELLOW-1 decorative
  raw-numeric path, empirically confirmed). **Console: warm load
  0 errors / 0 warnings**. Full-page screenshot captured (8 timelines,
  premium gestalt unchanged).

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend / zero
migration (alembic still 0050) ; doctrine #9 dated append, no new ADR.

## Implementation (r110, 2026-05-19) — Tier 4: R59 reclassification — the doctrine-#9 coord-scaling _consumer-migration_ de-accumulation is COMPLETE at r109 (`pathFromHistory` mis-flagged, disproved ; the I3 SSOT-internal item still remains — doctrine-#9 is NOT fully closed)

The r109-close binding default was "continue the Tier-4 SSOT-migration
ledger — `regime-quadrant` `pathFromHistory` → SSOT (the LAST of the 3
named hand-rolled sites)". **R59 inspect-first disproved the default's
premise** (doctrine #2 never-act-on-a-guess + #3 R59-reshapes-the-design
— the r67-class pattern: a prior round's "migration target" flag is a
HYPOTHESIS, verified against the real code before acting, and here
falsified — exactly as r67 disproved r66's gamma_flip proxy-scaling
guess).

**The disproof (real code, `components/ui/regime-quadrant.tsx:56-59`).**
`pathFromHistory(history: {x,y}[])` is, verbatim:
`history.map((p, i) => `${i===0?"M":"L"}${p.x},${-p.y}`).join(" ")`.
This is a trivial point-list→SVG-path serializer with a Y-flip and
**NO domain→range scaling and NO `.toFixed` formatting**. Its input
`{x,y}` is ALREADY in viewBox units — `position`/`history` are each in
`[-1, 1]` (line 26/30) and the SVG is `viewBox="-1.15 -1.15 2.3 2.3"`,
i.e. data coords ARE SVG coords 1:1 (only the y-axis flipped because
SVG +y is down vs the macro +inflation-up convention). It is exactly
consistent with how the rest of the component plots — the current-
position circle is the unscaled `cx={position.x} cy={-position.y}`
(line 159-160). Therefore `pathFromHistory` is **NOT a band/linear-
scaling reinvention** in the class of `VolumePanel` (slot/volH) or
`confluence-history` (xAt/yAt) — the two genuine coord-scaling
accumulation sites, migrated r105 and r109. The `microchart.ts:5-11`
"WHY THIS MODULE EXISTS" paragraph that listed it as one of "three
places … each reinventing band/linear scaling … the remaining two
sites follow" and the `regime-quadrant.tsx:14-17` self-comment
("pathFromHistory is a flagged migration target") were **speculative
mis-flags** (added r105 without inspecting pathFromHistory's
triviality), now corrected. R59 breadth: every live consumer
(`/macro-pulse`, `/`, `/sessions/[asset]`, `/learn/regime-quadrant`)
mounts `<RegimeQuadrant … />` WITHOUT a `history` prop, so the
`{history && history.length > 1}` trail path is largely non-rendered —
"migrating" it would consolidate near-dead code at a regression risk
for zero observable value.

**Why forcing the migration would be WRONG (not merely unnecessary).**
(a) `svgCoord` (= `.toFixed(1)`) on these coords would round to 0.1
viewBox-unit ≈ 14 px on the 320 px hero — a **visible quantization
regression** of the history trail (not the sub-pixel ≤1-ULP of
r108/r109). (b) Routing the `-p.y` Y-flip through
`linScale(0, 1, 0, -1)` (which does evaluate to `-v`) would be an
**absurd over-abstraction** — a sign flip is not a "linear scale";
it would reduce clarity, the inverse of the project mandate ("code
lisible > code clever", YAGNI, the r96 reconcile-not-blindly /
anti-over-extraction lesson). The honest move is to correct the
ledger, not to manufacture code motion.

**What r110 implemented (doc/comment-only — no behavioural code).**

1. **`apps/web2/lib/microchart.ts:5-11`** — the "WHY THIS MODULE
   EXISTS" doctrine-#9 paragraph rewritten to the R59-verified truth:
   the accumulation was the band/linear-scaling reinventions in
   `VolumePanel` (slot/volH, migrated r105 byte-identical) and
   `confluence-history` (xAt/yAt, migrated r109 — `xAt`/`svgCoord`
   bit-identical, `yAt` ≤1-ULP) ; `regime-quadrant`'s `pathFromHistory`
   was originally listed but r110's R59 inspection found it does NO
   scaling/formatting (raw viewBox-unit passthrough + y-flip) — NOT a
   scaling-accumulation site. The coord-scaling _consumer-migration_
   de-accumulation is **COMPLETE at r109** (the SSOT-internal I3
   remains ; doctrine-#9 is NOT fully closed).
2. **`apps/web2/components/ui/regime-quadrant.tsx:14-17`** — the
   self-comment de-flagged: `pathFromHistory` is NOT a microchart-SSOT
   target (R59 r110 — raw viewBox-unit passthrough, no scale/format,
   consistent with the unscaled position circle ; the d3 foreclosure
   note retained).
3. **ADR-099 `## Implementation (r110, 2026-05-19)`** (this) — the
   reclassification of record, with the disproof.

**Honest non-atomic scope / ledger (carried-forward NOT thinned,
#11 — re-scoped to the R59 truth).** The doctrine-#9 _coord-scaling
consumer-migration_ de-accumulation is DONE (r105 VolumePanel + r108
ScenariosPanel scalar + r109 confluence-history ; pathFromHistory
reclassified out with proof) — but doctrine-#9 is **NOT fully closed**:
the SSOT-internal I3 remains. The remaining genuine SSOT items, in
order: (i) the r105
**I3** — `bandSeriesPolyline` should compose `linScale` internally
(currently it hand-rolls `(v-min)/span` min..max normalization ; a
real SSOT-internal change, float-order-sensitive, r105-deferred-with-
explicit-reason — the genuine **r111 default**, deserving a fresh
non-degraded session) ; (ii) additive NEW components — sparkline
extraction, regime-timeline — "more coverage" not "de-accumulation"
(doctrine #8 distinction) ; (iii) the non-Tier-4 r107-deferred items
(`globals.css` §5 border-α, `NarrativeBlocks` `/10` chip) — tracked
under §Impl(r107)/residuals. Nothing dropped.

**Reviews (consolidated single pass — doctrine #14 ; ui-designer +
accessibility-reviewer N/A-with-reason: ZERO render / DOM / aria /
behavioural change — pure source comments + ADR/SESSION_LOG ;
ichor-trader R28 mandatory — the high-scrutiny risk here is
OVER-CLAIMING the reclassification / thinning the ledger).**

- **ichor-trader R28 — GREEN, merge, 0 RED.** Adversarial pass
  ("honest, or work-avoidance?"): the disproof independently
  re-verified against the real `regime-quadrant.tsx:56-59` /
  viewBox / unscaled position circle — "a legitimate r67-class
  disproof, NOT work-avoidance" ; the "svgCoord quantizes ≈13.9 px"
  arithmetic and the "linScale(0,1,0,-1) over-abstraction" reasoning
  confirmed correct ; the ledger diffed r109 §Impl(r109) deferred
  (4 items) vs r110 carry-forward — **all four accounted for,
  doctrine #11 honoured, nothing evaporated** ; no microchart.ts
  internal contradiction ; no cross-file drift (only the 2 rewritten
  sites asserted the stale flag, now mutually consistent) ;
  doctrine #9 dated-§Impl + #14 deploy-N/A-with-reason judged
  **honest** (build-inert, vitest 7f/111t-unchanged IS the proof).
  **YELLOW-1 (doc-only, non-blocking) APPLIED**: sharpened the
  "COMPLETE at r109" assertions (the §Impl title + the "what
  implemented" item + the ledger line + the `microchart.ts` comment)
  to "coord-scaling **consumer-migration** de-accumulation … but
  doctrine-#9 is NOT fully closed: the SSOT-internal I3 remains" —
  prevents a skim-reader misreading doctrine-#9 as fully closed,
  applied at every occurrence (the class, not just the headline).
- **ui-designer / accessibility-reviewer — N/A-with-reason (NOT
  dispatched — anti-FOMO subagent discipline, lesson #17).** Zero
  render / DOM / JSX / aria / behavioural change — pure source block
  comments + ADR/SESSION_LOG. The byte-identical compiled bundle
  (comments stripped) + `vitest 7f/111t` unchanged vs r109 prove the
  render is definitionally untouched ; dispatching a UI/a11y review
  of a comment diff would be FOMO subagent use, not protocol.

**Verification (doc/comment-only ⇒ build-inert — the build gate IS the
verification ; deploy + witness N/A-with-reason, honestly stated).**

- **Build gate** (final post-YELLOW committed shape, doctrine #14):
  `tsc --noEmit` **0** · `eslint --max-warnings 0` (microchart.ts +
  regime-quadrant.tsx) **0** · vitest **7 files / 111 tests**
  (IDENTICAL to r109 — zero delta proves the comment-only change is
  behaviourally inert ; `microchart.test.ts` never referenced
  `pathFromHistory`) · `next build` inert by the compiler-
  strips-comments invariant (GREEN on the prior comment-shape ; a
  further comment-text delta cannot alter the bundle). `git diff
--stat` = exactly **3 files, 0 lines in `__tests__`/`*.test.*`/
  `*.py`** (the ichor-trader build-inert probe satisfied).
- **Deploy / real-prod witness — N/A-with-reason.** A pure
  source-comment + ADR/SESSION_LOG change produces a byte-identical
  `next build` bundle ⇒ ZERO prod behaviour change ⇒ nothing new to
  witness (a witness would render the IDENTICAL r109
  confluence-history/VolumePanel/regime-quadrant, proving nothing).
  The r97 doc/infra-hygiene CI-only precedent ; faking a witness for
  a comment change would violate calibrated-honesty #11. Voie D +
  ADR-017 N/A (no signal/order/SDK surface ; `microchart.ts:45`
  self-attests "ADR-017 N/A: pure geometry"). LIVE state unchanged:
  HEAD will be the r110 commit, alembic 0050, dashboard stable.

Voie D + ADR-017 held ; web2-only doc/comment + ADR ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR.

## Implementation (r111, 2026-05-19) — Tier 4: the r105 **I3** — `bandSeriesPolyline` composes `linScale` internally (the SOLE remaining SSOT-internal doctrine-#9 item ; raw ≤1-ULP multiply-order, formatted-string bit-identical — disclosed, not flattened)

r110 reclassified the doctrine-#9 ledger to its R59-verified truth: the
coord-scaling _consumer-migration_ de-accumulation is COMPLETE at r109
(`VolumePanel` r105 + `ScenariosPanel` scalar r108 + `confluence-history`
r109 ; `pathFromHistory` reclassified out with proof), **but doctrine-#9
is NOT fully closed — the SSOT-internal I3 remains**. r111 closes it.
This is the explicitly-r105-deferred item, not a consumer migration: a
`microchart.ts`-internal re-expression of `bandSeriesPolyline`'s own
hand-rolled `(v - min) / span` min..max normalization onto the SSOT's
`linScale` primitive, re-proving its **sole** consumer (`VolumePanel`)
at the gate. r105's docstring deferred this verbatim — _"re-expressing
it atop `linScale` is deferred … to avoid a float-order risk for no
r105 consumer"_ — r111 is the round that pays that risk down honestly.

**R59 inspect-first (doctrine #2/#3 — real shapes + the meta-r110
warning that the default itself is R59-subject).** Direct verbatim
reads: `microchart.ts:162-178` (`bandSeriesPolyline` — `min =
Math.min(...values) ; span = Math.max(...values) - min || 1 ; y =
plotH - ((v-min)/span)*(plotH*headFrac) - plotH*footFrac`, headFrac
0.78 / footFrac 0.11) ; `components/briefing/VolumePanel.tsx:87` (the
**SOLE** consumer — `bandSeriesPolyline(closes, slot, volH)`,
`closes = usable.map(b => b.close)`, `volH = 132`, defaults) ;
`__tests__/microchart.test.ts:43-57` (verbatim pre-r105 `oldPricePts`)

- `:116-120` (the formatted-string `bandSeriesPolyline(...).toBe(
oldPricePts(...))` across 3 fixtures). R59 result: I3 **is a genuine
  linear-normalization site** (`(v-min)/span` IS a domain→[0,1] linear
  scale) — NOT disproved like r110's `pathFromHistory`. The default
  holds ; the meta-r110 R59-subject check was run and passed (I3 is real,
  not a forced/over-abstracted migration — `bandSeriesPolyline` already
  DOES the exact `linScale` arithmetic, just hand-rolled).

**Empirical float-order computed BEFORE coding (deterministic Node, the
real IEEE754 behaviour — never assumed).** Two candidate compositions
were evaluated against the verbatim pre-r111 `(v-min)/span`, on the 3
test fixtures (`realistic` n=7 price-scale, `minimalTwo` n=2 span‖1
fallback, `bigValues` n=3): **A** = `linScale(min, min+span, 0, 1)(v)`
(the r105-documented algebra, `microchart.ts:159-161`) ; **B** =
`linScale(0, span, 0, 1)(v - min)` (the r108/r109 0-anchored idiom).
Findings: (1) **`(min+span) - min === span` holds for ALL VolumePanel
fixtures** (price magnitudes ~1…~5000 vs spans ~1e-3…~3e2) ⇒ A and B
are **numerically identical** for the only consumer — no gratuitous
domain-recompute divergence ; the choice is principle, not numerics.
(2) raw normalized value vs `(v-min)/span` = **NOT bit-identical**
(`realistic` maxΔ = 2.776e-17 ≪ 1 ULP at the [0,1] scale ; `minimalTwo`/
`bigValues` coincidentally 0Δ) — the **multiply-order ≤1-ULP class,
exactly r108/r109** (`(v-min)*(1/span)` vs `(v-min)/span`, the second
rounding). (3) the **`svgCoord`-formatted `bandSeriesPolyline` string
is BIT-IDENTICAL** to the verbatim pre-r111 `oldPricePts` for all 3
fixtures (the ≤1-ULP raw delta × `plotH*headFrac` ≈ ×103 ≈ 3e-15 px
cannot cross a `.toFixed(1)` 0.1 boundary except on an exact `.x5`
tie — none in the fixtures) — **exactly the r109 path-format situation**:
the existing `microchart.test.ts:116-120` `toBe` STAYS GREEN, no
reclassification of that assertion.

**Decision — compose `linScale(min, min + span, 0, 1)` (candidate A,
the r105-documented algebra), raw ≤1-ULP NOT bit-identical (disclosed),
formatted-string bit-identical (re-pinned).** A is chosen over B: it is
the literal r105-documented decomposition (`microchart.ts:159-161` and
the r110 ledger both state _"the `(v-min)/span` is `linScale(min,
min+span, 0, 1)`"_), it is self-documenting (the domain IS the value
range `[min, min+span]`, no pre-centering trick a reader must decode),
and the empirical computation proved it introduces **no** divergence
beyond the unavoidable multiply-order (`(min+span)-min===span` for
every VolumePanel-class input — B's only theoretical advantage does not
materialize for the sole consumer). This is R59-confirmed by empirical
measurement, not blind trust of the prompt's literal target ; the
alternative B was evaluated and recorded for split-honesty completeness
(not silently dropped). The substitution is the SAME real number in a
DIFFERENT IEEE754 multiply order → ≤1 ULP ; the byte-identical
precedent is **refused** (the r108/r109 discipline, lesson #1/#9/#11) ;
the raw equivalence is proven to full precision (`toBeCloseTo(_, 9)`)
and the multiply-order DISCLOSED in docstring + test + this §Impl ; the
formatted-string bit-identity is separately re-pinned `toBe` (the
honest split — never flattened to one label, the r109 lesson).

**What r111 implements.**

1. **`apps/web2/lib/microchart.ts` `bandSeriesPolyline`** — a single
   `const norm = linScale(min, min + span, 0, 1)` (the build-scale-once
   idiom — r106 `divergingStop` / r108 `pWidth` / r109 `yAt`), then
   `y = plotH - norm(v) * (plotH * headFrac) - plotH * footFrac`. The
   `min`/`span` (incl. the `|| 1` fallback) computation is unchanged
   byte-for-byte ; only `(v - min) / span` → `norm(v)`. The function
   docstring's r105 deferral paragraph (_"r105 keeps this implementation
   exactly as `VolumePanel` had it inline … re-expressing it atop
   `linScale` is deferred … to avoid a float-order risk for no r105
   consumer"_) is rewritten to the r111 truth: it now composes `linScale`
   internally ; the raw normalized value is **≤1-ULP multiply-order**
   vs the pre-r111 `(v-min)/span` (NOT bit-identical, disclosed) ; the
   `svgCoord`-formatted polyline string stays **bit-identical** for
   VolumePanel-class data (the ≤1-ULP delta cannot cross a 1-dp
   boundary except on an exact `.x5` tie).
2. **`apps/web2/lib/microchart.ts:5-24`** — the "WHY THIS MODULE
   EXISTS" doctrine-#9 paragraph: the r110 line _"the one remaining
   SSOT-internal item is the r105 **I3** (`bandSeriesPolyline`
   composing `linScale`, below)"_ → **r111 closed it**. The doctrine-#9
   de-accumulation (coord-scaling consumer-migration COMPLETE at r109 +
   the SSOT-internal I3 COMPLETE at r111) is now **FULLY CLOSED**. The
   remaining Tier-4 is additive NEW components (sparkline / regime-
   timeline) — "more coverage" not "de-accumulation" (doctrine #8).
3. **`apps/web2/__tests__/microchart.test.ts`** — a NEW describe block
   (the r105/r108/r109 embedded-verbatim idiom) "bandSeriesPolyline
   composes linScale internally (r111 I3)": (a) the verbatim pre-r111
   `(v-min)/span` normalizer asserted `toBeCloseTo(_, 9)` vs
   `linScale(min, min+span, 0, 1)` across the 3 fixtures (the ≤1-ULP
   multiply-order — NOT `toBe`, honest) ; (b) the analytic exact pinned
   `toBe` (`v = min` → exactly `0` ; no multiply-order at the domain
   origin — the r109 `s=0` precedent) ; (c) the FULL formatted
   `bandSeriesPolyline` string re-pinned `toBe`-equal to the verbatim
   `oldPricePts` for the 3 fixtures (the split-honesty record: raw
   ≤1-ULP, formatted string bit-identical — the r109 path-format
   precedent stated explicitly, not implied) ; the pre-existing
   `:116-120` block is unchanged and stays GREEN (zero regression).

**Honest non-atomic scope (lesson #11 ; carried-forward NOT thinned).**
r111 = the I3 SSOT-internal re-expression ONLY. With I3 closed, the
doctrine-#9 de-accumulation is **FULLY CLOSED** (coord-scaling
consumer-migration r105+r108+r109 ; SSOT-internal I3 r111). Remaining
Tier-4, explicitly NOT thinned: (i) additive NEW components — sparkline
extraction (the `VolumePanel` price polyline as a reusable
`<Sparkline>`), regime-timeline (NEW, reusing `regime-quadrant`
`RegimeId`/`QUADRANTS` colour map) — "more coverage" not
"de-accumulation" (doctrine #8 distinction), each its own increment ;
(ii) T4.2 (uncertainty band / calibration overlay / degraded+empty
states / `prefers-reduced-motion` / no-truncated-axis audit) ; (iii)
T4.3 (responsive / mobile) ; (iv) the non-Tier-4 r107-deferred items
(`globals.css` §5 border-α, `NarrativeBlocks` `/10` chip) — tracked
under §Impl(r107)/residuals. Nothing dropped.

**Reviews (consolidated single pass — doctrine #14, re-verified on the
post-prettier committed shape ; ui-designer + accessibility-reviewer
N/A-with-reason: the `svgCoord`-formatted polyline is bit-identical for
the fixtures and ≤1-ULP sub-pixel for live data — zero render / DOM /
aria change, no new encoding, the r105/r108/r109/r110 a11y/ui-N/A
precedent + anti-FOMO #17 ; ichor-trader R28 mandatory — the
high-scrutiny risk is OVER-CLAIMING the float-order or a cross-file
drift in the sole-consumer re-proof).**

- **ichor-trader R28 — GREEN, merge, 0 RED, 0 YELLOW-requiring-
  application (the actual adversarial verdict, not a forecast — lesson
  #1).** Adversarial float-order pass, the disclosure surface
  independently re-derived and VERIFIED — (a) the raw normalized value
  is ≤1-ULP multiply-order `(v-min)*(1/span)` vs `(v-min)/span`, NOT
  bit-identical (the `realistic` fixture maxΔ=2.776e-17 reproduced) ;
  (b) `(min+span)-min===span` confirmed for all VolumePanel-class
  inputs ⇒ candidate A introduces no divergence beyond multiply-order
  (B-vs-A recorded, not silently dropped — split-honesty intact) ;
  (c) the `svgCoord`-formatted string is bit-identical for the 3
  fixtures (the ≤1-ULP × ~103 px cannot cross a 1-dp boundary, the
  `.x5`-tie caveat honest, vitest-green empirically) ; the test uses
  `toBeCloseTo(_,9)` exactly where ≤1-ULP and `toBe` exactly where
  bit-identical (formatted string + the `v=min` analytic exact) — "no
  over/under-claim, the r108/r109 discipline applied consistently".
  No cross-file drift: `VolumePanel` is the SOLE non-test consumer
  (grep-verified — `VolumePanel.tsx:87`), unchanged ; `min`/`span`/
  `|| 1` byte-identical ; the `VolumePanel.tsx:77-79` "byte-identical
  to pre-r105 inline math" comment **remains TRUE** (it scopes the
  _formatted rendered attributes_, which stay bit-identical — NOT the
  raw norm ; explicitly judged NOT a lesson-#5 drift) ; the docstring +
  the `microchart.ts:5-24` paragraph + this §Impl + the test state the
  SAME ≤1-ULP-raw / bit-identical-formatted split consistently across
  all four surfaces. Deferred ledger diffed vs r110 carry-forward —
  all items accounted for, doctrine #11 honoured, "FULLY CLOSED"
  scoped precisely to doctrine-#9 de-accumulation (NOT all of Tier-4 —
  additive NEW + T4.2/T4.3 + the r107 residuals explicitly remain).
  meta-r110 confirmed: the "continue I3" default WAS R59-checked (I3 a
  genuine `(v-min)/span` linear-normalization site, NOT disproved like
  r110's `pathFromHistory`). ADR-017 N/A (pure geometry, no
  bias/order). The candidate-**B** audit trail
  (`linScale(0, span, 0, 1)(v-min)` empirically identical to A for the
  sole consumer, with the self-guarding `min+span-min===span`
  precondition asserted before the `toBe`) was **proactively included**
  in the docstring + test + this §Impl (NOT a review-driven fix) — the
  reviewer judged it **"exemplary, exceeds the r108/r109 bar"**, so
  ZERO YELLOW required application. One minor no-action observation:
  the ADR "× `plotH*headFrac` ≈ ×103" arithmetic
  (`132*0.78 = 102.96 ≈ 103`) and the ≈3e-15 px figure independently
  re-confirmed correct.
- **ui-designer / accessibility-reviewer — N/A-with-reason (NOT
  dispatched — anti-FOMO subagent discipline, lesson #17).** The
  `bandSeriesPolyline` output is the `<polyline points>` string ;
  bit-identical for the test fixtures and ≤1-ULP (sub-pixel, far below
  the `svgCoord` 0.1 quantization) for live data ⇒ the rendered SVG
  is numerically/visually unchanged, no new colour/encoding, no
  DOM/aria change (`<svg role="img" aria-label>` untouched). The
  r105 (byte-identical) / r108 / r109 (≤1-ULP sub-pixel) a11y/ui-N/A
  precedent applies cleanly ; dispatching a UI/a11y review of a
  visually-inert numeric refactor would be FOMO, not protocol.

**Verification (real numbers — measured on deployed prod, not forecast ;
the SHIPPED≠FUNCTIONAL gate satisfied).**

- **SHIPPED≠FUNCTIONAL pre-check** (live prod
  `/v1/market/intraday/EUR_USD`, R53 at R59-time): **479 bars, all
  479 usable** (numeric `volume >= 0`), `close` field present
  (~1.164) ⇒ `VolumePanel` renders the `bandSeriesPolyline`
  close-price polyline from REAL data on a REAL asset (no r106-class
  empty-upstream trap ; the sole consumer is genuinely functional).
  At deploy-time the intraday window had rolled to **90 usable bars**
  (the live feed is time-varying — both ≥2, both functional ; honest,
  not the same snapshot as the R59-time precheck).
- **Build gate** (final post-prettier shape, doctrine #14): `tsc
--noEmit` **0** · `eslint --max-warnings 0` (microchart.ts +
  microchart.test.ts) **0** · vitest **7 files / 119 tests pass**
  (r109/r110 baseline 111 + the new r111 describe block 8 = 119 ;
  zero regression — the pre-existing `:116-120` string `toBe` stays
  GREEN, the formatted polyline still bit-identical) · `next build`
  **OK**.
- **Deploy**: `scripts/hetzner/redeploy-web2.sh` (additive — port
  3031, legacy `ichor-web` 3030 + tunnel untouched). RESULT
  **`local=200 public=200`, `DEPLOY OK`** ; LIVE URL **stable**
  `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel NOT restarted, unchanged vs r110). No SSH throttle (Step
  1-5 clean single pass).
- **Real-prod witness** — Playwright on the deployed public dashboard
  `/briefing/EUR_USD` (doctrine #7 zero-exposure ; REAL data, REAL
  asset, not a forecast). **The r111 surface is GREEN**: the
  `VolumePanel` close-price `<polyline>` renders from the 90 live
  bars (viewBox `0 0 640 150`, 1 polyline / 90 points / 90 bar rects),
  **every coordinate well-formed 1-dp via `svgCoord`** (`allOneDp`
  true — the ≤1-ULP-raw / bit-identical-formatted prediction
  CONFIRMED on real live data), all in-viewBox, the band-x
  arithmetic cross-checked EXACT (`x[0]=slot/2=3.6`, `x[1]=10.7`,
  `x[89]=636.4` — unchanged by r111), the y-values inside the exact
  head/foot-padded band ([14.5, 117.5] ⊂ the `headFrac`/`footFrac`
  envelope). Screenshot captured. **Honest console scoping (lesson
  #11 / r106-a — NOT over-claimed 0/0)**: the page carries
  **PRE-EXISTING, app-wide console errors that r111 did NOT
  introduce** and that are OUT OF SCOPE for this pure-geometry
  increment — proven, not assumed: (a) `/briefing/[asset]` shows
  9× `TypeError: e[o] is not a function` in **Next vendor chunks
  `5889`/`7985`** (NOT `microchart`), **asset-agnostic** (EUR_USD 9
  ≡ XAU_USD 9 — independent of the per-asset close prices the r111
  math touches), while the r111-changed `VolumePanel` polyline
  renders perfectly (if `norm` were not a function the `.map()`
  would throw and the polyline would be absent — it is present and
  correct) ; (b) the `/` landing (ZERO `VolumePanel`/`microchart`
  consumer) carries a DIFFERENT pre-existing set (8× CSP
  `localhost:8001` dev-artifact + 1× minified React #418
  hydration) ; (c) r111's 3-file diff is pure-geometry +
  test + ADR, vitest-119-GREEN — it cannot emit a vendor-chunk
  `TypeError`. These pre-existing defects are **flagged for a
  dedicated out-of-scope task (flag-not-fix, lesson #11 — NOT fixed
  here, NOT claimed clean)** ; the r111 witness GREEN is for the
  r111 surface only (the polyline render correctness on real data),
  honestly scoped.

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR. **doctrine-#9 de-accumulation FULLY CLOSED at r111** (coord-scaling
consumer-migration r105+r108+r109 + SSOT-internal I3 r111) ; remaining
Tier-4 = additive NEW (sparkline / regime-timeline, doctrine #8) →
T4.2 → T4.3.

## Implementation (r112, 2026-05-19) — Tier 4: additive NEW `<Sparkline>` — a point-to-point intraday price micro-trend on the r105 `xLinear`+`linScale` SSOT (the announced linear consumers ; doctrine #8 "more coverage", NOT de-accumulation ; R59 RESHAPED the literal default)

doctrine-#9 de-accumulation closed at r111. r112 is the first **additive
NEW** Tier-4 increment (doctrine #8 "more coverage" — a NEW component +
a NEW genuine consumer of the SSOT's linear primitives, NOT a migration
of existing math).

**R59 inspect-first RESHAPED the literal default (meta-r110 — the
default is itself a HYPOTHESIS).** The r111-close binding default was
"r112 = additive `<Sparkline>` — extract the `VolumePanel` close-price
polyline as a reusable `<Sparkline>`". A read-only researcher R59 +
direct orchestrator verification of the real code **disproved the
literal wording** (the r109-class reshape, not the r110-class full
disproof): `VolumePanel`'s close-price polyline is
`bandSeriesPolyline(closes, slot, volH)` (`VolumePanel.tsx:87`) where
`slot` is the **same categorical band the volume bars use**
(`bandLayout(n, W)`, `VolumePanel.tsx:85`) — x is the band-column
centre `i*slot + slot/2` (`microchart.ts:200`) with volume-overlay
head/foot padding (`headFrac 0.78` / `footFrac 0.11`,
`microchart.ts:188-205`). The SSOT's OWN docstring
(`microchart.ts:154-159`) states it explicitly: _"`bandSeriesPolyline`
— **band**-positioned x … NOT linear … a point-to-point linear
polyline must compose `xLinear` + `linScale`, NOT this."_ Extracting it
verbatim would yield a **band-coupled fake** (the r105 fake-SSOT lesson
one layer up) AND duplicate a series already on screen (the same
intraday closes `VolumePanel` already renders) — zero value, violating
the anti-accumulation spirit. R59 therefore RESHAPES: the genuine
increment is a **NEW point-to-point `<Sparkline>` composing `xLinear`
(`microchart.ts:87-90`) + `linScale` (`microchart.ts:72-82`) +
`svgCoord` (`microchart.ts:63-65`)** — precisely the consumers the SSOT
docstring already names as intended (`microchart.ts:34,69` "the
sparkline"), validating that r105's ui-designer C1 fix (which added
`linScale`/`xLinear`) was not speculative.

**R59 verified consumption site + real populated data (the #1
doctrine — projected AND populated, not type-only).** The only
per-asset numeric time-series the `/briefing/[asset]` page already
fetches AND that is empirically populated is the intraday closes:
`page.tsx:128` `getIntradayBars(...)`, `page.tsx:189`
`const recentBars: IntradayBarOut[] = intraday ? intraday.slice(-90)
: []`, `IntradayBarOut.close: number` — the SAME series `VolumePanel`
renders (`page.tsx:383`), empirically witnessed populated on real
assets at r111 (90 live bars, EUR_USD). The card enrichment fields
(`scenarios`/`calibration`/`confluence_drivers`/`thesis`) are
type-only-often-empty (`api.ts:210-238`, MEMORY r106/r108) and
confluence-history is real but NOT wired to the briefing page (a
different increment) — choosing the intraday closes **avoids the
SHIPPED≠FUNCTIONAL trap by construction** (the data is the proven-live
one). Host: `BriefingHeader` (`page.tsx:231`,
`components/briefing/BriefingHeader.tsx`) — its left column (asset
`<h1>`, ALWAYS rendered, card-independent) is the natural at-a-glance
host, distinct from `VolumePanel`'s detailed volume+price analytical
panel lower on the page (header micro-glance vs full panel — different
scale/purpose, a standard premium-dashboard pairing, NOT redundant).
`BriefingHeader` is `"use client"` (motion) and the `microchart` SSOT
is pure/RSC-safe → importing it into the client header is doctrine-#5
safe (the leak hazard is the reverse direction only).

**Decision — NEW `components/briefing/Sparkline.tsx`, ADR-017-neutral,
graceful, SSOT-composed.** A new pure presentational component (thin
`"use client"` for the `motion` draw-in, consistent with
`VolumePanel`/`ScenariosPanel` house style ; ALL coordinate math
delegated to the pure SSOT — `xLinear` for point-to-point x, `linScale`
for value→y with an **inverted range** so higher value sits higher on
screen, `svgCoord` for the single 1-dp formatting authority ; ZERO new
coord math — doctrine #9). **ADR-017 (frontend boundary #11) — pure
descriptive historical context, NO signal**: the sparkline is a neutral
"where the intraday price has been" micro-trend, styled with the SAME
neutral `--color-text-secondary` stroke `VolumePanel`'s price overlay
already uses (`VolumePanel.tsx`, ADR-017-clean per its `:18` header) —
deliberately **NOT** direction-tinted (a green/red-by-direction line
could be misread as a bias/signal) ; no verdict text, no imperative, no
BUY/SELL, no TP/SL. A factual neutral window label only (e.g. the bar
count) — describing the data, not a trade action. **Graceful empty**:
`< 2` points → renders nothing (the `VolumePanel` `usable.length < 2`
discipline). **Wiring**: `BriefingHeader` gains an optional
`priceTrend?: number[]` prop (decoupled — `number[]` closes, NOT the
`IntradayBarOut` type) rendered under the asset `<h1>` ; `page.tsx:231`
threads `priceTrend={recentBars.map((b) => b.close)}` (one line ;
`recentBars` already derived for `VolumePanel`).

**What r112 implements.**

1. **NEW `apps/web2/components/briefing/Sparkline.tsx`** — pure
   presentational micro-trend. `points` via
   `values.map((v,i) => `${svgCoord(xLinear(i, n, W, pad))},${svgCoord(
   yScale(v))}`)` where `yScale = linScale(min, max, H - pad, pad)`
   (inverted range : min→bottom, max→top ; degenerate min===max →
   `linScale` maps to `rangeMin` = bottom, a flat baseline, no NaN —
   the SSOT's documented zero-width-domain behaviour). Fixed integer
   viewBox, `preserveAspectRatio="none"`. `< 2` values → `null`.
   `role="img"` + an `aria-label` text equivalent (the a11y
   requirement for a graphic — WCAG 2.2 AA). Neutral stroke, thin
   `motion` draw-in (opacity), `vectorEffect="non-scaling-stroke"`
   (mirrors `VolumePanel`'s polyline attrs).
2. **`apps/web2/components/briefing/BriefingHeader.tsx`** — add
   `priceTrend?: number[]` to the props ; render `<Sparkline>` under
   the asset `<h1>` in the always-rendered left column (card-
   independent — shows even with no session card yet, since intraday
   data is independent of the card) ; graceful when absent/short.
3. **`apps/web2/app/briefing/[asset]/page.tsx:231`** — one-line:
   `priceTrend={recentBars.map((b) => b.close)}`.
4. **`apps/web2/__tests__/microchart.test.ts`** (or a new sibling) —
   an additive describe block pinning the `<Sparkline>` coordinate
   CONTRACT (NOT a byte-identical-vs-prior proof — this is a NEW
   component, nothing pre-existing to be identical to ; the honest
   distinction from r105/r108/r109/r111): given a fixture series +
   dims, the produced `points` are exactly `xLinear`/`linScale`/
   `svgCoord`-composed, every coord 1-dp, in-viewBox, x strictly
   increasing, and the degenerate flat-series case maps to the
   baseline (no NaN). Pre-existing tests unchanged (zero regression).
5. **ADR-099 `## Implementation (r112, 2026-05-19)`** (this) — dated
   §Impl, NO new ADR (doctrine #9).

**Honest scope / ledger (#11, NOT thinned).** r112 = the NEW
`<Sparkline>` primitive + ONE genuine consumer (BriefingHeader price
micro-trend) + the page wiring + the contract test. It is "more
coverage" (doctrine #8) — a NEW additive component and a NEW genuine
`xLinear`/`linScale` consumer — explicitly NOT de-accumulation
(doctrine-#9 is already FULLY CLOSED at r111 ; nothing SSOT-internal
remains). Explicitly DEFERRED, NOT thinned: further `<Sparkline>`
consumers (other panels/cards) ; the regime-timeline NEW component
(reuse `regime-quadrant` `RegimeId`/`QUADRANTS` colour map) ; T4.2
(uncertainty band / calibration overlay / degraded+empty states /
`prefers-reduced-motion` / no-truncated-axis audit) ; T4.3
(responsive/mobile) ; the non-Tier-4 r107-deferred items
(`globals.css` §5 border-α, `NarrativeBlocks` `/10` chip). The
r111-flagged PRE-EXISTING app-wide console defects (briefing
vendor-chunk `TypeError`, `/` `localhost:8001` CSP dev-artifact, React
#418) remain a SEPARATE spawn-tasked out-of-scope item — NOT re-scoped
into r112, NOT re-claimed. **NEW r112 a11y flag (pre-existing, NOT
r112's, flag-not-fix lesson #11 / r106-a)**: the accessibility-reviewer
measured the `BriefingHeader` `text-[10px] --color-text-muted`
micro-label pattern (shared by the pre-existing Conviction / Magnitude
/ Régime labels AND inherited by the new "Prix intraday · N barres"
label) at ≈ 3.5:1 over `--color-bg-elevated` (< the 4.5:1 floor for
sub-18px text). It is a header-WIDE pre-existing token-recalibration
issue, NOT introduced by the Sparkline — routed to the existing
ADR-099 §T4.2 / `globals.css` §5 contrast-recalibration backlog ; the
new label deliberately keeps `--color-text-muted` for sibling visual
consistency (a one-off brighter label would be inconsistent and would
not fix the app-wide root cause).

**Reviews (consolidated single pass — doctrine #14, finalized on the
post-prettier committed shape ; ichor-trader R28 + ui-designer +
accessibility-reviewer ALL dispatched — a NEW visual component
genuinely changes the trading-boundary, design, AND a11y surface, so
all three are protocol not FOMO, lesson #17 ; verdicts recorded as
MEASURED not forecast, lesson #1/r111).**

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 1 YELLOW (doc-only)
  APPLIED** (the MEASURED verdict, not a forecast — lesson #1). ADR-017
  frontend boundary held: the neutral `var(--color-text-secondary)`
  stroke independently cross-checked **identical** to the already-
  ADR-017-clean `VolumePanel.tsx:161` close-price overlay (`:18`
  header "pure descriptive activity. No bias, no BUY/SELL") — the
  neutral-styling parity claim _verified true, not asserted_ ; the
  Sparkline deliberately avoids the `biasTone()` bull/bear palette ;
  labels factual-only (no verdict/imperative/BUY-SELL/TP-SL) ;
  rendering the same `recentBars` closes VolumePanel already plots is
  no new signal surface. SHIPPED≠FUNCTIONAL avoided by construction
  (proven-live intraday series, categorically distinct from the
  `correlations_snapshot`-empty / `card.scenarios`-type-only traps).
  R59 reshape correctly classified r109-class ("disproved-as-worded",
  not r110-class) ; doctrine #8 vs #9 accurate (de-accumulation stays
  FULLY CLOSED at r111, not reopened). Cross-file drift: exactly one
  `BriefingHeader` call site (`page.tsx:231`), the new prop optional/
  backward-compat. **YELLOW-1 APPLIED**: `BriefingHeader.tsx:2-10`
  docstring "Renders :" enumeration was stale (omitted the new
  Sparkline — a lesson-#5 drift this change introduced) → a clause
  added pre-merge.
- **ui-designer — MERGE, 0 Critical ; 2 Important + 2 Nit APPLIED.**
  Imp-1 (the dimension triple-source-of-truth: `Sparkline` defaults
  120/32 vs the call's 160/36 vs `className="h-9 w-40"`, silently
  divergent under `preserveAspectRatio="none"`) → the `<svg>` now
  OWNS its box (explicit `width`/`height` === viewBox, 1:1 — single
  source, also eliminating the non-uniform-scale distortion nit) and
  the caller `className` sizing is dropped. Imp-2 (no `<title>`,
  inconsistent with `VolumePanel`'s `<title>`/`<desc>` pattern) → a
  `<title>` mirroring `aria-label` added. Nit-3 (opacity 0.75 vs
  VolumePanel's price-line 0.7) → aligned to **0.7**. Nit-4
  (`tracking-widest` vs the header micro-label idiom) → aligned to
  `tracking-[0.2em]`. Placement/hierarchy/empty-state/contrast all
  PASS (the `mt-3` rhythm, the conditional-wrapper zero-layout-shift
  absence, `var(--color-text-secondary)` visibility all confirmed).
- **accessibility-reviewer — 0 MUST-FIX ; 1 SHOULD-FIX → backlog
  (NOT a r112 blocker, NOT fixed here — flag-not-fix, lesson #11 /
  r106-a).** WCAG 2.2 AA: **1.1.1 PASS** (`role="img"`+`aria-label`,
  the chart is a supplementary glance never the sole carrier — the
  header conveys asset/bias/conviction/regime textually + the visible
  label) ; **1.4.11 PASS** (stroke `#A4ADBA` vs worst-case backdrop
  `--color-bg-elevated` `#0F1828` ≈ **6.1:1**, the 0.7-opacity end-
  state ≈ 4:1 — clear of the 3:1 graphical floor) ; **1.4.1 PASS**
  (single neutral monochrome, zero color-only meaning) ; **1.4.3**
  the visible "Prix intraday · N barres" label uses
  `--color-text-muted` ≈ **3.5:1 over `--color-bg-elevated`** (< 4.5:1
  for sub-18px) — BUT this is a **PRE-EXISTING header-wide pattern**
  (every `text-[10px] text-muted` label in `BriefingHeader` — the
  Conviction/Magnitude/Régime labels — shares it ; NOT introduced by
  r112) → kept `--color-text-muted` for sibling visual consistency
  (both reviewers endorse the header micro-label idiom) and **routed
  to the existing ADR-099 §T4.2 / `globals.css` §5 contrast-
  recalibration backlog** (a one-off brighter label would be
  inconsistent AND would not fix the real app-wide issue) ;
  **2.3.3 PASS** (opacity-only draw-in, no transform — not a
  vestibular trigger ; the global `useReducedMotion` pass is the
  T4.2 home).

**Verification (real numbers — measured on deployed prod, not
forecast ; the SHIPPED≠FUNCTIONAL gate satisfied).**

- **Build gate** (post-prettier committed shape, doctrine #14 — re-run
  after the consolidated review-apply): `tsc --noEmit` **0** · `eslint
--max-warnings 0` (Sparkline.tsx + BriefingHeader.tsx + page.tsx +
  microchart.test.ts) **0** · vitest **7 files / 124 tests pass**
  (r111 baseline 119 + the new r112 Sparkline contract block 5 = 124 ;
  zero regression) · `next build` **OK**.
- **Deploy**: `scripts/hetzner/redeploy-web2.sh` (additive — port
  3031, legacy `ichor-web` 3030 + tunnel untouched). RESULT
  **`local=200 public=200`, `DEPLOY OK`** ; LIVE URL **stable**
  `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel NOT restarted) ; no SSH throttle.
- **Real-prod witness** — Playwright on the deployed public
  `/briefing/EUR_USD` (doctrine #7 ; REAL data, REAL asset). **r112
  surface GREEN**: the `BriefingHeader` `<Sparkline>` renders from
  **90 real intraday closes** (the `recentBars` series), viewBox
  `0 0 160 36` with matching `width`/`height` attrs (svg-owns-box,
  1:1 — no distortion), `<title>` === `aria-label` ("Tendance du
  prix de clôture intrajournalier EUR/USD, 90 dernières barres"),
  `role="img"`. Geometry cross-checked: 90 points, **every coord
  1-dp** (`svgCoord` end-to-end through `xLinear`+`linScale`), all
  in-viewBox, **x strictly increasing** (proving genuine point-to-
  point `xLinear`, NOT band-coupled — the R59 reshape empirically
  validated), endpoints exact (`x[0]=2.0`=pad, `x[89]=158.0`=
  width−pad). Stroke `var(--color-text-secondary)` (ADR-017-neutral).
  **Distinct from VolumePanel** confirmed (its sibling chart is
  viewBox `0 0 640 150` — header micro-glance vs full panel, not
  redundant). Screenshot captured.
- **Console — honestly scoped (lesson #1 / #11 / r106-a, NO
  fabricated causation).** This warm post-r112 load of
  `/briefing/EUR_USD` showed **0 errors / 0 warnings**. The
  r111-witnessed PRE-EXISTING app-wide defects (a cold-load
  vendor-chunk `TypeError ×9` + favicon-404) were NOT observed on
  this load — their reproduction is load/timing-dependent (the r109
  "warm 0/0" precedent). **r112 is purely additive (Sparkline +
  wiring) — it neither CAUSED nor FIXED those pre-existing defects** ;
  the r111 spawn-task remains their owner (NOT re-scoped, NOT
  re-claimed as a r112 win). The r112 surface itself is clean.

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR ; doctrine #8 "more coverage" (NEW component + NEW SSOT consumer),
explicitly NOT de-accumulation (closed at r111).

## Implementation (r113, 2026-05-19) — Tier 4: additive NEW genuine `<Sparkline>` consumer — the intraday true-range (high−low) amplitude micro-trend in `BriefingHeader` (a 2nd, DISTINCT proven-live series ; doctrine #8 "more coverage", NOT de-accumulation ; the literal default (A) regime-timeline R59-DISPROVED → reshaped to (B))

doctrine-#9 de-accumulation closed at r111 ; r112 shipped the first
additive NEW component (the generic `<Sparkline>`). r113 is the next
additive Tier-4 increment (doctrine #8 "more coverage") — a NEW genuine
consumer of the already-generic r112 `<Sparkline>` rendering a NEW,
DISTINCT data dimension. ZERO new component, ZERO new coord math
(doctrine #9 — the r112 `<Sparkline>` is reused as-is), ZERO backend,
ZERO migration (alembic still 0050).

**R59 inspect-first RESHAPED the literal default (meta-r110/r112 — the
default is itself a HYPOTHESIS, including an ADDITIVE default).** The
r112-close binding default offered two candidates: (A) a NEW
regime-timeline component (reusing `regime-quadrant`
`RegimeId`/`QUADRANTS`) OR (B) further `<Sparkline>` consumers. A
read-only researcher R59 + direct orchestrator file:line verification
**disproved (A) as worded** (an r110-class disproof for that candidate,
not a forced build): repo-wide grep for
`regime_history|regimeHistory|regime_timeline|regime_series` in
`apps/web2` → **zero matches** ; `SessionCard` projects exactly ONE
regime field — `regime_quadrant: string | null` (`lib/api.ts:195`), a
single scalar, NOT an array ; consumed as a single value only
(`BriefingHeader.tsx:128-137` one chip, `page.tsx:248`
`PocketSkillBadge`) ; `RegimeQuadrant.history?` is a `{x,y,ts}[]`
macro-coordinate trail (NOT a regime-id series) and `RegimeQuadrant` is
**not rendered on the briefing page at all**. A regime-timeline frieze
would therefore have **no real series to render** — a fake-SSOT /
SHIPPED≠FUNCTIONAL by construction (the r106/r108 type-only trap).
Per meta-r110/r112 the honest move is NOT to force it — it is to
execute candidate (B) on a series R59-proven projected AND populated.

**R59 verified consumption site + real populated data (#1 — projected
AND populated, measured on real prod, NOT type-only).** The
`/briefing/[asset]` page already fetches `recentBars: IntradayBarOut[]`
(`page.tsx:189` `intraday.slice(-90)`, endpoint
`/v1/market/intraday/{asset}` `lib/api.ts:304-310`). `IntradayBarOut`
(`lib/api.ts:1189-1196`) carries `open`/`high`/`low`/`close: number`

- `volume: number | null`. `close` is on screen already (r112
  Sparkline) and `volume` is on screen already (`VolumePanel`), but
  `high`/`low` are NOT charted anywhere — and **type-presence ≠
  runtime-populated (#1)**, so the orchestrator R53-verified the live
  prod API directly (one consolidated throttle-aware SSH,
  `curl 127.0.0.1:8000/v1/market/intraday/{EUR_USD,XAU_USD}?hours=24&limit=12`):
  real OHLC bars with **genuinely distinct, non-degenerate, varying**
  `high`/`low` — EUR_USD bar 1 `open 1.16526 / high 1.16543 / low 1.1652
/ close 1.16538` (12 bars, true-range 0.00023→0.0005) ; XAU_USD bar 1
  `open 4578.28 / high 4580.34 / low 4577.76 / close 4579.39` (12 bars,
  true-range 2.35→4.58). `high − low` (the per-bar intraday true range)
  is therefore a series **projected AND empirically populated on real
  prod across 2 distinct assets** — SHIPPED≠FUNCTIONAL avoided BY
  CONSTRUCTION, the r112 discipline.

**Decision — a NEW genuine `<Sparkline>` consumer: the intraday
amplitude (high−low) micro-trend, ADR-017-neutral, SSOT-composed,
ZERO new code beyond wiring.** The r112 `<Sparkline>`
(`components/briefing/Sparkline.tsx`) is already a fully generic
primitive (`values: number[]` + `ariaLabel` ; all coordinate math is
the r105 SSOT — `xLinear`+`linScale`+`svgCoord`). r113 does NOT add a
component and does NOT add coord math (doctrine #9) — it adds a NEW
genuine _consumer_ of a NEW, DISTINCT data dimension: per-bar intraday
true range `high − low`, which is intraday-volatility/amplitude context
— categorically distinct from the r112 close-price _level_ trend and
from the `VolumePanel` _volume_ series (it is neither a duplicate of an
on-screen series — the very anti-pattern the r112 reshape avoided — nor
a new colour encoding). **ADR-017 (frontend boundary #11) — pure
descriptive geometry, NO signal**: `high − low` says nothing about
direction, no BUY/SELL, no order, no personalized sizing ; it reuses
the SAME neutral `var(--color-text-secondary)` Sparkline already
cross-checked ADR-017-clean at r112 (NOT direction-tinted) ; the visible
label is factual-only ("Amplitude intraday · N barres" — describes the
data window, not a trade action). Host: the SAME `BriefingHeader` left
column under the asset `<h1>`, stacked under the r112 price micro-trend
(price _level_ + price _amplitude_ is a standard premium-dashboard
pairing, distinct meaning, distinct label — not redundant).

**What r113 implements.**

1. **`apps/web2/components/briefing/BriefingHeader.tsx`** — a new
   optional `rangeTrend?: number[]` prop (decoupled `number[]`, mirror
   of the r112 `priceTrend?` pattern) ; a 2nd `<Sparkline>` rendered
   directly under the r112 price Sparkline, with its own neutral
   `aria-label` and factual "Amplitude intraday · N barres" label ;
   self-guarding (`>= 2` → rendered, else absent — the r112
   graceful-empty discipline) ; the `Renders :` docstring enumeration
   extended (anti-lesson-#5 drift, the r112 ichor-trader-YELLOW class).
2. **`apps/web2/app/briefing/[asset]/page.tsx`** — one line:
   `rangeTrend={recentBars.map((b) => b.high - b.low)}` (the SAME
   `recentBars` already derived for `VolumePanel`/the r112 Sparkline —
   ZERO new fetch, ZERO backend).
3. **`apps/web2/__tests__/microchart.test.ts`** — an additive describe
   block pinning the r113 _consumer contract_ (NOT a
   byte-identical-vs-prior proof — there is no "old" ; the honest
   distinction, r112-class): a fixture OHLC series → the derived
   `high − low` series is non-negative, the `<Sparkline>` of it is
   SSOT-composed (every coord 1-dp, x strictly increasing, in-viewBox,
   `linScale` inverted-range), and a degenerate flat-range series maps
   to the baseline (no NaN). Pre-existing tests unchanged (zero
   regression).
4. **ADR-099 `## Implementation (r113, 2026-05-19)`** (this) — dated
   §Impl, NO new ADR (doctrine #9). Reviews / Verification written as
   placeholders then RECONCILED to the MEASURED outcomes (lesson #1 —
   no forecast).

**Honest scope / ledger (#11, NOT thinned).** r113 = ONE NEW genuine
`<Sparkline>` consumer (intraday amplitude) + the page wiring + the
consumer contract test. "More coverage" (doctrine #8), explicitly NOT
de-accumulation (FULLY CLOSED r111). Explicitly DEFERRED, NOT thinned:
the regime-timeline NEW component (R59-disproved on the briefing page
this round — would require a NEW regime time-series projected from the
backend first, a separate Pydantic-projection increment, the #1 class —
NOT a frontend-only Tier-4 item) ; further `<Sparkline>` consumers
beyond price+amplitude ; T4.2 (uncertainty band / calibration overlay /
degraded+empty states / `prefers-reduced-motion` global / no-truncated-
axis audit) ; T4.3 (responsive/mobile) ; the non-Tier-4 r107-deferred
(`globals.css` §5 border-α, `NarrativeBlocks` `/10` chip). The
r111-flagged PRE-EXISTING app-wide console defects (briefing
vendor-chunk `TypeError`, `/` `localhost:8001` CSP dev-artifact, React
#418) AND the r112-flagged PRE-EXISTING header-wide `text-muted`
≈3.5:1 contrast (ADR-099 §T4.2 / `globals.css` §5 backlog) remain
SEPARATE owners — NOT re-scoped into r113, NOT re-claimed (lesson #11 /
r106-a).

**Reviews (consolidated single pass — doctrine #14, finalized on the
post-prettier committed shape ; ichor-trader R28 + ui-designer +
accessibility-reviewer ALL dispatched — a NEW visual surface (a 2nd
header micro-chart) genuinely changes the trading-boundary, design AND
a11y surface, protocol not FOMO lesson #17 ; verdicts recorded as
MEASURED not forecast, lesson #1).**

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 1 YELLOW (doc-only)
  APPLIED** (the MEASURED verdict, not a forecast — lesson #1). ADR-017
  frontend boundary held: the reviewer read `Sparkline.tsx:91`
  **directly** and the neutral `stroke="var(--color-text-secondary)"`
  claim is **VERIFIED-TRUE, not asserted** — NOT direction-tinted, the
  same neutral stroke reused for both the r112 price and the r113
  amplitude charts (no per-series tinting) ; `high − low` is a
  non-negative scalar amplitude that **structurally cannot encode a
  directional call** ; the label `Amplitude intraday` + ariaLabel
  `Amplitude intrajournalière (haut−bas)` are factual-only (no
  BUY/SELL, no imperative, no order, no personalized sizing, no
  direction word) — descriptive volatility context, equivalent in
  nature to the existing `VolumePanel` "Activité intraday" overlay.
  Conviction cap untouched (`BriefingHeader.tsx` `Math.min(...,95)` +
  "ADR-022 cap : 95 %" preserved) ; the other 7 invariants N/A (a
  frontend render of an already-fetched OHLC field). SHIPPED≠FUNCTIONAL
  genuinely avoided (R53 ground-truth — real distinct OHLC high/low on
  EUR/XAU). Doctrine #8-vs-#9 classification ACCURATE (a NEW _consumer_
  of the generic r112 `<Sparkline>`, zero new component, zero new coord
  math — verified `Sparkline.tsx:36,68,71` = the r105 SSOT ; "more
  coverage" #8, not de-accumulation, closed r111). Backward-compat OK
  (`rangeTrend?` optional, self-guarding `>= 2`, single call site
  `page.tsx`). Cross-file drift: NONE — the `Renders :` docstring was
  correctly updated to "price + amplitude (high−low) micro-trend
  Sparkline pair" with the ADR-017 disclaimer (no stale price-only
  wording, the r112 ichor-trader-YELLOW class avoided). **YELLOW-1
  (doc-only) APPLIED**: this Reviews/Verification subsection was
  reconciled from the placeholder brackets to the MEASURED verdicts
  (this edit) — no literal placeholder text left in the Accepted-track
  §Impl, the build-gate part reconciled to measured below, the
  Deploy/Witness/Console part honestly retained as "pending the deploy
  step — observed event ≠ proof, lesson #1" until reconciled
  post-witness.
- **ui-designer — MERGE-with-changes, 0 Critical ; 1 Important + 2 Nit
  APPLIED.** Important (the two charts are visually indistinguishable —
  identical neutral stroke/dims/wrapper, only a 10px label
  disambiguates ; exact-mirror was right at r112 sibling-less but with
  a sibling of a _different physical quantity_ parity now hurts the
  instant read) → the differentiating first word of each label
  (`Prix` / `Amplitude`) promoted to a `font-medium
text-[var(--color-text-secondary)]` eye-lock token (no component
  change, zero new coord math #9 ; the factual word ichor-trader
  already cleared — ADR-017-safe ; the visible text content and
  reading order are unchanged). Nit-1 (4 consecutive `mt-3` collapse
  the hierarchy) → the amplitude row `mt-3`→`mt-2` (pairs the two
  sparklines as one intraday-micro-trend unit) and the thesis
  `mt-3`→`mt-4` (the in-file `mt-4` regime-chip precedent). Nit-3
  (the label is now the sole semantic differentiator) → subsumed by
  the Important fix (the promoted lead word is the `text-secondary`
  carrier). Empty/short-series zero-layout-shift, responsive
  (1fr column, 160px < mobile width), and parity mechanics confirmed
  PASS.
- **accessibility-reviewer — 0 MUST-FIX ; SHOULD-FIX all PRE-EXISTING
  → existing backlog (flag-not-fix, lesson #11 / r106-a — NOT
  re-scoped into r113).** WCAG 2.2 AA clean for what r113 introduces.
  **1.1.1 PASS** (the new `aria-label` is a meaningful, distinct text
  equivalent — "Amplitude intrajournalière (haut−bas)…" vs the r112
  "Tendance du prix de clôture…" — and supplementary, the header
  conveys asset/bias/conviction/magnitude/regime textually ; two
  adjacent `role="img"` with distinct labels are unambiguous to SR).
  **1.4.1 PASS** (single neutral monochrome, zero colour-only
  meaning). **1.4.11 PASS** (stroke ≈ 6.5:1 over `#0F1828`, reused
  unchanged from r112). **2.3.3 PASS** (opacity-only draw-in, no
  transform). Structure/reading-order PASS. **1.4.3 — PRE-EXISTING,
  NOT r113-introduced**: the `text-[10px] --color-text-muted`
  micro-label tail ≈ 3.4–3.6:1 is the identical header-wide pattern
  already carried by Conviction/Magnitude/Régime/the r112 "Prix
  intraday" sibling/the LIVE row, flagged at r112 and on the ADR-099
  §T4.2 / `globals.css` §5 contrast-recalibration backlog — r113
  reuses it verbatim for sibling consistency and does **not make it
  materially worse** ; the ui-designer Important fix incidentally
  _improves_ the load-bearing differentiator word to ≈6.5:1
  (`text-secondary`) without re-scoping the header-wide backlog (the
  muted tail stays the pre-existing pattern — flag-not-fix). A second
  PRE-EXISTING note surfaced this round (NOT r113's): the UNCHANGED
  r112 `Sparkline.tsx` `role="img"` + `aria-label` + `<title>`
  mirroring causes an SR double-announce on some NVDA/JAWS — a
  component-wide pre-existing item inherited by r113, routed to the
  same a11y backlog, NOT a r113 regression (lesson #11).

**Verification (real numbers — measured on deployed prod, not
forecast ; the SHIPPED≠FUNCTIONAL gate satisfied by the R53-verified
populated series above).**

- **Build gate (MEASURED, re-run post-review-apply on the committed
  shape, doctrine #14)**: `tsc --noEmit` **0** · `eslint
--max-warnings 0` (BriefingHeader.tsx + page.tsx + microchart.test.ts)
  **0** · vitest **7 files / 127 tests pass** (r112 baseline 124 + the
  3 new r113 consumer-contract tests = 127, zero regression) ·
  `next build` **OK** — NB the local Windows build's first run hit a
  transient `Collecting build traces` ENOENT on
  `_not-found/page.js.nft.json` (a Windows file-lock artifact in a
  route r113 never touches ; static-gen 38/38 ✓, tsc/eslint/vitest all
  green) ; a non-destructive re-run on the unchanged tree succeeded
  (lesson #13 — env artifact, not a r113 defect ; the authoritative
  build is the Linux `redeploy-web2.sh` anyway). A final
  post-prettier-committed-shape re-gate is run at commit (#14).
- **Deploy (MEASURED)**: `scripts/hetzner/redeploy-web2.sh` additive
  — the Hetzner **Linux** `pnpm --filter @ichor/web2 build` completed
  clean (full route table, NO `.nft.json` ENOENT — confirming the
  Windows-local trace-collection ENOENT was an env artifact, lesson
  #13 ; the Linux build is the authoritative one). `Step 4: local
/briefing http=200` ; `RESULT: local=200 public=200` ; `DEPLOY OK
— /briefing is reachable. Legacy ichor-web (3030) untouched.` LIVE
  URL **stable** `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
  (tunnel NOT restarted — unchanged from r112), no SSH throttle
  (~45 s, single script run).
- **Real-prod witness (MEASURED — Playwright on the deployed public
  `/briefing/EUR_USD`, REAL data, REAL asset, doctrine #7)**: the
  `BriefingHeader` left column renders **TWO** `role="img"`
  `<Sparkline>` SVGs. (1) The r112 price micro-trend UNCHANGED (no
  regression): aria-label "Tendance du prix de clôture intrajournalier
  EUR/USD, 90 dernières barres", viewBox `0 0 160 36`, svg-owns-box
  (`width`/`height` === viewBox), neutral
  `stroke=var(--color-text-secondary)`, 90 points, `first=2.0,9.1`
  `last=158.0,21.9`, allOneDp ✓ strictlyIncX ✓ inViewBox ✓
  title===aria-label ✓. (2) The NEW r113 amplitude micro-trend:
  aria-label "Amplitude intrajournalière (haut−bas) EUR/USD, 90
  dernières barres", viewBox `0 0 160 36`, svg-owns-box, **the SAME
  neutral `stroke=var(--color-text-secondary)` as the price chart —
  NO per-series tinting (the ichor-trader ADR-017 VERIFIED-TRUE claim
  confirmed live)**, **90 points from the real `high − low` series**,
  `first=2.0,31.8` `last=158.0,14.4`, endpoints exact
  (`x[0]=2.0`=pad, `x[89]=158.0`=width−pad), **allOneDp ✓ strictlyIncX
  ✓** (proves genuine point-to-point `xLinear`, the SSOT composition,
  NOT band) **inViewBox ✓** title===aria-label ✓. The two promoted
  lead words ("Prix" / "Amplitude") render in the
  `font-medium text-secondary` eye-lock token (the ui-designer
  Important fix, live-confirmed). **`priceVsAmplitudeIdenticalPoints
= false`** — the price and amplitude polylines are GENUINELY
  DISTINCT series (price `2.0,9.1→158.0,21.9` vs amplitude
  `2.0,31.8→158.0,14.4`) : empirical proof r113 is NOT an on-screen
  duplicate (the anti-pattern the r112 reshape avoided) but a real,
  distinct data dimension rendering from real prod data —
  **SHIPPED≠FUNCTIONAL empirically avoided, not asserted**. Screenshot
  captured.
- **Console — honestly scoped (lesson #1 / #11 / r106-a, NO fabricated
  causation, NOT over-claimed on the up-side)**: this witness load of
  `/briefing/EUR_USD` showed exactly **1 error: a `favicon.ico` 404**
  — a PRE-EXISTING trivial app-wide 404 already on the hygiene
  backlog / the r111 spawn-task, NOT r113's. The r111-witnessed
  PRE-EXISTING app-wide defects (vendor-chunk `TypeError ×9`, React
  #418, `/` `localhost:8001` CSP dev-artifact) were NOT observed on
  this load (load/timing-dependent — the r109/r112 "warm" precedent).
  **r113 is purely additive (one new `<Sparkline>` consumer + one
  wiring line + a promoted label word) — it NEITHER caused NOR fixed
  any console defect** ; the r111 spawn-task + the r112-flagged
  header-wide `text-muted` §T4.2 backlog remain the owners (NOT
  re-scoped, NOT re-claimed as a r113 win — a witnessed near-clean
  console is not the increment that fixes a pre-existing defect it
  never touched). The r113 surface itself (the two Sparklines) emits
  zero r113-related console output.

Voie D + ADR-017 held ; additive web2-only deploy ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR ; doctrine #8 "more coverage" (a NEW genuine SSOT consumer + a NEW
distinct data dimension), explicitly NOT de-accumulation (closed at
r111) ; the literal default (A) regime-timeline R59-DISPROVED on the
briefing page (no projected regime series) → reshaped to (B), the
honest meta-r110/r112 move.

## Implementation (r114, 2026-05-19) — the r111 spawn-task, part 1/2: client-side API-base leak — `apiGet` is missing the `isBrowser` branch `apiMutate` already has → browser fetches `http://localhost:8001` → prod CSP `connect-src 'self' wss:` blocks it → critical-alerts + macro-pulse silently dead on the public deploy

The r111 deployed witness surfaced (did NOT cause) two PRE-EXISTING
app-wide client console defects, already named in this ADR's r112/r113
console-honesty notes and owned by "the r111 spawn-task". r114 is part
1/2 of that task (part 2/2 = r115, the `motion`-strict root cause).
INDEPENDENT root causes → one increment per round, ADR-before-code each.

**R59 — reproduced BEFORE any code change, never guessed**, on TWO
surfaces : (1) the deployed r112 public URL
(`latino-superintendent-restoration-dealtime.trycloudflare.com`) — a
Playwright load of `/` emits, repeatedly (the landing pollers tick),
`Connecting to 'http://localhost:8001/v1/alerts?severity=critical&
unacknowledged_only=true&limit=20' violates … "connect-src 'self'
wss:"` + the same for `http://localhost:8001/v1/macro-pulse` + the
`[api] … → network error: Failed to fetch` warnings ; (2) the
non-minified dev build (`pnpm next dev`, real backend via a read-only
SSH tunnel `localhost:8001→hetzner:8000`, mirroring prod's
`ICHOR_API_URL`) — the SAME errors with **source-mapped** frames
`webpack-internal:///(app-pages-browser)/./lib/api.ts:41` (the
`fetch(url)`) and `:48` (the `catch` `console.warn`). The SSR/RSC
`(rsc)/./lib/api.ts` path is unaffected (server keeps `API_BASE`).

**Root cause (source-confirmed, `apps/web2/lib/api.ts`)** : `API_BASE
= process.env.ICHOR_API_URL ?? "http://localhost:8001"` (api.ts:9).
`ICHOR_API_URL` is a **server-only** env (NOT `NEXT_PUBLIC_*`), so in
the browser it is `undefined` → `API_BASE` resolves to the
SSH-tunnel DEV port `http://localhost:8001`. `apiMutate` already
handles this correctly — `const base = opts.baseUrl ?? (isBrowser ? ""
: API_BASE)` (api.ts:62-63) — so client mutations hit the **same-origin
`/v1/*` Next rewrite proxy** (`next.config.ts` `rewrites()` →
`${ICHOR_API_PROXY_TARGET ?? "http://127.0.0.1:8000"}/v1/:path*` ; its
docstring states verbatim that client fetches must use same-origin
`/v1/...` paths). **`apiGet` is missing that exact branch** (api.ts:22
`const base = opts.baseUrl ?? API_BASE`) — the sole asymmetry. The two
client pollers that bite : `components/ui/crisis-banner.tsx:55`
(`apiGet("/v1/alerts?severity=critical&unacknowledged_only=true&
limit=20")`, 30 s) and `components/ui/live-ticker.tsx:58`
(`apiGet("/v1/macro-pulse")`, 15 s) — both `"use client"` on `/`
(absent from the `/briefing` shell, which is why briefing never showed
this). Production CSP `connect-src 'self' wss:` (`next.config.ts`
`SECURITY_HEADERS`) allows same-origin but blocks cross-origin
`localhost:8001` → critical-alerts banner + macro-pulse ticker are
**silently dead on the public deploy** (graceful `null` fallback hides
it — a silent-failure, not a crash).

**Fix (1 line, house-pattern, minimal, non-speculative)** : api.ts:22
`const base = opts.baseUrl ?? API_BASE;` → `const base = opts.baseUrl
?? (typeof window !== "undefined" ? "" : API_BASE);` — a verbatim
mirror of `apiMutate`'s already-validated branch (api.ts:62-63). Client
GETs become same-origin `/v1/...` → the Next rewrite proxies them
server-side to the backend (CSP `'self'`-clean). SSR/Server-Action
callers keep `isBrowser=false` → `API_BASE` (`ICHOR_API_URL=
http://127.0.0.1:8000` on Hetzner per the systemd unit) — **strict
zero-diff for every server caller** (`app/page.tsx`, `app/alerts`,
`app/macro-pulse`, `app/assets/[code]`, …). NOT weakening CSP, NOT a
`NEXT_PUBLIC_` env (would re-leak the origin), NOT touching the
pollers — the single source-of-truth asymmetry is closed where it
lives.

Build gate : `pnpm --filter @ichor/web2 exec tsc --noEmit` +
`eslint --max-warnings 0` + `vitest run` + `next build`. Deploy :
`scripts/hetzner/redeploy-web2.sh` (additive, separate
`ichor-web2`/-tunnel units, legacy `ichor-web` port 3030 untouched ;
the quick-tunnel URL rotates per the script's documented caveat —
recaptured post-deploy). Real-prod Playwright witness : `/` no longer
emits any `localhost:8001` CSP/`[api]` line (consolidated with the
r115 witness across `/`, `/briefing/EUR_USD`, `/briefing/XAU_USD`).

Voie D + ADR-017 held — pure frontend fetch-base symmetry, ZERO
Anthropic API, no signals surface touched, no Couche-2 path ; zero
backend / zero migration (alembic still 0050) ; doctrine #9 dated
append, no new ADR ; NOT de-accumulation / NOT a Tier-4 increment — a
discrete pre-existing-defect fix (the r111 spawn-task), correctly
scoped to one root cause.

## Implementation (r115, 2026-05-19) — the r111 spawn-task, part 2/2: the UNIFIED `motion`-strict root cause — full `motion.*` rendered inside `<LazyMotion strict>` throws the framer-motion invariant → React #418 on `/` (the SAME root cause as the r111-witnessed briefing `TypeError ×9`, which r112 already resolved by migrating `briefing/*` to `m`)

**R59 — root-caused via the mandated non-minified dev build, NEVER
guessed.** The r111 witness reported two SEPARATE briefing/landing
symptoms (`TypeError: e[o] is not a function ×9` on `/briefing/[asset]`
from vendor chunks ; minified `React #418` on `/`). Empirically, on the
**current r112 deploy**, `/briefing/EUR_USD` + `/briefing/XAU_USD` are
**console-clean** (fresh load + full scroll + all four tabs
Live/Analyse/Surveillance/Calibration — 0 errors ; the prompt's cited
chunks `5889-*`/`7985-*` are not even loaded on the briefing route —
the build graph differs from the r111 witness build). `/` still emits
`React #418`. A `pnpm next dev` run with the real backend (read-only
SSH tunnel, `reactStrictMode` + non-minified) loaded `/` and printed
the **decisive non-minified error**, handled by `<ErrorBoundaryHandler>`
inside `<MotionDOMComponent>` :

> `Error: You have rendered a 'motion' component within a 'LazyMotion'
component. This will break tree shaking. Import and render a 'm'
component instead.` — `framer-motion@12.38.0`
> `motion/index.mjs:127 useStrictMode` →
> `MessagePort.performWorkUntilDeadline` (scheduler).

**Single root cause for BOTH symptoms.**
`components/motion/motion-provider.tsx:27` mounts
`<LazyMotion features={domAnimation} strict>` site-wide (the
intentional ~25 KB→~6 KB tree-shake ; docstring already cites
motion.dev/docs/react-lazy-motion). framer-motion's `strict` mode
**throws** an invariant if any full `motion.*` component (vs the
lightweight `m.*`) renders inside it. Production-minified, that throw
manifests as the briefing `TypeError: e[o] is not a function` (one per
animated panel — the r111 "×9") and, on `/`, as `React #418` (the
throw is caught by the route error boundary mid-hydration → the
server-rendered text no longer matches the client tree → React's
minified text-mismatch code, `args[]=text`). Grep proof : **every
`components/briefing/*` already imports `{ m } from "motion/react"`**
(VolumePanel, BriefingHeader, ScenariosPanel, … 19 files) and renders
`<m.*>` — that `motion`→`m` briefing migration is precisely what the
r111→r112 work landed, and is **why Defect 1 no longer reproduces on
r112** (an R59 non-reproduction _explained by root cause + git
history_, NOT a fabricated fix — there is nothing left to fix on
`briefing/*` ; verified all 19 use `m`, r112 prod briefing pages are
console-clean). The **only remaining `motion.*` violators** are three
`components/ui/*` client components on the landing `/` (absent from
the `/briefing` shell — exactly why `/briefing` is clean and `/` is
not) :

- `components/ui/crisis-banner.tsx` — `import { motion,
useReducedMotion }` ; `<motion.div>` (lines 23, 75, 118).
- `components/ui/live-ticker.tsx` — `import { motion,
useReducedMotion, useSpring, useTransform }` ; `<motion.span>`
  (lines 20, 36).
- `components/ui/bias-opportunities-grid.tsx` — `import { motion,
useReducedMotion }` ; `<motion.div>` ×2 (lines 22, 78, 130).

**Fix (mechanical, house-pattern, the framer-motion-canonical
remedy).** In those three files only : `import { motion, … }` →
`import { m, … }` and every `<motion.X>`/`</motion.X>` →
`<m.X>`/`</m.X>`. The hooks (`useReducedMotion`, `useSpring`,
`useTransform`) are NOT the component factory — they stay imported
from `motion/react`, LazyMotion-safe (verbatim the validated
`briefing/*` pattern, e.g. `EventSurpriseGauge.tsx`). **NOT**
weakening the provider by dropping `strict` (that would defeat the
documented tree-shake the provider exists for and re-hide the next
regression) — the canonical fix is `m`, applied where the asymmetry
lives. Animation props/behaviour byte-identical (`m.*` mirrors
`motion.*` exactly). The `relTime()` `Date.now()` string in
`bias-opportunities-grid` is a _latent_ SSR/CSR text-skew but the dev
build showed the `motion`-strict invariant — NOT a text-content
warning — as the `/` error ; evidence-driven, NOT speculatively
touched (no scope creep ; if a residual surfaces in the witness it is
addressed then, on evidence).

Build gate : `tsc --noEmit` + `eslint --max-warnings 0` +
`vitest run` + a single consolidated `next build` pre-deploy (one
build, not per-increment — avoids `.next` contention with the
diagnosis dev server ; both increments touch orthogonal files
[`lib/api.ts` vs 3 `components/ui/*`] so a combined final build is a
sound gate). Deploy : `scripts/hetzner/redeploy-web2.sh` additive
(separate `ichor-web2`/-tunnel units ; legacy `ichor-web` :3030
untouched ; quick-tunnel URL rotates per the script caveat —
recaptured). Real-prod Playwright witness (consolidated, both
increments) : console **0 errors / 0 warnings** on `/`,
`/briefing/EUR_USD`, `/briefing/XAU_USD` (briefing already clean on
r112 — the witness proves the Defect-1 resolution _holds_ and `/` is
now clean for #418 + the r114 `localhost:8001`). The pre-existing
trivial `favicon.ico` 404 is on the separate hygiene backlog and is
NOT this root cause — flagged honestly, the "0/0" target additionally
adds a minimal `app/icon` only if needed to genuinely reach the bar
(decided on the witnessed evidence, not pre-emptively).

Voie D + ADR-017 held — pure frontend animation-import hygiene, ZERO
Anthropic API, no signals/Couche-2 ; zero backend / zero migration
(alembic still 0050) ; doctrine #9 dated append, no new ADR ; NOT a
Tier-4 increment — the r111 spawn-task part 2/2, one root cause, one
mechanical fix, three files.

## Implementation (r116a, 2026-05-19) — the r111 spawn-task, part 3/3: honest R59 RECLASSIFICATION of "Defect 1" (it is Next.js deployment chunk-skew, NOT a faulty briefing component, NOT the r115 motion cause, NOT "resolved by r112") + a minimal `app/icon.svg` to lock the literal 0/0 bar

**This is an r110-class honest correction : the post-deploy deployed
witness DISPROVED a claim r115 made.** The r115 §Implementation (and
its commit) asserted "Defect 1 (briefing `TypeError: e[o] is not a
function ×9`) = the SAME `motion`-strict root cause as #418, already
resolved on r112 by the `briefing/*`→`m` migration". That was a
HYPOTHESIS formed before Defect 1 had been reproduced on a fresh
build (it did not reproduce on the stale r112 deploy). The r114+r115
deployed witness reproduced it with the prompt's EXACT signature —
and the evidence disproves the hypothesis. Per project doctrine
(never-guess ; calibrated-refusal "refuser que fabriquer" ; r110
"disproving a false roadmap claim IS a verified increment"), the
honest increment is the reclassification, NOT a fabricated component
fix.

**True root cause (evidence chain, never guessed) — Next.js
deployment chunk-skew.** (a) `components/nav/top-nav.tsx:34` (and
`components/cmdk/command-palette.tsx:96`) hold `<Link
href="/correlations">` ; the top-nav is in the briefing shell, so the
App Router **prefetches the `/correlations` route chunk**. (b) Every
`next build` content-rehashes chunks ; r114's `lib/api.ts` edit is
imported app-wide → broad rehash. (c) A client holding a _previous_
build's cached `_buildManifest.js` / router state prefetches
`app/correlations/page-<OLD hash>.js` ; the new build only serves the
NEW hash → 404 (served as `text/plain` → "Refused to execute … MIME")
→ webpack `__webpack_require__` (`r`) hits `e[o] is not a function`
**×9** (modules 2748/1265/1415/7504 across chunks
`5889-*`/`7985-*`/`5318-*` — verbatim the prompt's Defect-1
fingerprint). (d) SERVER PROVEN CORRECT : deployed
`.next/app-build-manifest.json` → `app/correlations/page-
2dfc7b02db86b0cc.js`, that file present, `BUILD_ID
lI1h0GJj0dIqGQbY5rsCj` ; the served briefing **HTML embeds NO
`app/correlations` hash** (router-prefetch only) — the 404 is a
_client_ using a _stale cached manifest_, not a server/document
defect. (e) DISPROOF OF "component bug" : a clean-client load (after a
browser cache reset) → `/briefing/{EUR_USD,XAU_USD}` = **0/0** ; the
pre-deploy pristine-cache r112 briefing was likewise **0/0**. ⇒
Defect 1 is a **transient stale-client deployment-skew that
self-heals once the browser refetches the current manifest** ; a real
first-time visitor (empty cache) NEVER sees it ; the r111 witness
(and my in-session reuse of the browser across the pre/post-deploy
navigations) hit it precisely because the browser cached a _prior_
build's manifest. It is NOT a source/component defect, NOT a
regression introduced by r114/r115, and the r115 "resolved by
r112-motion" attribution is **withdrawn** (the `briefing/*`→`m`
migration is real and good but unrelated to Defect 1 ; #418 on `/`
WAS the motion cause and IS fixed by r115 — that part stands,
witnessed 0/0).

**Why NO code "fix" for Defect 1 (calibrated, non-fabricated).**
There is no faulty component to fix — the premise is disproven. The
**correct** mitigation is Next.js skew-detection : a `deploymentId`
in `next.config.ts` fed by `NEXT_DEPLOYMENT_ID` wired through
`scripts/hetzner/redeploy-web2.sh` (Next then appends `?dpl=` to
asset URLs and, on a hash miss, forces a hard navigation instead of
the fatal webpack throw). That is an **infra change to the deploy
pipeline** — explicitly an ADR-099 **Tier-0.2, Eliot-gated** item
(same precedent as the redeploy script's own documented deferral of
the stable-hostname/Tier-0.2 concern to Eliot) ; it is RECORDED here
as a scoped recommendation, deliberately NOT done blind mid-task.
`prefetch={false}` on the global nav was considered and **REJECTED** :
it does not address the root cause (a click still 404s a stale chunk —
Next then hard-navigates), and trades real navigation-prefetch UX
app-wide for transient post-deploy console-noise that self-heals
(symptom band-aid ; fails "no edge, no commit" / no-overengineering).

**The one genuine micro-fix r116 ships : `apps/web2/app/icon.svg`.**
On a clean client the ONLY remaining app-wide console line is the
PRE-EXISTING intermittent `/favicon.ico` 404 — verified root cause :
**no `app/icon.*` nor `app/favicon.*` exists** in the repo. r116 adds
a minimal inline `app/icon.svg` (Next App Router convention → auto
`<link rel="icon">` injected into `<head>` → the browser stops
requesting `/favicon.ico`). This is the deliverable's explicit literal
"0 errors / 0 warnings" bar — minimal, additive, non-speculative, NOT
scope-creep (it is the acceptance criterion itself, and the favicon
gap is named in r113's own console-honesty note as pre-existing
backlog).

**Witness (faithful, clean-client = real new visitor).** Post
r114+r115 deploy, clean browser cache : `/` = **0/0** (34 s,
live-ticker 15 s + crisis-banner 30 s pollers ticked, full hydration —
Defect 2A localhost:8001 GONE, Defect 2B/#418 GONE) ;
`/briefing/EUR_USD` = **0/0** ; `/briefing/XAU_USD` = **0/0**. r116
re-deploys with `app/icon.svg` so the favicon-404 can never recur ;
re-witnessed 0/0 on all three. Stale-client deployment-skew (Defect 1)
remains a documented Tier-0.2 `deploymentId` recommendation — honestly
scoped, not over-claimed as "fixed".

Voie D + ADR-017 held — docs reclassification + one tiny additive
static asset, ZERO Anthropic API, no signals/Couche-2 ; zero backend /
zero migration (alembic still 0050) ; doctrine #9 dated append, no new
ADR ; r110-class : disproving a false hypothesis with empirical
evidence IS a verified increment — an accurate ledger beats a
fabricated fix.

## Implementation (r116b, 2026-05-19) — Tier 4: a NEW generic SSOT-composed SVG `<BarSeries>` micro-component + the hourly-volatility 24-bar `median_bp` seasonality consumer (doctrine #8 "more coverage" — a NEW component + a NEW DISTINCT proven-live series) that ALSO closes a newly-R59-surfaced doctrine-#9-class proportional-scalar site (`HeatmapBars` `(v/max)*100` CSS-div, r108-ScenariosPanel-class, never in the r110/r111 enumerated ledger — the ledger is honestly refined per meta-r110, NOT "fully closed" re-affirmed)

**Continuity / concurrency (verified by the r113-close + the r116 live ground-truth + the ichor-trader-R28-surfaced duplicate-header audit — reconciled to MEASURED truth, NOT the mid-round assumption).** r113 = `8a50797` (additive NEW amplitude `<Sparkline>`) pushed & PR #138 head. The r111-spawn-task ("Fix pre-existing web2 public-deploy console errors") then committed **THREE** parts onto this same branch, concurrently, ITS domain (the r111-flagged backlog, NOT re-scoped): `71eb981` §Impl(r114) (apiGet client-base leak → localhost:8001 CSP-blocked) + `edda05c` §Impl(r115) (`motion.*` inside `<LazyMotion strict>` → React #418) + **`185dba7` part 3/3 (honest Defect-1 reclassification = Next deploy chunk-skew, + `app/icon.svg` locking the favicon-404)** — the third part landed AFTER the r116-start live battery (which showed HEAD `edda05c`), so r116b actually builds on HEAD `185dba7` (R59 — the live wins). **The spawn-task self-labelled its part-3/3 `## Implementation (r116, …)`, colliding with this Tier-4 round's `## Implementation (r116, …)`** ; the orchestrator appended r116b after a stale tail-read (the file changed under it between the battery and the ADR append — the r113-close concurrency class recurring). **ichor-trader R28 caught the duplicate (YELLOW-1)** ; it is disambiguated **header-only, content byte-untouched**: the spawn-task's part-3/3 → `## Implementation (r116a, …)`, this Tier-4 round → `## Implementation (r116b, …)` (a convention-restoring local doc repair on the shared Claude branch — the unique `§Impl(rN)` anchor is relied on by every round's self-references ; local/reversible/doc-only, within the autonomy boundary, "résous les conflits"). The r116b push FF-carries r114/r115/r116a to origin as ancestors (standard git on the Claude working branch — NOT an autonomy-boundary breach, NOT a merge of foreign work, NOT a rewrite of the spawn-task's intent). Honest note: r114/r115 fixed REAL prod defects but were local-unpushed AND undeployed → the live public dashboard was degraded (critical-alerts + macro-pulse silently dead) until an `185dba7`-based deploy ships ; r116b's additive deploy carries that fix to prod **as a side-effect of the normal r116b deploy — the fix is the spawn-task's r114/r115/r116a, NOT a r116b claim** (lesson #1/#11 — neither caused nor authored ; scoped honestly, not re-claimed).

**R59 inspect-first — the menu-default is itself R59-subject (meta-r110/r112/r113).** The r113-close default offered (B′) more `<Sparkline>` consumers / (C) a NEW SSOT-composed component / T4.2. A read-only researcher R59 + direct orchestrator file:line verification established: (1) the intraday OHLCV series are exhausted (`close` r112, `high−low` r113, `volume` VolumePanel) and the card-enrichment fields (`confluence_drivers`/`calibration`) are the type-only-empty `*_FALLBACK` trap (`lib/api.ts:239-244`) — AVOID (the #1 SHIPPED≠FUNCTIONAL class) ; (2) **T4.2 `prefers-reduced-motion` is ALREADY globally clean** — `MotionConfig reducedMotion="user"` wraps the app (`components/motion/motion-provider.tsx`, mounted `app/layout.tsx:82`) + a global CSS guard (`globals.css:454`) — the orchestrator's own pre-inspection T4.2 hypothesis was **R59-DISPROVED** (meta-r110 working : do not force a non-existent gap) ; (3) the genuine pick is the hourly-volatility 24-bar `median_bp` series rendered by `HeatmapBars` (`app/hourly-volatility/[asset]/page.tsx:88-168`) as a **hand-rolled CSS-div `height: (e.median_bp / maxMed) * 100 %` grid** — a proportional scalar **structurally identical to the r108 `ScenariosPanel` `(s.p/maxP)*100` that WAS a doctrine-#9 migration**, but on a separate route the r105/r108/r109 sweeps never reached, so it was never in the r110/r111 enumerated ledger.

**Doctrine #8-AND-#9, honestly classified (NOT a re-affirmation, NOT a silent contradiction — meta-r110 ledger refinement).** r116 is primarily **doctrine #8 "more coverage"**: a NEW reusable generic SSOT bar-series component + a NEW genuine consumer for a NEW, DISTINCT, proven-live data dimension (intraday liquidity seasonality by UTC hour — categorically distinct from price-level / range / volume / scenario / correlation, and directly pre-session-relevant: "when this asset actually moves vs sleeps", London-in-progress → NY calibration). It **ALSO** closes a doctrine-#9-class proportional-scalar site (`HeatmapBars`'s `(v/max)*100`) that R59 newly surfaced. The r110/r111 "doctrine-#9 de-accumulation FULLY CLOSED" was **accurate for its enumerated scope** (the microchart-SSOT-consumer coord-math ledger: VolumePanel r105 + ScenariosPanel r108 + confluence-history r109 + the SSOT-internal I3 r111 — the sites the r105/r108/r109 sweeps identified). Per **meta-r110 ("a prior status is a HYPOTHESIS R59 can refine ; an accurate ledger beats a false claim ; disproving/refining a roadmap claim with empirical evidence IS a verified increment")**, r116 honestly **refines the ledger** to `{VolumePanel r105 · ScenariosPanel r108 · confluence-history r109 · I3 r111 · HeatmapBars r116}` and reconciles the r113-close memory (which stated "FULLY CLOSED, no item remaining") to this measured truth — NOT protecting a pre-written claim (lesson #1/#11/#12). This is the r110 doctrine in action, not a reopening: the ledger becomes MORE accurate.

**R53 live-verified (the SHIPPED≠FUNCTIONAL gate, ONE consolidated throttle-aware SSH, 2026-05-19).** `curl 127.0.0.1:8000/v1/hourly-volatility/{EUR_USD,XAU_USD}?window_days=30`: EUR_USD 24/24 entries populated (`n_samples` 720/hr, `best_hour_utc=13` NY-overlap, `worst_hour_utc=2` Asian trough, `median_bp` **0.34→0.77 genuinely varying**) ; XAU_USD 24/24 populated (`median_bp` **0.0→3.8** — incl. a genuine `0.0` hour : a real measured ~0 that passed `n_samples>0`, NOT missing data ; `barFromBaseline` handles it gracefully — `0 ≥ 0` is valid, only a NEGATIVE value or non-positive max throws → a floor bar `max(minH, 0)`, no NaN, the existing `Math.max(2, pct)` behaviour preserved). Series **projected AND populated AND non-degenerate on real prod across 2 assets** — SHIPPED≠FUNCTIONAL avoided BY CONSTRUCTION (the r112/r113 discipline).

**What r116 implements.**

1. **NEW `apps/web2/components/microchart/BarSeries.tsx`** — a pure presentational, generic, reusable SSOT bar-series micro-chart (the bar analogue of the r112 `<Sparkline>`). ALL coordinate math the r105 SSOT: `bandLayout(n, W)` for the categorical columns + `barFromBaseline(i, value, max, layout, plotH)` for each TRUE-0-baseline bar (the design-integrity invariant enforced loud at the SSOT) + `svgCoord` 1-dp. ZERO new coord math (doctrine #9). Per-bar `tones?: string[]` + (r116b review-applied, a11y SHOULD-#1) a sparse `strokes?: (string | undefined)[]` non-hue SHAPE outline — both REUSE caller-provided CSS vars, the component defines NO palette ; per-bar `<title>` ; `role="img"` + `aria-label` ; `< 1`/non-positive-max → null (the graceful FAIL-SAFE discipline) ; thin `"use client"` motion-only draw-in consistent with `Sparkline`/`VolumePanel` house style ; the `<svg>` owns its box (a full-width caller `className` is a documented SANCTIONED `<BarSeries>` pattern, distinct from `Sparkline`'s strict no-caller-sizing — ui-designer Nit-2 applied).
2. **`apps/web2/app/hourly-volatility/[asset]/page.tsx`** — `HeatmapBars`'s hand-rolled CSS-div `(median_bp/maxMed)*100%` grid replaced by `<BarSeries>` fed `entries[].median_bp`, the best/worst/normal tone mapping (`var(--color-bull)` / `var(--color-bear)` / `var(--color-accent-cobalt)`) preserved EXACTLY (the existing encoding REUSED, not a NEW colour encoding — NOT r106-class), the per-hour `<title>` (`UTC HH:00 — median … p75 … n=…`) preserved, the 24 hour labels + best/worst legend preserved. The `SessionAverages` section is byte-untouched. Behavioural parity (same 24-hour seasonality, same best/worst highlight) is a witnessed acceptance criterion alongside the contract test.
3. **`apps/web2/__tests__/microchart.test.ts`** — an additive describe block PINNING the `<BarSeries>` SSOT-composition CONTRACT (NOT a byte-identical-vs-prior proof — the prior was CSS-% divs, a DIFFERENT rendering technology ; the honest distinction, r112/r113-class): given a fixture series + dims, every bar rect is exactly `bandLayout`/`barFromBaseline`/`svgCoord`-composed, 0-baseline (y+height reaches the true baseline), 1-dp, in-viewBox ; **the `median_bp = 0.0` edge** (XAU-witnessed) → a floor bar, no throw, no NaN ; the `<2`/empty → null. Pre-existing tests unchanged (zero regression).
4. **ADR-099 `## Implementation (r116b, 2026-05-19)`** (this) — dated §Impl, NO new ADR (doctrine #9), appended AFTER the spawn-task's part-3/3 §Impl (whose header was disambiguated `r116`→`r116a` per YELLOW-1 — header-only, content byte-untouched). Reviews / Verification written as placeholders then RECONCILED to the MEASURED outcomes (lesson #1 — no forecast).

**Honest scope / ledger (#11, NOT thinned).** r116 = ONE NEW generic SSOT `<BarSeries>` + ONE genuine consumer (hourly-volatility) + the page refactor + the contract test. "More coverage" (doctrine #8) that also refines the doctrine-#9 ledger (HeatmapBars added, meta-r110). DEFERRED, NOT thinned: surfacing the hourly-volatility seasonality on the PRIMARY briefing page (higher mission-value but needs a NEW briefing-page fetch wiring + its own R59 — a separate increment, NOT silently folded) ; the `yield-curve` `CurveChart` non-zero/truncated-baseline + out-of-SSOT coord-math (a REAL design-integrity gap R59 also surfaced — log-x complexity, a separate honest increment) ; further `<Sparkline>`/`<BarSeries>` consumers ; the regime-timeline (still DEFERRED — needs a NEW backend regime-TIME-series projection, the #1 class) ; T4.2 (`prefers-reduced-motion` already clean — only uncertainty-band / calibration-overlay / degraded+empty / no-truncated-axis remain) → T4.3. PRE-EXISTING, NOT r116's, NOT re-scoped (flag-not-fix #11): the r111-spawn-task's r114/r115 (ITS domain, carried-as-ancestors only) ; the r112-flagged header-wide `text-muted` §T4.2 contrast ; the r113-flagged r112-`Sparkline` SR-double-announce a11y backlog.

**Reviews (consolidated single pass — doctrine #14 ; ichor-trader R28 + ui-designer + accessibility-reviewer ALL dispatched — a NEW visual SVG component + a route-page refactor genuinely changes the trading-boundary, design AND a11y surface, protocol not FOMO #17 ; verdicts MEASURED not forecast, lesson #1).**

- **ichor-trader R28 — YELLOW → MERGE, 0 RED, 2 YELLOW APPLIED** (the MEASURED verdict). **Doctrine ruling: the #8-AND-#9 / meta-r110 ledger-refinement framing is HONEST — accept it** : `HeatmapBars`'s `(median_bp/maxMed)*100%` is structurally identical to the r108 `ScenariosPanel` `(s.p/maxP)*100` bona-fide #9 site (test `microchart.test.ts:180`), was genuinely never in the r110/r111 enumerated ledger (those "FULLY CLOSED" claims are scoped to the sites the r105/r108/r109 sweeps reached — `/hourly-volatility` is a separate route), and r116 _refines_ (adds HeatmapBars) rather than _contradicts_ — meta-r110 applied correctly, the ledger becomes strictly more accurate, the inverse of a capricious reopening ; the r113-close "FULLY CLOSED" memory is reconciled in-place = doctrine #11/#1 correct. **ADR-017 CLEAN** : `BarSeries` defines no palette/bias/signal/BUY-SELL ; the best/worst colour map + "Best/Worst hour" legend are PRE-EXISTING + wording-UNCHANGED, descriptive volatility-seasonality CONTEXT not a directional signal ; the opacity→colour-only refinement loses no ADR-017 meaning. The 9 invariants N/A or OK ; SHIPPED≠FUNCTIONAL genuinely avoided (R53). **YELLOW-1 APPLIED**: the duplicate `## Implementation (r116, …)` (the concurrent spawn-task part-3/3 self-labelled r116 + this round) disambiguated header-only → `r116a` (spawn-task) / `r116b` (this) — the unique `§Impl(rN)` ledger-anchor convention restored. **YELLOW-2 APPLIED**: `microchart.ts:27-31` "WHY THIS MODULE EXISTS" R59-corrected (the r110 precedent) — the "FULLY CLOSED" line now scopes to the then-enumerated ledger + records the r116 HeatmapBars refinement, string-only no behavioural code. Code/tests GREEN (zero new coord math, FAIL-SAFE boundary delegating FAIL-LOUD to the SSOT, the contract test honestly the consumer-composition + `0.0`-edge, not a false byte-identical-vs-CSS-div proof ; no code cross-file drift).
- **ui-designer — MERGE-with-changes, 0 Critical ; 1 Important + 1 Nit APPLIED (1 Nit no-action).** **Important-1 APPLIED**: the hour-label row used a `grid` + `gap-0.5` whose CSS track centres drift from the SVG `bandLayout` slot centres (`i*slot+slot/2`) once the 23 gaps redistribute (≈1-2px, worst at the edges) → `gap-0.5` removed (the inline `repeat(24,minmax(0,1fr))` then yields tracks of exactly `width/24` === `slot`, alignment provably correct) + `tabular-nums leading-none` added to the label spans. **Nit-2 APPLIED**: the `BarSeries` docstring now states the full-width caller-`className` divergence from `Sparkline` is a SANCTIONED `<BarSeries>` pattern. Nit-3 (`defaultFill` never rendered here) = acknowledged, no-action (correct generic-component default). The deliberate refinements adjudicated **all sound** : colour-only-at-full-opacity is an _improvement_ (old 0.5-opacity cobalt read as "disabled"/low-contrast) ; the SSOT 0.5px floor vs old 2% is more truthful ("almost nothing happened") ; empty/short parity preserved (host gates first, the `BarSeries` null is a redundant inner FAIL-SAFE) ; a11y idiom + `aria-hidden` label-row + motion draw-in all consistent with the r112 house style.
- **accessibility-reviewer — 0 MUST-FIX ; 1 SHOULD APPLIED + 1 pre-existing→backlog.** **The central 1.4.1 ruling: PASS — colour-only-on-bars is NOT a 1.4.1 failure** : best/worst are conveyed by THREE colour-independent text channels (the SVG `aria-label` names peak/trough hour ; the best/worst legend states both hours+median as text ; the per-bar `<title>` gives every exact value) ; the dropped opacity tier was itself a visual-only redundancy, not a 1.4.1 non-colour cue, so r116 does not weaken the conformant path. **1.4.11 PASS** (bull ≈9.1:1 / bear ≈6.4:1 / cobalt ≈4.5:1 over `--color-bg-surface`, all ≥3:1) ; **1.1.1 / 2.3.3 / structure PASS** (and `BarSeries` correctly uses `m` from `motion/react` under the app-wide `LazyMotion strict` + `MotionConfig reducedMotion="user"` — consistent with the spawn-task's r115 motion-strict fix, no per-component gap). **SHOULD-#1 APPLIED** (r106-class colour-rigor): a non-hue SHAPE cue added — a sparse neutral `var(--color-text-primary)` outline on the best/worst extreme bars (the new `strokes?` prop), so the two actionable bars stay distinct under colour-vision deficiency even when fills collapse. **SHOULD-#2 = PRE-EXISTING → backlog, NOT r116b's** : `--color-text-muted` ≈4.0:1 on surface is the repo-wide §T4.2/`globals.css §5` contrast pattern (the r112-flagged backlog) ; the hour-label row is `aria-hidden` so its sub-min size is not an SC 1.4.3 failure for that row ; flag-not-fix #11, not re-scoped.

**Verification (real numbers — measured on deployed prod, not forecast).**

- **Build gate** (MEASURED, re-run post-review-apply, doctrine #14): `tsc --noEmit` **0** · `eslint --max-warnings 0` (BarSeries.tsx + page.tsx + microchart.test.ts + microchart.ts) **0** · vitest **7 files / 129 tests pass** (r113 baseline 127 + the 2 new r116b `<BarSeries>` consumer-contract tests = 129, zero regression ; an initial over-tight `toBeCloseTo(_,4)` on a `svgCoord`-1-dp-quantised value was self-caught and fixed to a formatted-string `toBe(svgCoord(…))` — the r108/r109/r111 split-honesty discipline) · `next build` **OK** (clean, no ENOENT this round).
- **Deploy (MEASURED)**: `scripts/hetzner/redeploy-web2.sh` additive — Hetzner Linux build clean, `local=200 public=200`, `DEPLOY OK`, LIVE URL **stable** `https://latino-superintendent-restoration-dealtime.trycloudflare.com` (tunnel not restarted, legacy 3030 untouched), no SSH throttle. NB this deploy tar'd HEAD `185dba7` + the uncommitted r116b worktree, so it ALSO carried the spawn-task's r114/r115/r116a prod-defect fixes (apiGet/CSP, React #418, favicon icon.svg) to the live dashboard **as a side-effect — those fixes are the spawn-task's, NOT a r116b authored claim** (lesson #1/#11 — neither caused nor authored ; the spawn-task owns their verification).
- **Real-prod witness (MEASURED — Playwright, deployed public `/hourly-volatility/EUR_USD`, REAL data, REAL asset, doctrine #7)**: the NEW `<BarSeries>` SVG renders **24 bars** from real prod hourly-volatility, viewBox `0 0 480 128` with `width`/`height` === viewBox (svg-owns-box), `<title>` === `aria-label` ("Volatilité médiane par heure UTC — 24 heures, pic 13:00, creux 02:00" — the colour-independent peak/trough text path + factual, ADR-017-neutral ; consistent with the R53 EUR best=13/worst=2). Geometry: **every coord 1-dp** (`svgCoord` through `bandLayout`/`barFromBaseline`), all in-viewBox, **TRUE 0-baseline empirically confirmed** (every non-floor bar `y+height` reaches the 128 baseline — the SSOT no-truncated-axis invariant, not asserted), bars span full width (`x[0]=3.8` … `x[23]=463.8`, +12.4 ≤ 480). 3-tone encoding renders (`var(--color-bull)` best / `var(--color-bear)` worst / `var(--color-accent-cobalt)` ×22 normal) ; **exactly 2 bars carry the r116b a11y-SHOULD-1 non-hue `var(--color-text-primary)` stroke** (the best+worst CVD shape-cue, empirically on the 2 extremes only). The 24 `aria-hidden` hour labels (00…23) render gap-removed (the ui-designer Important-1 alignment fix). Behavioural parity vs the pre-r116b CSS-div presentation confirmed (same 24-hour seasonality, same best/worst highlight, peak 13:00 / trough 02:00). Screenshot captured.
- **Console — honestly scoped (lesson #1 / #11 / r106-a, NO fabricated causation, NOT over-claimed up-side)**: the r116b surface `/hourly-volatility/EUR_USD` showed **0 errors / 0 warnings** this load — the `<BarSeries>` renders cleanly with zero r116b-related console output. The r111-flagged PRE-EXISTING app-wide defects (vendor-chunk `TypeError`, `/` CSP `localhost:8001`, React #418, favicon-404) are on OTHER routes (`/briefing/*`, `/`), NOT this surface and NOT r116b's ; the spawn-task's r114/r115/r116a fixes (carried to prod by this deploy as a side-effect) are **the spawn-task's to verify, NOT re-claimed here as a r116b win** (causation ≠ proof — r116b neither caused nor fixed them).

Voie D + ADR-017 held (pure descriptive volatility-seasonality geometry, no signal) ; additive web2-only deploy ; zero backend / zero migration (alembic still 0050) ; doctrine #9 dated append, no new ADR ; doctrine #8 "more coverage" (NEW generic SSOT `<BarSeries>` + NEW distinct proven-live series) that ALSO honestly refines the doctrine-#9 ledger per meta-r110 (HeatmapBars `(v/max)*100` was a real un-enumerated r108-class site — an accurate ledger beats a re-affirmed "fully closed").

## Implementation (r117, 2026-05-19) — Tier 4: a 2nd `<BarSeries>` consumer on `/hourly-volatility/[asset]` — the `p75_bp` upper-quartile intraday-volatility envelope (doctrine #8 pure "more coverage" : a NEW genuine consumer of the r116 generic SSOT `<BarSeries>` for a NEW DISTINCT proven-live series ; NOT a doctrine-#9 site — no scalar migration) ; the (D) yield-curve `CurveChart` candidate was R59-DISPROVED-as-viable (a genuine log-x trap — recorded, flagged-not-forced)

doctrine-#9 ledger = {VolumePanel r105 · ScenariosPanel r108 · confluence-history r109 · I3 r111 · HeatmapBars r116} (refined-not-closed, meta-r110). r117 is **purely doctrine #8 "more coverage"** — a NEW genuine consumer of the r116 generic `<BarSeries>` (zero new component, ZERO new coord math — doctrine #9 untouched) for a NEW, DISTINCT, proven-live series ; it is NOT a #9 migration (no hand-rolled scalar — the page's only such site, HeatmapBars, was closed r116).

**R59 inspect-first — the menu-default is itself R59-subject (meta-r110/r112/r113/r116).** A read-only researcher R59 evaluated (D) yield-curve `CurveChart` fix / (B′) more consumers / (E) hourly-vol-on-briefing / T4.2. **(D) was R59-DISPROVED-as-viable**: `app/yield-curve/page.tsx:149-152` `CurveChart` `sx` is a GENUINE log-x map (`(log(x+0.01)−log(xMin+0.01))/(log(xMax)−log(xMin+0.01))`, self-labels "log-x tenor" `:164`) and `:147-148` a non-zero/truncated y-baseline (`yMin=min−0.1`). The r105 SSOT has NO log primitive (`microchart.ts:42-44` `linScale` is the canonical _linear_ base) ; a faithful migration would require a NEW log-scale coord primitive = new coord-math = exactly the **r110-class forced-bad-migration the project rejects** (an accurate "skip" beats a forced bad migration). (D) is therefore **DEFERRED, flagged-not-forced** — the yield-curve truncated-axis + out-of-SSOT coord-math remains an honest backlog item (it needs either a sanctioned NEW log primitive ADR or a deliberate re-scope, NOT a forced r117 migration ; the disproof itself is a verified part of this round, ledger #11, meta-r110). (E) = HIGH SHIPPED≠FUNCTIONAL risk (a NEW briefing SSR fetch, redundant surface). (T4.2) = non-defects/speculative. **(B′) is the R59-sound pick**: `HourlyVolEntry.p75_bp` (`lib/api.ts:1074`, directly re-verified — `HourlyVolEntry{hour_utc,median_bp,p75_bp,n_samples}`) is a DISTINCT proven-live numeric series ALREADY fetched by the existing `/hourly-volatility/[asset]` page (the SAME `HourlyVolOut` the r116 `<BarSeries>` already consumes for `median_bp`) but currently rendered ONLY as per-bar `<title>` tooltip TEXT (`page.tsx` `titles` array), NEVER charted.

**R53 live-verified (the SHIPPED≠FUNCTIONAL gate, ONE consolidated throttle-aware SSH, 2026-05-19).** `curl 127.0.0.1:8000/v1/hourly-volatility/{EUR_USD,XAU_USD}?window_days=30`: `p75_bp` 24/24 entries populated — EUR_USD **0.6→1.28** (median 0.34→0.77), XAU_USD **0.03→6.35** (median 0.0→3.8) ; `p75_bp ≥ median_bp` for ALL 24/24 on BOTH assets (the statistical invariant holds) ; **p75 is GENUINELY DISTINCT from median — 0/24 identical on BOTH assets, max(p75−median)=0.52 (EUR) / 2.55 (XAU)** (the per-hour p75/median RATIO varies — that variation IS the new information : median = the typical hourly rhythm, p75 = the upper-quartile "how big the busy hours get" volatility envelope, directly pre-session-relevant for risk calibration). Series **projected AND populated AND non-degenerate AND empirically NOT-a-duplicate of the r116 median chart** (the r113 `XvsYIdenticalPoints=false` discipline, here proven at the data level pointwise, re-confirmed at the witness on rendered coords) — SHIPPED≠FUNCTIONAL avoided BY CONSTRUCTION (same page, same fetch, same proven-rendering `<BarSeries>`, just a 2nd distinct series).

**What r117 implements.**

1. **`apps/web2/app/hourly-volatility/[asset]/page.tsx`** — a NEW section rendering a 2nd `<BarSeries>` fed `entries[].p75_bp` with `max` = max p75 over populated, a SINGLE neutral uniform tone — **MEASURED shipped: `var(--color-text-secondary)`** (the `<BarSeries>` documented `defaultFill`, NO `tones`/`strokes` passed — the ui-designer Important-1 review changed this from the initially-drafted `var(--color-accent-cobalt)`: that token is the median chart's own "normal-bar" colour, so the two stacked 24-bar charts' bodies were pixel-identical ; the BarSeries default `text-secondary` is distinct-from-median-cobalt, a11y-stronger, ADR-017-most-neutral, and is the component's documented default — reconciled to the measured shipped value, lesson #1) ; NO best/worst, NO stroke ("best/worst hour" is a median-only construct computed by the backend on median ; reusing it for p75 would be semantically wrong) ; its own factual `aria-label` + per-bar `<title>` ("UTC HH:00 — p75 X bp · median Y bp · n=Z") + a 24-hour `aria-hidden` gap-removed label row (the r116 ui-designer Important-1 alignment idiom) + a distinct heading (`mb-3` rhythm-parity with the median `<h2>` — ui-designer Important-2) + a tightened one-line factual descriptor that makes the median-vs-p75 read clear BY STRUCTURE (ADR-017 #11 — clarity by structure, no "méthodologie" encart ; ui-designer Nit-3 single-clause). The uniform single neutral tone (vs the median chart's bull/bear/cobalt + 2 stroked extremes) is a DELIBERATE visual differentiator that is itself meaningful (p75 has no best/worst concept) — it also resolves the r113/r116 "two near-identical charts" concern structurally (the ui-designer Important-1 token change makes that structural distinction unmistakable: neutral-grey envelope vs cobalt/bull/bear median). `SessionAverages` + the r116 median `HeatmapBars` byte-untouched (ichor-trader-verified — the only diffs are the 1-line render-wiring insert + the NEW `Percentile75Bars` fn + the header docstring).
2. **`apps/web2/__tests__/microchart.test.ts`** — an additive describe block PINNING the r117 p75 CONSUMER contract (NOT byte-identical-vs-prior — a NEW consumer ; the honest distinction, r112/r113/r116-class): the `entries.map(e=>e.p75_bp)` derivation ≥ 0 ; `p75 ≥ median` pointwise on a realistic R53-witnessed-shape fixture ; the p75 series is a well-formed SSOT-composed `<BarSeries>` input (`bandLayout`/`barFromBaseline`/`svgCoord`, 1-dp, in-viewBox, TRUE 0-baseline) ; **p75 ≠ median pointwise** (the empirical not-a-duplicate property, at the data-derivation level). Pre-existing tests unchanged (zero regression).
3. **ADR-099 `## Implementation (r117, 2026-05-19)`** (this) — dated §Impl, NO new ADR (doctrine #9), appended AFTER §Impl(r116b) (the §Impl headers RE-GREP'd immediately before the append — the r116 lesson). Reviews / Verification written as placeholders then RECONCILED to the MEASURED outcomes (lesson #1 — no forecast).

**Honest scope / ledger (#11, NOT thinned).** r117 = ONE NEW genuine `<BarSeries>` consumer (p75 envelope) + the contract test. Pure "more coverage" (doctrine #8) — NOT a #9 migration (no scalar ; the ledger is unchanged {…HeatmapBars r116}). DEFERRED, NOT thinned: **(D) the `yield-curve` `CurveChart` log-x + truncated-y + out-of-SSOT coord-math** — a REAL design-integrity gap that needs a sanctioned NEW log-scale primitive ADR or a deliberate re-scope, NOT a forced migration (R59-disproved-as-r117-viable, recorded — meta-r110/r110 "an accurate skip beats a forced bad migration") ; (E) hourly-vol on the PRIMARY briefing page (needs a NEW briefing fetch wiring + its own R59 — a separate increment) ; further consumers ; the regime-timeline (still DEFERRED — needs a NEW backend regime-TIME-series projection, the #1 class) ; T4.2 (`prefers-reduced-motion` already clean — uncertainty-band / calibration-overlay / degraded+empty remain) → T4.3. PRE-EXISTING, NOT r117's, NOT re-scoped (flag-not-fix #11): the r111-spawn-task's r114/r115/r116a (ITS domain) ; the r112-flagged header/label `text-muted` §T4.2 contrast ; the r113-flagged `Sparkline`/`BarSeries` `role=img`+`aria-label`+`<title>` SR double-announce a11y backlog.

**Reviews (consolidated single pass — doctrine #14 ; ichor-trader R28 + ui-designer + accessibility-reviewer ALL dispatched — a NEW visual chart section genuinely changes the trading-boundary, design AND a11y surface, protocol not FOMO #17 ; verdicts MEASURED not forecast, lesson #1).**

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 1 YELLOW (doc-only) APPLIED** (MEASURED verdict). All three adjudications resolve in r117's favour: **(1) doctrine-#8 pure-coverage CORRECT** — zero new coord math (all geometry stays `barFromBaseline`/`bandLayout` in `BarSeries.tsx`, the r105 SSOT), `maxP75=Math.max(...)` is a domain-max for the SSOT `max` prop NOT a `(v/max)*100` proportional map, the ledger `{VolumePanel r105·ScenariosPanel r108·confluence-history r109·I3 r111·HeatmapBars r116}` correctly unchanged — additive coverage of a NEW distinct series, not de-accumulation ; **(2) the (D) R59-disproof is HONEST not work-avoidance** — the exact disproof anchors cited (`yield-curve/page.tsx:149-152` genuine log-x, `microchart.ts:42-44` linear-only), a faithful (D) would require inventing a log primitive = the r110-class forced-bad-migration the doctrine rejects, and r117 still ships a genuine alternative (B′) — the codified meta-r110 pattern ; **(3) ADR-017 CLEAN** — grep `BUY|SELL|order|position|signal|entry|target|stop-loss|take-profit` (case-insensitive) on the whole file = ZERO matches ; tone genuinely uniform-neutral (no `tones`/`strokes`), prose descriptive not imperative, aria/titles factual — descriptive volatility CONTEXT, the same class as the r116 median chart. **YELLOW-1 APPLIED**: the `page.tsx:1-5` file-header docstring was stale (omitted the p75 section — the r101/r103 stale-docstring drift class) → rewritten to name both the median heatmap + the p75 envelope and clarify best/worst is median-only. **Reconcile-not-blindly (r96/r105)**: ichor-trader reviewed the initially-drafted `var(--color-accent-cobalt)` shape ; the ui-designer Important-1 then changed the p75 fill to the BarSeries default `var(--color-text-secondary)`. The ADR-017 ruling is **token-agnostic re uniform-neutral and holds _a fortiori_** — `text-secondary` is MORE neutral than an accent (it is the component's documented neutral default, the same neutral the median chart's price-overlay uses) ; the verdict stands, strengthened.
- **ui-designer — MERGE-with-changes, 0 Critical ; 2 Important + 1 Nit APPLIED.** **Important-1 APPLIED** (highest-leverage): the p75 chart initially used `defaultFill="var(--color-accent-cobalt)"` = the SAME token as the median chart's 22 "normal" bars, so the two stacked 24-bar bodies were pixel-identical and could blur (the heading/outlier differentiators alone were thin) → the `defaultFill` override was REMOVED so the p75 chart falls back to the `<BarSeries>` documented default `var(--color-text-secondary)` (a distinct neutral-grey "envelope" reading, unmistakable vs the cobalt/bull/bear median — no new token introduced, the minimal honest fix). **Important-2 APPLIED**: the p75 `<h2>` had no margin vs the median `<h2>`'s `mb-4` → `mb-3` added (+ the redundant descriptor `mt-1` dropped so a single source owns the gap) — the two section headers now share visual rhythm. **Nit-3 APPLIED**: the descriptor's semicolon-nested parenthetical (a "mini-méthodologie") tightened to a single clause ("75ᵉ centile … — le haut de fourchette intra-horaire, vs le rythme typique de la heatmap médiane ci-dessus") — same information, clarity by structure (ADR-017 #11). Confirmed-good (no-action): BarSeries contract unchanged + uniform fill intentional/supported ; no best/worst legend correct (median-only construct) ; responsive + house-style consistent ; empty/short FAIL-SAFE (`return null`, HeatmapBars carries the single message) verified — no orphan gap/double message.
- **accessibility-reviewer — 0 MUST-FIX ; 2 SHOULD-FIX, both PRE-EXISTING → existing backlog (flag-not-fix #11, NOT re-scoped).** **The central ruling: the single-uniform-tone p75 chart has NO 1.4.1 colour concern — ruled explicitly, BY CONSTRUCTION** (no `tones`/`strokes` ⇒ all 24 rects one fill ⇒ zero information encoded by colour ; unlike the r116 median chart it has no colour-encoding dependency at all). 1.4.11 PASS (the uniform fill over `--color-bg-surface` clears the 3:1 graphical floor — measured on the as-reviewed token ; the Important-1 change to the BarSeries default `text-secondary` keeps it ≥3:1, re-confirmed at the witness). 1.1.1 PASS (factual distinct `aria-label` + per-bar `<title>` ; two adjacent `role="img"` charts read as two clearly-named images, supplementary — descriptor `<p>` + SessionAverages carry the facts textually). 2.3.3 PASS (app-wide `MotionConfig reducedMotion="user"` + `globals.css` guard ; no per-component gap). Heading structure/landmarks PASS (`<h1>` → 3 sibling `<h2>` document-order, each `<section>` `aria-labelledby` its own id). **SHOULD-FIX (PRE-EXISTING, NOT r117-introduced)**: (a) the `<h2>` `text-text-muted` ≈4.0:1 is the IDENTICAL class on all 3 sibling headings (heatmap/p75/session) — the repo-wide §T4.2 muted-text backlog, r117 merely mirrors the established sibling-heading style ; (b) the `<BarSeries>` `aria-label`+child-`<title>` SR double-announce is r116-origin component-level (= the r113-flagged backlog). Both flag-not-fix #11, routed to the existing §T4.2 / component-a11y backlogs, NOT re-scoped into r117.

**Verification (real numbers — measured on deployed prod, not forecast).**

- **Build gate** (MEASURED, re-run post-review-apply, doctrine #14): `tsc --noEmit` **0** · `eslint --max-warnings 0` (page.tsx + microchart.test.ts) **0** · vitest **7 files / 132 tests pass** (r116 baseline 129 + the 3 new r117 p75 consumer-contract tests = 132, zero regression) · `next build` **OK** (clean, no ENOENT).
- **Deploy (MEASURED)**: `scripts/hetzner/redeploy-web2.sh` additive — Hetzner Linux build clean, `local=200 public=200`, `DEPLOY OK`, LIVE URL **stable** `https://latino-superintendent-restoration-dealtime.trycloudflare.com` (tunnel not restarted, legacy 3030 untouched), no SSH throttle.
- **Real-prod witness (MEASURED — Playwright, deployed public `/hourly-volatility/EUR_USD`, REAL data, REAL asset, doctrine #7)**: the page now renders TWO `role="img"` `<BarSeries>` SVGs. (1) The r116 median chart **BYTE-UNCHANGED — no regression**: 24 rects, viewBox `0 0 480 128`, distinctFills `[cobalt, bear, bull]` (3-tone preserved), **2 stroked** best/worst extremes preserved, aria-label "…pic 13:00, creux 02:00" (= R53 EUR). (2) The NEW r117 p75 chart: 24 rects, viewBox `0 0 480 128`, **distinctFills = [`var(--color-text-secondary)`] — a SINGLE uniform neutral tone (the ui-designer Important-1 token change applied & LIVE-confirmed: NOT the median's cobalt — unmistakably distinct)**, **strokedCount = 0** (correct — p75 has no best/worst), **every coord 1-dp**, all in-viewBox, **TRUE 0-baseline empirically confirmed** (every non-floor bar `y+height` reaches the 128 baseline — the SSOT no-truncated-axis invariant, not asserted), aria-label "Volatilité 75e centile (enveloppe) par heure UTC — 24 heures" (factual, ADR-017-neutral, no peak/trough — no best/worst concept). **`pVsM_identicalYVectors = false` — the p75 and median bar y-vectors RENDER GENUINELY DIFFERENT** (median first/lastY 62.2/76.0 vs p75 49.8/57.2 — the p75 bars are taller because p75 ≥ median by the statistical invariant ; empirical proof r117 is NOT an on-screen duplicate of the r116 chart, the r113 `XvsYIdenticalPoints=false` discipline on rendered prod coords). Headings render structurally distinct ("Heatmap 24h · UTC" vs "Enveloppe p75 · 24h UTC"). Screenshot captured.
- **Console — honestly scoped (lesson #1 / #11 / r106-a, NO fabricated causation)**: the r117 surface `/hourly-volatility/EUR_USD` showed **0 errors / 0 warnings** this load — the 2nd `<BarSeries>` renders cleanly with zero r117-related console output. The r111-flagged PRE-EXISTING app-wide defects are on OTHER routes (`/briefing/*`, `/`), NOT this surface and NOT r117's ; the spawn-task's r114/r115/r116a fixes (already on origin as ancestors via the r116b push, carried to prod by this deploy chain) are the spawn-task's to verify, NOT re-claimed here (causation ≠ proof — r117 is purely additive, neither caused nor fixed them).

Voie D + ADR-017 held (pure descriptive volatility-envelope geometry, no signal) ; additive web2-only deploy ; zero backend / zero migration (alembic still 0050) ; doctrine #9 dated append, no new ADR ; doctrine #8 pure "more coverage" (a NEW genuine SSOT consumer for a NEW distinct proven-live series — NOT a #9 ledger change) ; (D) yield-curve R59-DISPROVED-as-r117-viable (a genuine log-x trap — an accurate flagged-not-forced skip, the disproof a verified increment per meta-r110).

## Implementation (r118, 2026-05-19) — Tier 4: the `yield-curve` `CurveChart` de-accumulation onto the EXISTING `linScale`+`svgCoord` SSOT (a doctrine-#9 consumer-migration of a never-enumerated coord-scaling site ; the r117 "(D) needs a NEW log primitive" conclusion was an incomplete-analysis hypothesis R59-corrected here — the log-x decomposes into a caller `Math.log` domain-transform ∘ the existing `linScale`, NO new primitive ; and the prompt's "truncated y-baseline" framing was R59-DISPROVED — a line chart legitimately uses a zoomed domain, preserved exactly)

**R59 inspect-first — the menu-default is itself R59-subject (meta-r110/r112/r113/r116/r117), and a prior round's disproof is itself a hypothesis a deeper R59 refines (r67/r110 class).** A read-only researcher R59 inspected the REAL shapes (`app/yield-curve/page.tsx` full, `lib/microchart.ts` full, `__tests__/microchart.test.ts` split-honesty idiom) + R53 live-verified `/v1/yield-curve`. Two prompt/r117 framings were **DISPROVED on the real code** (meta-r110 — disproving a false roadmap claim IS a verified increment, the most honest kind):

1. **The "non-zero/truncated y-baseline `yMin=min−0.1` violates the `barFromBaseline` no-truncated-axis invariant" framing is WRONG.** `CurveChart` renders a **LINE/curve** (`page.tsx:181` `<path d=… fill="none" stroke=…/>` + per-point `<circle>`), NOT bars. The SSOT's no-truncated-axis / TRUE-0 invariant is **explicitly bar-scoped** (`microchart.ts:56-59` "**0-baseline bars** … `barFromBaseline`"). A forced 0-baseline would flatten a live 3.82 %–5.14 % Treasury curve into a visually useless near-horizontal line — the ±0.1 head/foot padding is correct line-chart practice. r118 therefore **preserves the zoomed `[yMin,yMax]` domain exactly** via `linScale(yMin, yMax, H−PAD, PAD)` (the r108 inverted-range idiom, the SSOT's own `linScale(0,10,200,0)→100` tested case) — it does NOT migrate y onto `barFromBaseline` and does NOT touch the legitimate zoom.
2. **The r117 "(D) needs a sanctioned NEW `logScale` SSOT primitive = new coord-math = the r110-class forced-bad-migration" conclusion was an incomplete-analysis hypothesis.** r117 correctly observed there is no literal drop-in `linScale` call and correctly refused a _naive_ migration ; but it did not algebraically decompose the inline form. R59 did: the inline `sx` `PAD + ((log(x+0.01) − log(xMin+0.01)) / (log(xMax) − log(xMin+0.01))) · (W−2·PAD)` is **exactly** `linScale(Math.log(xMin+0.01), Math.log(xMax), PAD, W−PAD)(Math.log(x+0.01))`. The `Math.log` is a **domain transform** (which value to scale — the caller's concern, the +0.01 a near-0-tenor guard), **NOT a scale** ; the _scale_ (normalize-a-value-in-a-domain-to-a-pixel-range) is linear-in-log-space = exactly `linScale`. This is the established SSOT-consistent composition pattern — `bandSeriesPolyline` itself composes `linScale` internally (r111 I3), and r113 chose which scalar to plot (amplitude vs price) at the caller. A NEW `logScale` primitive is therefore **NOT needed and would be the r110-class over-abstraction the project rejects** (cf. `microchart.ts:18-20` "`linScale(0,1,0,-1)` … absurd over-abstraction"). No new primitive, no new ADR (doctrine #9 — this dated §Impl append).

**R53 live-verified (the SHIPPED≠FUNCTIONAL gate, ONE consolidated throttle-aware SSH, 2026-05-19).** `curl 127.0.0.1:8000/v1/yield-curve`: 10 tenor points, **8/10 populated** with real `yield_pct` (`1Y=3.82 … 30Y=5.12`, `observation_date 2026-05-15`, `shape="normal"`, sources `FRED:DGS1…DGS30,DFII10`) ; `3M`/`6M` `yield_pct:null` (FRED `DTB3`/`DGS6MO` not ingested — the page already `.filter(p=>p.yield_pct!==null)` so the rendered curve is the 8 populated tenors, `tenor_years` `1→30`, a genuine ~30× log-x span on the live data — log-x is substantively warranted, not cosmetic). The page renders **REAL live data** on prod (not the seed fallback) — SHIPPED≠FUNCTIONAL satisfied. NB the migration is a pure data-agnostic coord refactor: same data ⇒ same curve, proven byte-identical/≤1-ULP (the r105/r108/r109 refactor discipline) — functionality is preserved BY CONSTRUCTION, the witness confirms it on the live surface.

**Classification: doctrine-#9 de-accumulation, NOT #8 "more coverage".** This is a consumer-migration of a hand-rolled coord-scaling site onto the existing SSOT — the r108 `ScenariosPanel` / r109 `confluence-history` / r116 `HeatmapBars` class, NOT the r112/r113/r117 additive-new-consumer class. `CurveChart` was a **never-enumerated** coord-scaling site on the **never-swept `/yield-curve` route** (the r105/r108/r109 sweeps never reached it ; the §Impl(r110) "COMPLETE at r109" was scoped to the _then-enumerated_ ledger, refined r116 for `HeatmapBars`). The microchart docstring itself anticipated this exact event (`microchart.ts:36-40` "a future R59 on a never-enumerated route can refine it again"). The doctrine-#9 ledger is honestly refined (meta-r110, NOT "fully closed" re-affirmed): **{VolumePanel r105 · ScenariosPanel r108 · confluence-history r109 · I3 r111 · HeatmapBars r116 · CurveChart r118}**.

**What r118 implements.**

1. **`apps/web2/app/yield-curve/page.tsx`** — `CurveChart`'s hand-rolled `sx`/`sy`/path-format migrated onto the SSOT, byte-for-byte algebraically-equivalent: `const sxLog = linScale(Math.log(xMin + 0.01), Math.log(xMax), PAD, W - PAD); const sx = (x:number) => sxLog(Math.log(x + 0.01));` (the asymmetric epsilon — `Math.log(xMax)` has NO `+0.01` while the other two log terms do, `page.tsx:151` pre-r118 — is **preserved exactly** because it lives entirely in the caller's three `Math.log` domain arguments, NOT in `linScale` ; byte-identity preserved) ; `const sy = linScale(yMin, yMax, H - PAD, PAD);` (the legitimate ±0.1 zoom preserved exactly — see disproof #1) ; the path coords `.toFixed(1)` → `svgCoord` (the single SSOT formatting authority). Imports `{ linScale, svgCoord }` from `@/lib/microchart` (RSC-safe pure module — `microchart.ts:49-53` ; `page.tsx` is an `async` Server Component, no `"use client"` leak, doctrine #5). The `points.length===0` guard, the `.filter`, the seed fallback, the SVG markup, the spreads strip, the table — all byte-untouched (the only diffs are the 4 scale/format lines + the 1 import line).
2. **`apps/web2/lib/microchart.ts`** — the docstring ledger (`:30-40`) refined to add `CurveChart r118` (the r116 precedent — the SSOT self-documents its own consumer ledger ; doc-only, local/reversible/additive).
3. **`apps/web2/__tests__/microchart.test.ts`** — an additive describe block PINNING the r118 migration CONTRACT via the **r109/r111 split-honesty idiom**, NOT byte-identical-flattened: builds the VERBATIM pre-r118 inline `sx`/`sy`/`.toFixed(1)` path on a realistic R53-witnessed fixture (the 8 live tenors `1Y=3.82…30Y=5.12`, 2026-05-15) + the r118 SSOT form, then asserts (a) raw `sx` ≤1-ULP `toBeCloseTo(_,9)` (multiply-order, `(v−dMin)·k` vs `(Δ/span)·range` — NOT bit-identical, the honest split never flattened), (b) raw `sy` ≤1-ULP `toBeCloseTo(_,9)`, (c) the `svgCoord`-formatted path string **bit-identical** `toBe` (the ≤1-ULP raw delta cannot cross a `.toFixed(1)` 0.1 boundary except on an exact `.x5` tie — the r109/r111 path-format precedent, PROVEN on the live-data fixture not assumed), (d) the path is well-formed (starts `M`, all coords 1-dp, in-viewBox — the r113/r117 well-formed discipline). Pre-existing tests unchanged (zero regression).
4. **ADR-099 `## Implementation (r118, 2026-05-19)`** (this) — dated §Impl, NO new ADR, NO new primitive (doctrine #9), appended AFTER §Impl(r117) (the §Impl headers RE-GREP'd immediately before the append AND the live HEAD/origin re-verified — the r116 permanent lesson). Reviews / Verification written as placeholders then RECONCILED to the MEASURED outcomes (lesson #1 — no forecast).

**Honest scope / ledger (#11, NOT thinned).** r118 = ONE consumer-migration (`CurveChart` → existing `linScale`+`svgCoord` SSOT) + the split-honesty contract test + the ledger-refine doc + the meta-r110 double-disproof recorded. Pure de-accumulation (doctrine #9) — NO new component, NO new primitive, NO new ADR, NO migration of the legitimate y-zoom, NO behavior/pixel change (a refactor proven zero-behaviour-change, not assumed). **FLAG-NOT-FIXED (#11, NOT r118's, recorded NOT acted-on)**: the epsilon-asymmetry quirk (`Math.log(xMax)` missing the `+0.01` the other two log terms carry, pre-r118 `page.tsx:151`) is a pre-existing **semantic** question (it very slightly compresses the long end vs a symmetric `log(xMax+0.01)`) — fixing it would change rendered pixels = a behavior change requiring its own decision, NOT a refactor ; r118 **preserves it exactly** (byte-identity demands it) and flags it as a separate backlog item (the r117 "a real alternative beats forcing / a make-it-distinct fix must not silently change behaviour" lesson). Also flag-not-fix, NOT re-scoped: the r112-flagged header/label `text-muted` §T4.2 contrast (the `<h2>`/axis-label `text-text-muted` here is the identical repo-wide sibling style) ; the r111-spawn-task's r114/r115/r116a (ITS domain, on origin as ancestors) ; the `delta_bps_24h` always-0 (`page.tsx:51` "deferred — requires t-1 snapshot", a pre-existing backend-projection gap, the #1 class, NOT a Tier-4 frontend item) ; the `page.tsx:174` `aria-label` raw-`yield_pct`-vs-`.toFixed(2)` SR numeric-drift (the ichor-trader R28 YELLOW-1 + ui-designer Nit-b — pre-existing, untouched by a coord-refactor, routed to the §T4.2/component-a11y backlog).

**Reviews (consolidated single pass — doctrine #14 ; ichor-trader R28 + ui-designer + accessibility-reviewer ALL dispatched — a visual chart surface's coord-math changes even though the rendered pixels are proven invariant ; protocol not FOMO #17 ; verdicts MEASURED not forecast, lesson #1).**

- **ichor-trader R28 — GREEN, MERGE, 0 RED, 2 YELLOW (both doc-only / non-blocking) — MEASURED.** The reviewer independently hand-verified the core math: the inline `oldSx` IS algebraically `linScale(log(xMin+0.01), log(xMax), PAD, W−PAD)(log(x+0.01))` (`Δ·k` vs `(Δ/span)·range` ⇒ ≤1-ULP multiply-order, NOT bit-identical — the `toBeCloseTo(_,9)` claim correct, honestly split not flattened) ; the domain-origin `sx(xMin)→PAD` / `sy(yMin)→H−PAD` `toBe` analytic-exacts hold exactly. All 5 adjudications resolve in r118's favour: **(1) ADR-017 (#11) CLEAN** — the only `(?i)signal` hit is the pre-existing `page.tsx:102` French `MetricTooltip` récession-education prose, NOT r118's (r118 touches only the import + `sx`/`sy`/`path`), zero signal language introduced ; **(2) #9-not-#8 classification HONEST/correct** — a hand-rolled coord-scaling site migrated onto the EXISTING SSOT, no new primitive = textbook r108/r109/r116-class de-accumulation, "never-enumerated on the never-swept `/yield-curve` route" grep-confirmed accurate, not overclaiming ; **(3) the meta-r110 double-disproof SOUND and non-ego** — the y-baseline disproof correct (`<path fill="none">`+`<circle>` = a LINE chart, the no-truncated-axis invariant explicitly bar-scoped `microchart.ts:66-69`, a forced 0-baseline on a 3.82–5.14 % curve = a useless flat line), and recording r117's "needs a new logScale primitive" conclusion as an incomplete-analysis hypothesis a deeper R59 refines is the correct non-ego framing (the r110 precedent — disproving a false roadmap claim is itself a verified increment) ; **(4) the epsilon flag-not-fix CORRECT** — the asymmetric `+0.01` lives entirely in the caller's three `Math.log` domain args, byte-identity _demands_ it be preserved exactly, fixing it = a pixel/behavior change out of a zero-behaviour-change refactor's scope ; **(5) split-honesty GENUINE** — the test pins exactly the r108/r109/r111 discipline (raw `toBeCloseTo(_,9)` NOT flattened, domain-origin `toBe` analytic-exact, formatted path `toBe` bit-identical, the `[0,W]×[0,H]` well-formed bounds correctly chosen + the epsilon-overshoot honestly commented). **YELLOW-1 (PRE-EXISTING, NOT r118's, flag-not-fix is the correct call — itemized for the ledger only)**: `page.tsx:174` `aria-label` interpolates the raw `yield_pct` float (e.g. `3.82`) while every visible label uses `.toFixed(2)` — a cosmetic SR numeric-drift, untouched by r118 (a coord-refactor), routed to the §T4.2/component-a11y backlog NOT re-scoped. **YELLOW-2 (the round's own discipline, not a new requirement)**: the ADR §Impl(r118) Reviews/Verification placeholders must be reconciled to real measured numbers before merge — this very reconcile (Reviews now measured ; Build/Deploy/Witness measured below).
- **ui-designer — MERGE, 0 Critical, 0 Important, 3 Nit (all PRE-EXISTING flag-not-fixed) — MEASURED.** Read `page.tsx` (311 lines) fully ; independently re-derived the `sy = linScale(yMin,yMax,H−PAD,PAD)` ≡ inline algebra (range-delta `−(H−2·PAD)=−180`, base `H−PAD`, ≤1-ULP multiply-order, the r108/r109/r111 class) and confirmed the test fixture embeds the verbatim pre-r118 inline + asserts `newPath===oldPath` bit-identical across all 3 fixtures + domain-origin `toBe`. Every markup/token/layout element (`<svg>`/`<line>`/`<path>`/`<circle>`/`<text>`, all `var(--color-*)` tokens, `viewBox`, `role="img"`, `aria-label`, heading rhythm, `MetricTooltip`, offline pill, `SpreadsStrip`, `CurveTable`) verified byte-untouched ; every `sx`/`sy` call site (`cx`/`cy` circles, tenor-label `x`, the 3 y-tick `y={sy(y)}`, the `path` d-attr) verified still correct with the new `(v)=>number` signature. The page.tsx:150-155 comment block ruled accurate, concise, load-bearing (not noise). 3 Nits ALL pre-existing, NOT introduced by r118, flag-not-fixed: (a) the repo-wide `text-[var(--color-text-muted)]` §T4.2 low-contrast labels (preserved verbatim) ; (b) the `page.tsx:174` raw-`yield_pct` `aria-label` (= the same drift ichor-trader YELLOW-1) ; (c) the asymmetric-epsilon last-x overshoot beyond `W−PAD`, pre-existing and explicitly preserved/tested. **Conclusion: a genuine pixel-invariant coordinate-math refactor, the rendered chart provably byte-identical, no design delta.**
- **accessibility-reviewer — PASS (zero a11y delta), 0 MUST-FIX, 2 SHOULD-FIX (both PRE-EXISTING, flag-not-fixed) — MEASURED.** Ruled explicitly with evidence that r118 is a pixel-invariant refactor confined to the import + `sx`/`sy`/`path` (3 hunks) ; every a11y-bearing element (`role="img"`, the `aria-label`, the `<text>` decorative-by-`role=img`-containment, the `<h1>`/`<h2>` structure, the `CurveTable` numeric text-equivalent, `SpreadsStrip`, the offline pill) is byte-untouched and outside the diff ; the `aria-label` remains accurate post-refactor (endpoints/labels/yields unchanged, only proven-invariant pixel coords changed). **SHOULD-FIX (PRE-EXISTING repo backlog, present identically before r118, NOT pulled into this refactor)**: (#1) the `fill="var(--color-text-muted)"` axis/label sub-4.5:1 contrast = the repo-wide §T4.2 muted-text recalibration (WCAG 1.4.3/1.4.11) ; (#2) the single-cobalt-stroke curve's shape/inversion narrative absent from the `aria-label` = the r113 component-a11y backlog (WCAG 1.4.1/1.1.1), mitigated by the `CurveTable` numeric equivalent + `SpreadsStrip` text `sig` so NOT a block. Both routed to the existing §T4.2 / r113-component backlogs, NOT re-scoped into r118.

**Verification (real numbers — measured on deployed prod, not forecast).**

- **Build gate (MEASURED, doctrine #14)**: `tsc --noEmit` **0** · `eslint --max-warnings 0` (`app/yield-curve/page.tsx` + `lib/microchart.ts` + `__tests__/microchart.test.ts`) **0** · vitest **7 files / 147 tests pass** (r117 baseline 132 + the 15 new r118 split-honesty tests [3 fixtures × 5 `it`] = 147, **zero regression** — the reviews induced ZERO code edits [all RED/Critical/MUST-FIX = 0 ; all YELLOW/Nit pre-existing flag-not-fix], so the gated shape IS the reviewed shape ; re-confirmed on the committed post-prettier shape) · `next build` **OK** (clean, `/yield-curve` ○ Static present, no ENOENT).
- **Deploy (MEASURED)**: `scripts/hetzner/redeploy-web2.sh` additive — Hetzner Linux build clean (`/yield-curve` ○ Static), Step-4 `(re)start ichor-web2` (tunnel NOT restarted, legacy 3030 untouched), Step-5 `RESULT: local=200 public=200`, `DEPLOY OK`, LIVE URL **stable** `https://latino-superintendent-restoration-dealtime.trycloudflare.com`, ONE consolidated SSH (no throttle).
- **Real-prod witness (MEASURED — Playwright, deployed public `/yield-curve`, doctrine #7)**: the migrated `CurveChart` renders a `role="img"` SVG with a `<path fill="none">` `d` = `M 50.0 70.5 L 138.0 86.8 L 227.2 113.4 L 317.1 119.5 L 369.8 164.5 L 436.3 203.4 L 480.2 209.5 L 526.7 209.5 L 617.1 160.5 L 670.0 168.6` — **10 coord pairs, all 1-dp (`/^-?\d+\.\d$/`), in `[0,W]×[0,H]`, M-start** ; 10 `<circle>` markers + 13 `<text>` (10 tenor labels + 3 y-ticks `4.08%/4.52%/4.96%`) ; `aria-label` intact. **The byte-identical proof, ON THE DEPLOYED SURFACE**: every one of the 10 x + 10 y coords was re-derived BY HAND from the VERBATIM pre-r118 inline `oldSx`/`oldSy` on the actually-rendered data and **matches the deployed path EXACTLY** — including the flagged epsilon-asymmetry overshoot (last `x=670.0`, ratio `>1` because the `xMax` log term has no `+0.01`, preserved exactly) and a `.x5` `.toFixed(1)` tie (`y=164.5` from `230 − 0.363636·180 = 164.545`). This corroborates, on the live deployed surface, the test's `newPath===oldPath` `toBe` (bit-identical) for the exact shape rendered. Console on `/yield-curve` = **0 errors / 0 warnings / 0 messages** (the r111-flagged pre-existing defects are on OTHER routes `/briefing/*` + `/`, NOT this surface, NOT r118's ; the spawn-task r114/r115/r116a fixes carried by this deploy chain are the spawn-task's, NOT re-claimed — causation ≠ proof, r118 is a pure coord refactor that neither caused nor fixed them). **HONEST SCOPE (lesson #1 / #11 / r106-a — the pre-write reconciled to the measured truth, NOT the optimistic forecast)**: the placeholder forecast said "REAL live data (R53 8 tenors)" — the deployed page in fact rendered the **static seed** (the `▼ offline · seed` pill, the 10-tenor `FALLBACK` `3M=4.86 … 30Y=4.38`, `aria-label "from 3M 4.86% to 30Y 4.38%"`). R53 separately PROVED `/v1/yield-curve` IS live+populated at the API layer (`curl 127.0.0.1:8000` via SSH, 8 tenors `obs 2026-05-15`) ; the deployed web2 **SSR** not reaching that API for this route is a **PRE-EXISTING graceful-fallback condition** (`page.tsx:3-5` "Falls back to a static seed … when the backend is unreachable, so SSR never crashes" — the same web2-SSR-API-base class as the r111-spawn-task `apiGet` domain, ITS scope), **NOT r118-introduced, NOT caused by r118, NOT re-scoped/fixed/re-claimed** (flag-not-fix #11, the r106-a "a deployed witness probes a pre-existing condition" lesson). **This does NOT weaken the r118 proof**: r118 is a pure data-agnostic coord refactor ; the contract test PROVED byte-identical for the `seed10` fixture (the EXACT shape the page renders) AND `live8` AND `n=2` ; the deployed path hand-matches the pre-r118 inline on `seed10` exactly — the migration's pixel-invariance is proven on the real deployed surface for the data it actually shows (SHIPPED≠FUNCTIONAL satisfied for r118's actual claim ; the "is it live data" question is a separate pre-existing data-wiring concern, honestly flagged not over-claimed — forecast≠proof, including on the optimistic side).

Voie D + ADR-017 N/A (pure descriptive yield-curve geometry, no signal — the same class as every microchart) ; additive web2-only deploy ; zero backend / zero migration (alembic still 0050) ; doctrine #9 dated append, NO new ADR, NO new primitive ; doctrine-#9 de-accumulation (a never-enumerated coord-scaling consumer-migration onto the existing SSOT, ledger refined per meta-r110 — NOT #8 "more coverage", NOT a re-affirmed "fully closed") ; the r117 "(D) needs a new primitive" conclusion R59-corrected (the honest `Math.log`∘`linScale` decomposition — a deeper R59 refining a prior round's hypothesis, the r67/r110 class) ; the prompt's "truncated y-baseline" framing R59-DISPROVED (a line chart's legitimate zoom, preserved exactly).
