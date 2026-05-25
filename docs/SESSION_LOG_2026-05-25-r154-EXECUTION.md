# SESSION_LOG — r154 EXECUTION (2026-05-25)

> Tier 4 axis-4 +1 LEVEL DEPTH compound round : CB Speaker class extension + r153 code-reviewer fix-cluster + Pattern #16 doctrine codify (PERMANENT via memory + hook).

## Round outcome

**Engine 8 coverage 41.1% → 47.4%** on empirical 60d fixture (95 events). r154 closes 2 r153 binding default candidates in a single compound feat commit `3626a8d` (+382 LOC across 5 files).

**Pattern #16 EMPIRICALLY VALIDATED 2ND TIME** — r154 deploy api+web2 each Step-3a/3b/3c + Step-4 attempt 1 OK (zero retry). The codification works durably across consecutive rounds.

**Pattern #15 R59-disprove now stable across 7 applications** : r154 added CB Speaker honest-unmapped subset (researcher web R59 verified literature too thin for BoJ Ueda / BoC Macklem / Fed-Chair-non-FOMC / Trump / RBNZ Breman speakers → kept unmapped per calibrated refusal).

**4 of 8 axes ✅ CLOSED + axis 4 r154 deeper** : 1-2 r123 / 3 r132+r133 / **4 ✅ +1 LEVEL r152+r153+r154 ⭐** / 5 EMPIRICALLY GREEN r146 / 6 r142+r143 / 7 LIVE / 8 PARTIAL r131.

## Phase 0 R59 dual-audit

### Researcher web — CB Speaker literature verification

Verified peer-reviewed citations :

- **Akhtar-Faff-Oliver-Subrahmanyam 2012 _JBF_** (US S&P/DJIA asymmetric — already in Engine 8 r153)
- **Ehrmann-Fratzscher 2007 ECB WP 557** (verified primary source) : monetary-inclination statements move rates 1.5-2.5 bp ; BoE communication-dispersion 6-10 bp
- **Cieslak-Schrimpf 2019 _JIE_** (DOI: 10.1016/j.jinteco.2019.01.012) : 50%+ Fed/ECB press conferences carry non-monetary news → speeches are an information channel separate from decisions
- **Born-Ehrmann-Fratzscher 2014 ECB WP 1332** : speeches little effect in tranquil times, substantial only in crisis (implies VIX-gated magnitude — parity with r147 design)
- **Ranaldo-Rossi 2009 _JIMF_** (DOI: 10.1016/j.jimonfin.2009.06.005) : SNB verbal interventions DO move assets, contrast Kohn-Sack 2004 finding ordinary Fed speeches do NOT
- **Kurov-Wolfe-Gilbert 2021 _FRL_** : pre-FOMC drift disappeared post-2015 except around press-conference meetings (already in Engine 8 doctrine)

### HONEST UNMAPPED per Pattern #15 R59-disprove

- **Fed Chair non-FOMC speeches** — Kohn-Sack 2004 finding ordinary Fed speeches don't move yields ; no per-event bp magnitude in published lit
- **BoJ Gov Ueda Speaks** — single-source media commentary only (no peer-reviewed)
- **BoC Gov Macklem Speaks** — no academic event study
- **US Presidential remarks (Trump Speaks)** — Tillmann 2020 / Bianchi 2019 / Ge-Kurov-Wolfe 2018 find effects but content-dependent + 1-4h fade ; methodologically incoherent with pre-event drift framework
- **RBNZ Gov Breman Speaks** — no NZD asset + no literature

### code-reviewer post-hoc on r153 commit `6c4c3cd`

Verdict : READY-WITH-FIX (0 BLOCK, 0 CRITICAL, 3 SHOULD-FIX, 6 NICE-TO-HAVE). 4 findings applied r154 :

