# SESSION LOG — 2026-06-11 (close 06-12 ~00:30) · Session 04/09 re-run · Geopolitics differentiation + tone-column vitality

> Master-plan reference: [`PLAN_DIRECTEUR.md`](PLAN_DIRECTEUR.md) v4.1 §5
> session-file execution mapping — **04 → Chantier C**. Two PRs squash-merged
> same session: [#229](https://github.com/fxeliott/ichor/pull/229) → `e985a68`
> and [#230](https://github.com/fxeliott/ichor/pull/230) → `1ea6eb3`, both
> deployed + runtime-witnessed. Chantier C slice-1 blueprint persisted to
> memory (`ichor_chantier_c_slice1_blueprint.md`) — next session starts there.

## 0 · Verdict

The S04 re-fire closed the geopolitics data-gate FOR REAL — and the runtime
witness of that very fix exposed a deeper, older hole: the GDELT tone column
has been flat-zero for the entire retention window. The session shipped both
the differentiation fix and the honest-absence guard the discovery demanded,
same day, with an independent fresh-context reviewer on each PR.

## 1 · Ground truth first

- Re-fire protocol honored: PLAN_DIRECTEUR §5 maps session-file 04 → Chantier
  C; §5ter-bis re-read. 5-reader fan-out (plan/roadmap/S04 gaps/code/CLAUDE.md)
  before any code.
- Prod witness BEFORE coding: `_section_geopolitics` live on the 5 assets —
  EUR/NAS `applied=true`, **GBP matched=0, XAU matched=0, SPX matched=1**
  despite the S03 per-asset GDELT density (gold 403 rows/24h). Pool-cap
  simulation (40/200/400/1000/full) proved the 40-row most-negative pool is
  the structural bottleneck, NOT density — invalidating the passive
  "applied=True in a few days" watch item.

## 2 · Shipped

1. **PR #229 `e985a68` — widen per-asset GDELT candidate pool 40→400.**
   `_GEO_GDELT_POOL` 400 + router `_FILTER_FETCH_MULTIPLIER` 80 (default-top
   parity CI-pinned via route introspection) + deterministic `id.asc()`
   tiebreak (reviewer fold) + empirical rationale pinned in tests.
   Cap-400 simulation: 5/5 assets differentiate (XAU 0→48, GBP 0→9, SPX 1→11).
2. **PR #230 `1ea6eb3` — column-vitality guard / honest absence.** Witness of
   #229 post-deploy showed `applied=true` 5/5 BUT tone=+0.0 tops and keyword
   noise ("NBA Mock Draft" ticker-linked to GBP via _Bailey_). Root cause:
   **gdelt_events.tone = 0.0 on 13,607/13,607 rows over 8 days** — ArtList
   JSON carries no per-article tone (official DOC 2.0 docs list none; live
   probe 429-limited), parser default `art.get("tone", 0.0)` silent since
   ingestion. Guard: ≥20 pool rows ALL tone=0.0 → suspend the ranking with an
   explicit band + `GDELT:tone` DegradedInput; AI-GPR untouched; auto-disarms
   on any real tone. Reviewer folds: pool-scoped wording, exact-boundary test
   (19→normal / 20→suspended), `max_age_days=0` sentinel documented.

## 3 · Independent fresh-context reviews (both READY TO MERGE, findings folded)

- #229: 0 blocker / 0 major / 4 minor / 3 nit — folded MINOR 1 (tiebreak) +
  MINOR 3 (route-default introspection) + NIT (floor comment) pre-merge.
- #230: 0 blocker / 1 MAJOR explicitly classified follow-up (router parity in
  tone-dead regime, see §5) / 2 minor / 2 nit — minors + boundary nit folded
  pre-merge. Reviewer executed `is_adr017_clean(band)` directly (True) and
  verified ALL degraded_inputs consumers are pass-through (no ratio math).

## 4 · Verification (runtime, not "it compiles")

- Tests: 13 geo per-asset + 6 router-filter suites green; 450
  data_pool/ADR-017/ADR-081 regression green; ruff + format clean; mypy 0 new
  (23==23 and 16==16 stash-proven); 15/15 pre-commit hooks; CI 100% green on
  every push (15, 15, 14, 14 checks).
- Deploys ×2 `redeploy-api.sh` (backups `ichor_api.20260611-205857`,
  `-222039`), healthz+sample 200 both.
- **Final witness (post #230 deploy)**: 5/5 assets render the honest
  suspension band + `GDELT:tone` degraded trace, AI-GPR intact, zero
  fabricated list. Coach-FR witnessed on the freshest card (XAU ny_close
  22:26: 6 mécanismes FR sourced verbatim, COT/RVOL/geo/prediction-markets
  crossed). Engine alive: 24 Opus-4.8 xhigh cards/20h, critic active.

## 5 · Tone-dead blast radius (named follow-ups — NOT regressions of this session)

1. **`TARIFF_SHOCK` alert structurally neutralized** — gate `count_z>=2.0 AND
avg_tone<=-1.5` can NEVER fire on a dead column (an alert that cannot ring
   = the worst "zone d'ombre"). Highest-leverage follow-up.
2. `/v1/geopolitics/heatmap` `mean_tone` flat 0.0 — the ONE endpoint the
   frontend actually consumes (`apps/web/app/geopolitics/page.tsx:29`).
3. `/v1/geopolitics/briefing` router still serves "most-negative" on the dead
   column (brain suspends, panel fabricates — reviewer #230 MAJOR; no in-repo
   consumer today).
4. **Real tone repair** (un-gates 1-3): local FinBERT on GDELT titles
   (run_news_tone_scorer pattern, Voie-D clean, RECOMMENDED) vs ToneChart
   bins vs GKG V2Tone — S03-class slice.
5. **Class closure**: extend the S03 freshness monitor with column-vitality
   probes (zero-variance on critical columns over 48h → DATA_QUALITY alert).
   The monitor sees ARRIVAL, not validity — this is the TGA-bug class at
   column level, caught here only because a consumer witness looked.

## 6 · Chantier C slice-1 (next session, blueprint ready)

`ichor_chantier_c_slice1_blueprint.md` (memory D--Ichor) holds: current
3-snapshot fusion flow (file:line), DimensionVote target contract, golden-card
diff harness = prerequisite (does NOT exist; no full-pool stub either), 7 CI
traps (seam markers, S05 token guards, pinned values, positional tuple,
800-char cap, fixed priors), and the GPR doctrine web-research (threats≠acts,
90-99th percentile non-linearity, USD conditional safe haven, oil-supply
layer) for the future geopolitics `vote()`.

## 7 · Invariants held

ADR-017 (bands content-neutral, `is_adr017_clean` asserted + reviewer-executed)
· Voie D (zero `import anthropic`, zero LLM calls added, ZERO Anthropic spend)
· no migration · watermark untouched · ADR-110 engine framing (Opus 4.8 xhigh;
session interactive = Fable 5 jusqu'au 22/06, conforme décision owner §9.3)
· brain↔panel parity pinned at the router's introspected default.

## 8 · Re-fire #2 (06-12 ~01:00) — the tone column REPAIRED for real (ADR-112, PR #232 `090af3c`)

The owner re-fired with « tu es sûr d'avoir tout traité à 100% ? ». Honest
answer: no — §5 follow-up ① (real tone repair) was the highest-leverage
untreated gap: the geopolitics dimension was honestly SUSPENDED, not alive.
Shipped same night:

- **NEW `run_gdelt_tone_scorer`** (mirrors `run_news_tone_scorer`): local
  FinBERT scoring of unscored English titles (62% of rows/48h, prod
  witness), `tone = (p_pos − p_neg) × 10` on the GDELT-like scale; 15-min
  timer + OnFailure notify; no migration (`0.0` keeps meaning unscored/
  non-English/balanced); 48h first-run backfill.
- **Fresh reviewer (8 hunt axes): APPROVE, 0 blocker** — MAJOR-1 folded
  pre-merge: `TARIFF_SHOCK` avg_tone now averages SCORED rows only
  (unscored 0.0 excluded — a 62%-English mix would have made the −1.5
  gate ~1.6× harder than calibrated); + backfill-before-enable, rowcount
  guard, stale VADER comment, smoke test.
- **Runtime witnesses (all live prod)**: backfill 2,158 rows scored ·
  24h window now 877 neg / 419 pos / true −10..+10 distribution · service
  `Result=success ExecMainStatus=0` · **geo section 5/5: guard
  auto-disarmed, `applied=true`, degraded=[], REAL per-asset negative
  events** (World Bank→EUR, RICS housing→GBP, Nasdaq chips→SPX/NAS) ·
  heatmap `mean_tone` alive (US −0.66, India −1.3) · `tariff_shock`
  computes `avg_tone=−0.213` on scored rows — the alert is fireable again
  (no anomaly today, correct silence).
- Residual NITs (named): FinBERT saturates clearly-negative headlines at
  −10 (ranking unaffected; coarser granularity than a lexicon tone) ·
  dispose() GC warning on CLI exit (non-fatal, exit 0 proven) · MINOR-1
  noisy-notify on transient DB blips = follow-up with the column-vitality
  probes.

## 8bis · Ops notes

- ny_close 22:00 batch ran 4/6 cards during the interactive session
  (contention §6.1 coexisted; durations 417-672s in xhigh norm); GDELT
  collector polite budget respected (429 probes stopped after 2 attempts).
- Reviewer agent hit the Max-plan session limit at ~23:55 (reset 00:00 Paris)
  — resumed via SendMessage, no work lost; a stray detached-HEAD from the
  interrupted reviewer was repaired by fast-forwarding the branch
  (`git checkout -B`, no history rewrite).
