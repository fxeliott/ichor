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