- **SF-1** : fixture `_meta.n_events: 94` declared vs actual 95 entries (off-by-one drift). Closing-sync coverage prose 39.4% was wrong (actual 41.1%).
- **SF-2 (architectural)** : asymmetric override preserved SIGNED `expected_drift_bp` despite `direction="unknown"` → Brier pipeline silently inherited business_cycle_sign bias.
- **N-1** : `_ASYMMETRIC_NEGATIVITY_CLASSES` defined inline in hot path → move to module-level constant.
- **N-2** : frontend `PARSE_FAILURE_FR["asymmetric_negativity_bias"]` still used pre-trader-YELLOW-2 wording (borderline directional) → rewrite to SSOT-consistent epistemic.

Deferred to r155 : SF-3 (deploy latency budget exponential backoff), N-3 (aria-label asymmetric a11y), N-4 (watchlist), N-5 (fixture semantic doc), N-6 (magic number doc).

## Phase 1 compound implementation

Single feat commit `3626a8d` +382 LOC across 5 files :

### Strand A — code-reviewer fix-cluster (4 items)

**SF-1 fixture reconciliation** (`apps/api/tests/fixtures/ff_titles_60d_high_medium_2026-05-24.json`) :

- `_meta.n_events: 94` → `95` (matches actual events[] length)
- Closing-sync prose updated 39.4%/94 → 47.4%/95 (post-r154 mechanical recomputation)

**SF-2 architectural sign-strip on asymmetric** (`event_proximity_engine.py:764-775`) :

```python
if event_class in _ASYMMETRIC_NEGATIVITY_CLASSES and expected_drift_bp is not None:
    direction = "unknown"
    # r154 SF-2 architectural fix : strip business_cycle_sign bias from
    # the magnitude when the asymmetric sentinel fires. The literature
    # framing is conditional-on-negative-surprise UNSIGNED magnitude ;
    # the pre-event direction is unknown ; therefore exporting a signed
    # value would silently propagate business-cycle-default bias into
    # downstream Brier/confluence consumers (which multiply by sign).
    # Set abs() so the magnitude is honest-unsigned and downstream
    # consumers compute on an unbiased prior.
    expected_drift_bp = abs(expected_drift_bp)
    parse_failures.add("asymmetric_negativity_bias")
```

Same doctrine #11 calibrated honesty class as r150 RBA/BoC trader YELLOW-2 (caveat string-only honesty was asymmetric — backend honest, downstream silently biased).

**N-1 module-level constant** (`event_proximity_engine.py:447-458`) :

- `_ASYMMETRIC_NEGATIVITY_CLASSES` moved from inline (hot path) to module-level after `_TITLE_FRAGMENT_BLOCKED`. Frozenset literal allocated ONCE at import instead of per session-card × asset × pass.

**N-2 frontend SSOT** (`apps/web2/lib/eventAnticipation.ts:284-292`) :

- `PARSE_FAILURE_FR["asymmetric_negativity_bias"]` reworded from "Réaction asymétrique : magnitude significative uniquement sur surprise négative" (borderline directional) to "Skew empirique négatif (asymétrie selon le signe de la surprise, Akhtar 2012 / Ranaldo-Rossi 2009)" (SSOT-consistent epistemic). Same trader YELLOW-2 epistemic framing now mirrored in 3 places (backend caveat, frontend translation, code comments).

### Strand B — Pattern #16 doctrine codify (OUT-OF-REPO PERMANENT)

**`~/.claude/projects/D--Ichor/memory/ichor_r51-r71_doctrinal_patterns.md`** : NEW Pattern #16 section after Pattern #15 (~80 LOC) :

- Pattern statement : any long-lived SSH pipe = failure-class equal to Step-4 SSH-restart (Pattern #14)
- Empirical witness : r152 Step-3 timeout, r153 zero-retry validation, r154 second consecutive zero-retry validation
- How-to-apply : 4-step decompose discipline
- Where-it-applies : api + web2 ✓ codified r153 ; brain N/A (direct rsync)
- Twin doctrine to Pattern #14 (Step-4 SSH-restart)
- Generalizes to ANY long-lived SSH operation in deploy scripts

**`~/.claude/hooks/auto_context_injector.ps1`** KEYWORD DEPLOY rule extended :

- Existing rule referenced runbook + scp confirmation
- r154 extension : inject Pattern #14 + #16 doctrine reference on deploy keyword detection so future sessions inherit the doctrine via session-resume hook

Out-of-repo files (memory + hook), no commit in this repo. Doctrine is now PERMANENT.

### Strand C — CB Governor scheduled-speech class extension

`event_proximity_engine.py` :

**`EVENT_CLASS_BASELINE_BP`** += 3 new classes (literature-anchored) :

- `ECB_Speech: 7.0` — Ehrmann-Fratzscher 2007 + Cieslak-Schrimpf 2019 (rate-channel 1.5-2.5 bp → equity extrapolation conservative)
- `BoE_Speech: 8.0` — Ehrmann-Fratzscher 2007 BoE-specific 6-10 bp dispersion midpoint
- `SNB_Speech: 10.0` + asymmetric_negativity_bias sentinel — Ranaldo-Rossi 2009 + 2024 SNB textual-analysis

**`_TITLE_TO_EVENT_CLASS`** += 4 patterns ordered EARLY (before BoJ generic fallback) :

- `("ecb president", "ECB_Speech")` — Lagarde + future ECB presidents
- `("bailey", "BoE_Speech")` — current BoE governor
- `("mansion house", "BoE_Speech")` — annual speech variant
- `("snb chairman", "SNB_Speech")` — Schlegel + future SNB chairmen

**`_ASYMMETRIC_NEGATIVITY_CLASSES`** extended : `{"CCI", "Michigan", "SNB_Speech"}` (3rd class joins r153 sentiment asymmetric pattern).

**NEW caveat surface block for SNB_Speech** :

```
"Skew empirique négatif : sentiment négatif observé historiquement plus rapide
à propager que sentiment positif (Ranaldo-Rossi 2009 JIMF, données 2000-2005
pré-floor-cap — généralisation post-2015 à confirmer)"
```

**NEW caveat surface block for ECB_Speech + BoE_Speech** :

```
"Magnitude extrapolée de l'event-window taux (Ehrmann-Fratzscher 2007 ECB WP
557) vers l'equity via gate VIX — calibration equity-specifique r155+"
```

**Frontend `EVENT_CLASS_FR`** += 3 new CB Speaker labels :

- `ECB_Speech: "Discours BCE (Lagarde, hors décision)"`
- `BoE_Speech: "Discours BoE (Bailey, Mansion House)"`
- `SNB_Speech: "Discours SNB (Schlegel)"`

### Tests added

**Backend** (17 new tests across 4 r154 classes) :

- `TestR154CbSpeakerClassMapping` (7) : 3 ship mappings (ECB/BoE/SNB) + 4 honest-unmapped regression (BoJ/BoC/Trump/RBNZ stay null + Mansion House variant + bare BoE GovBailey)
- `TestR154NewBaselineKeys` (4) : new baselines + tier-ordering invariant (speakers < decision-day classes)
- `TestR154SnbSpeechAsymmetricSentinel` (2) : SNB in `_ASYMMETRIC_NEGATIVITY_CLASSES` + module-level constant importable
- `TestR154AsymmetricMagnitudeSignStripped` (2) : SF-2 architectural fix empirically witnessed via business_cycle_sign=-1 (CCI emits unsigned positive magnitude, ISM symmetric emits signed negative)
- `TestR154FixtureMetaReconciliation` (2) : SF-1 meta n_events matches events length + post-r154 coverage ≥ 45%

**Frontend** (4 new tests) :

- `r154 EVENT_CLASS_FR CB Speaker extension` (4 tests for ECB_Speech/BoE_Speech/SNB_Speech labels + regression vs r147+ decision-day classes)
- N-2 SSOT-consistency rewrite of `r153 translates asymmetric_negativity_bias sentinel` assertion (now matches purely-epistemic "Skew" framing)

## Build gate (MEASURED on COMMITTED-shape doctrine #14)

- **pytest targeted** : 216/216 (was 199 r153 + 17 r154 new = 216)
- **vitest** : 425/425 (was 421 r153 + 4 r154 EVENT_CLASS_FR + 1 SSOT fix update = 425)
- **tsc** : 0 errors
- **ESLint** : clean
- **Prettier** : clean (all r154 files)
- **Ruff check + format** : clean
- **ADR-017 source-inspection lockstep CI** : green on `lib/eventAnticipation.ts`
- **Backend ADR-017 invariant** : auto-covers new files via `_ADR017_PROD_ROOTS`
- **Brier 12-factor lockstep r142+r148** + **r149 event-class consistency** : all preserved
- **bash syntax** : clean (api + web2 + brain scripts)

## Phase 3 deploy via R-DEPLOY-6 (Pattern #16 EMPIRICALLY VALIDATED 2ND TIME)

```
[2026-05-25T09:01:17Z] Step 3a: local-tar package -> /tmp/ichor_api_redeploy.tar.gz
[2026-05-25T09:01:18Z] Step 3b: scp tarball -> remote /tmp
[2026-05-25T09:01:19Z] Step 3b attempt 1: scp OK
[2026-05-25T09:01:20Z] Step 3c: ssh-extract + rsync + chown (short single call)
[2026-05-25T09:01:21Z] Step 3c attempt 1: extract+rsync OK
[2026-05-25T09:01:21Z] Step 4: restart ichor-api; wait /healthz
[2026-05-25T09:01:22Z] Step 4 attempt 1: SSH restart OK
```

api : Step 3a + 3b + 3c + 4 each attempt 1 OK. healthz=200 + all 6 priority asset endpoints return 200 (EUR_USD/GBP_USD/USD_CAD/XAU_USD/NAS100_USD/SPX500_USD).

web2 : Step 1a + 1b + 1c + 4 each attempt 1 OK. local /briefing=200 + public /briefing=200. Tunnel stable.

**Pattern #16 now EMPIRICALLY VALIDATED on 2 consecutive deploys** (r153 + r154). The codification works durably.

## Phase 3.5 R-WITNESS-EMPIRICAL via Playwright

`/briefing/EUR_USD?cb=r154` snapshot extract :

```
- region "Catalyseur imminent · ancrage littérature"
  - CB Consumer Confidence
  - "Confiance consommateurs (Conference Board) · USD · medium"   ← preserved from r153
  - "T−1j 4h" (28h to Tue 26 May 16:00 CB Consumer Confidence)
  - group "Biais de dérive attendu : Direction indéterminée, magnitude 0.2 bp, confiance faible, vix < p50 (régime calme)"
    - "Direction indéterminée pour cette classe d'événement"
    - "Confiance faible · VIX < p50 (régime calme)"
  - paragraph: "Asymétrie cyclique non vérifiée, défaut expansion ; Skew empirique négatif : magnitude observée historiquement asymétrique selon le signe de la surprise (Akhtar 2012 JBF + Pinchuk 2022 arXiv) ; Magnitude prior littérature, pas calibrée sur historique Ichor"
  - paragraph: "Ancrage : Lucca-Moench 2015 (drift) + Boyd-Hu-Jagannathan 2005 (asymétrie cyclique) + Kurov 2021 (gate VIX) + Akhtar et al. 2012 JBF (asymétrie consumer-sentiment) + Andersen-Bollerslev-Diebold-Vega 2007 JIE (MNA intraday) + Pinchuk 2022 arXiv"
  - paragraph: "Limitations remontées : Skew empirique négatif (asymétrie selon le signe de la surprise, Akhtar 2012 / Ranaldo-Rossi 2009)"   ← N-2 SSOT fix LIVE (was "Réaction asymétrique : magnitude significative uniquement sur surprise négative" pre-r154)
```

**All r154 changes empirically witnessed in prod** :

- ✓ Event meta "Confiance consommateurs (Conference Board)" (r153 mapping preserved)
- ✓ Magnitude 0.2 bp (was 0.06 r153 deploy ; SF-2 abs() fix landed — positive value preserved)
- ✓ "Direction indéterminée pour cette classe d'événement" (asymmetric override)
- ✓ Caveat "Skew empirique négatif" (r153 trader YELLOW-2 preserved)
- ✓ Literature anchor extended (Akhtar 2012 + ABDV 2007 + Pinchuk 2022)
- ✓ **"Limitations remontées : Skew empirique négatif (asymétrie selon le signe de la surprise, Akhtar 2012 / Ranaldo-Rossi 2009)"** — **N-2 SSOT fix LIVE on prod**
- ✓ Drift cluster aria-label includes VIX regime (r152 a11y IMPORTANT-2 preserved)
- ✓ Footer round-numbers correctly omitted (r152 ui-designer fix preserved)
- ✓ ZERO directional imperatives (ADR-017 preserved)

Screenshot archived `r154_briefing_eur_usd_event_anticipation_panel.png`.

## Empirical coverage outcome

- Pre-r154 (r153 actual after SF-1 reconciliation) : **41.1%** (39 mapped / 95 events) — NOT 39.4%/94 as r153 closing-sync prose claimed
- Post-r154 : **47.4%** (45 mapped / 95 events)
  - - BoE_Speech 3 (Bailey ×3)
  - - ECB_Speech 2 (Lagarde ×2)
  - - SNB_Speech 1 (Schlegel)
  - = net +6 mapped
- CI threshold ratchet : 35% (r153) → 45% (r154 effective threshold per `test_post_r154_coverage_above_baseline`)

## Honest scope (doctrine #2 + #11)

- NO new ADR.
- NO new migration.
- NO new feature flag.
- NO data backfill.
- Pure compute extension + test invariants + frontend SSOT alignment.
- Strand B (Pattern #16 doctrine codify) is OUT-OF-REPO (memory file + auto-context-injector hook). PERMANENT via session-resume hook.
- Sentinels propagate honestly 3 layers (engine frozenset → view → router sorted list → frontend FR label via PARSE_FAILURE_FR with r154 SSOT-fixed wording).
- Doctrine #9 dated §Impl(r154) APPEND on ADR-099, NO new ADR.
- doctrine-#9 coord-math ledger UNCHANGED.

## Voie D + Mission axis impact

- **Voie D held 69 rounds** (zero `import anthropic` r154 ; pure compute extension + sub-agent dispatch + Playwright witness + SSH/SQL probe + no LLM call).
- **Mission centrale axis-4 +1 LEVEL DEPTH (r152 + r153 + r154 cumulative)** — Engine 8 LIVE + USER-VISIBLE + coverage broader.
- Axes post-r154 : 1-2 ✅ r123 / 3 ✅ r132+r133 / **4 ✅ +1 LEVEL r152+r153+r154 ⭐** / 5 ✅ EMPIRICALLY GREEN r146 / 6 ✅ CLOSED r142+r143 / 7 🎯 LIVE / 8 🎯+1 PARTIAL r131.
- **4 of 8 axes ✅ CLOSED + axis 4 r154 deeper still.**

## NEW pattern observation r154

**Pattern #15 R59-disprove now stable across 7 applications** :

1. r147 Bauer DP21003 hallucination caught (citation-identity)
2. r148 daily-bar reaction-beta REJECT (methodology)
3. r150 PIVOT 1 VIX 5y rolling REJECT (data state)
4. r150 PIVOT 2 RBA/BoC sign-flip REJECT (single-source unreplicated)
5. r153 Karnaukh-Vrolijk 2019 hallucination caught (citation-identity)
6. r153 ISM Services weak-citation acknowledged honestly (kept ISM=15bp with caveat)
7. **r154 CB Speaker honest-unmapped subset** (BoJ/BoC/Fed-Chair-non-FOMC/Trump/RBNZ : refused to fabricate magnitudes for content-dependent or unsupported classes)

**Pattern #16 EMPIRICALLY VALIDATED 2nd consecutive deploy** (r153 + r154). Durable.

**Multi-round doctrinal self-correction** : r153 code-reviewer dispatch killed by session-compact → r154 Phase 0 re-dispatched on r153 commit + 4 findings applied. Future rounds will inherit this self-correction discipline.

## r155 binding default candidates

(a) ⭐ AUTO-RECO **PMI Services class extension** (Flash Manufacturing/Services PMI EUR/GBP/USD — 6 events in fixture, ~53-55% coverage). Researcher R59 first on S&P Global Flash PMI separate-class literature.

(b) **US Retail Sales + Core Retail Sales class** (4 events in fixture). Andersen-Bollerslev 2003 supports. Effort S.

(c) **UK Claimant Count Change + Average Earnings Index extension**. Effort S.

(d) **FRED VIXCLS backfill 5y** (deferred since r150). Effort M, researcher R59 first on FRED bulk API.

(e) **Empirical reaction-beta backfill via Dukascopy 1-min FREE multi-year** — replaces literature priors with Ichor-historical. Effort L (3-5 dev-days). Pattern #15 R59 first.

(f) **`output_gap_proxy` wiring** (composite NFCI + SBET + macro nowcast). Effort M.

(g) **r147 MRO smell fix** (`TestBrierLockstepWithR147(TestAdr017Invariants)` inherits non-Brier tests — deferred since r150).

(h) **Per-currency Employment subclass** (trader r150 YELLOW-3).

(i) **r152 trader YELLOW-1/2 visual demotion of literature priors**.

(j) **Code-reviewer r153 SF-3 deploy latency budget** + optional exponential backoff.

(k) **Code-reviewer r153 N-3** aria-label conditional magnitude when driftMeaningful=false (asymmetric a11y).

(l) **FRED ALFRED reconciler unit normalization upstream** (deferred since r147).

(m) **`actual_source` / `actual_revised` columns** + EU/UK reconcilers.

Pattern #15 R59-disprove-before-commit applies to every r155 ⭐ AUTO-RECO candidate.

## ZERO Anthropic API spend

## Post-mortem Steenbarger (Phase 5 — strengths-based reverse-journal)

**2 process wins** :

1. **Pattern #15 R59-disprove caught my OWN proposed magnitudes for low-evidence speakers.** Initial planning would have shipped CB Speaker mappings for ALL 6 governors (Bailey/Lagarde/Schlegel/Macklem/Ueda + Trump). Researcher web R59 verified literature only supports 3 (ECB/BoE/SNB) — BoJ Ueda has only Reuters/CNBC commentary (single-source non-peer-reviewed), BoC Macklem zero academic event-study, Trump speeches are content-dependent + 1-4h fade (methodologically incoherent with pre-event drift framework). Refused to fabricate magnitudes. Pattern #15 now stable across 7 applications — the discipline is durable, not ad-hoc.

2. **Code-reviewer compact-kill gap closed empirically.** r153 code-reviewer agent was killed mid-session by compact (0 bytes output). r154 Phase 0 re-dispatched on r153 commit + got back READY-WITH-FIX with 4 actionable items, all applied this round (SF-1 + SF-2 + N-1 + N-2). The procedural discipline "if a sub-agent dies mid-session, the NEXT round's Phase 0 includes re-dispatch as candidate (a)" worked end-to-end. Multi-round self-correction is now part of the doctrine library implicitly.

**1 micro-fix (not refonte) for r155** :

The SF-1 fixture drift (94 declared vs 95 actual) had been hiding in r153 closing-sync prose for ~12 hours unnoticed. The CI invariant test `test_title_coverage_pct_above_threshold` was checking coverage % but NOT checking `_meta.n_events == len(events)`. **Micro-fix r155** : the test `test_fixture_meta_n_events_matches_events_length` I added r154 SHOULD have been part of the original r153 fixture creation. Generalizable lesson : whenever a fixture file has METADATA describing the payload, ALWAYS include a CI test asserting metadata consistency. r155 candidate (j) : add similar metadata-consistency tests across ALL `tests/fixtures/*.json` files (currently the only fixture but the pattern generalizes).
