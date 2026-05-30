# r145 — EXECUTION LOG — 2026-05-22

> **Status** : CODE SHIPPED + PUSHED + BUILD GATE GREEN. Deploy + empirical witness DEFERRED r146 Phase 0 (lesson #24 SSH-instability triggered 3 consecutive Hetzner SSH timeouts — trader stop-loss discipline applied per doctrine #2 + Steenbarger pattern).
> **Branch** : `claude/amazing-heyrovsky-80df1e` · **HEAD pre-r145** : `8fc8cbd` · **HEAD post-r145 feat** : `9abea76`
> **Voie D streak** : 60 rounds (zero `import anthropic` ce round)
> **No new migration** : reuses r141 schema 0052 + r144 ALFRED data.

## TL;DR

r145 closes Mission centrale axis-5 USER-SURFACE VISIBILITY (code-side) : the r141 `classify_surprise()` 5-state classifier (dormant since r141) is now wired as the single API truth-source ; the r144 18 populated US event actuals now surface on `/briefing/[asset]` via a new `<RecentActualsPanel>` tile.

R59 dual-audit (parallel sub-agents) caught a CRITICAL design subtlety BEFORE code : reading `classify_surprise()` source verbatim revealed lines 242-249 compute `magnitude_pct` INDEPENDENTLY of `state`. So today (no range provider) the classifier returns `state=unavailable` for all 18 events BUT `magnitude_pct` populates from FF consensus point. Future-proof contract : when r146+ range provider lands, state badges + amber emphasis auto-light up without UI/API changes (gated by `stateMeaningful` parameter).

4-reviewer parallel dispatch (doctrine #17 NEW visible UI) ; all SHIP-WITH-FIXES (0 BLOCK + 0 CRITICAL/RED) ; fix-cluster applied (2 CONCORDANT 2/4 + 9 single-domain authority findings).

Build gate FULLY GREEN : pytest 148/148 + vitest 369/369 + tsc 0 + eslint 0 + next build OK. Committed `9abea76` + pushed.

Deploy + Playwright witness DEFERRED r146 Phase 0 due to 3 consecutive SSH timeouts on Hetzner (lesson #24 SSH-instability, transient). Parity with r142→r143 frontend deploy deferral pattern.

## Phase 0 — R59 dual-audit (2 parallel sub-agents)

### code-explorer : current-state mapping

- **`/v1/calendar/*` endpoints** : 2 routes, neither projects `actual`/`forecast`/`forecast_min`/`forecast_max`. `CalendarEventOut` projects 8 fields, none r141/r144.
- **`classify_surprise()` consumers** : ZERO in routers. Dormant.
- **`MacroSurprisePanel`** : consumes FRED-derived ESI z-scores, ORTHOGONAL to per-event actual. r135/r136/r137 are on the FRED track.
- **ORM** : `EconomicEvent.actual` / `.forecast` / `.forecast_min` / `.forecast_max` / `.previous` confirmed lines 36-39 as `String(64)` nullable.
- **schemas.py** : zero `EconomicEvent` Pydantic shape (inline in router).
- **Recommendation** : NEW endpoint + NEW tile (don't shoehorn into MacroSurprisePanel).

### researcher : trader-grade UI patterns + AMF/ADR-017 alignment

- FF/Bloomberg pattern collapses geometric+directional (green=bullish). **Ichor must NOT replicate** that collapse.
- AMF DOC-2008-23 compliance : descriptive geometric labels OK ; `acheter`/`hot CPI → USD-bullish` banned (already in `adr017_filter.py`).
- **FR copy locked** (researcher §3) : `Donnée non publiée` / `Dans la fourchette des analystes` / `Au-dessus de la fourchette` / `En-dessous de la fourchette` / `Pile sur le consensus`.
- **Counter-intuitive regime guard** (researcher §5, arXiv 1410.8427+2212.04525) : surface raw geometric classification ONLY ; directional interpretation deferred to verdict/confluence layers (codified at `economic_event_surprise.py:223-226`).
- 5 implementer items locked : MacroSurprisePanel visual grammar reuse + row display order + footer caveat mirror + CI invariant on FR strings + `unavailable` silent badge.

### Critical R59 source-verbatim discovery

`classify_surprise()` lines 242-249 :

```python
magnitude_pct: float | None = None
if actual_f is not None and consensus_f is not None and abs(consensus_f) > 1e-9:
    magnitude_pct = (actual_f - consensus_f) / abs(consensus_f) * 100.0
```

The magnitude_pct is computed INDEPENDENTLY of state. So even when `forecast_min/max` are NULL (r145 reality everywhere), the classifier returns `state=unavailable` BUT magnitude IS populated from the FF consensus point. **Wiring the classifier today is the correct future-proof contract** — not deferring it as my initial Option A was suggesting.

## Phase 1 — Backend implementation (3 files)

### `services/recent_actuals.py` (NEW, ~150 LOC)

Pure compute. `RecentActualRow` frozen dataclass + `fetch_recent_actuals()` ORM query past N-day window where `actual IS NOT NULL`, then `classify_surprise()` per row. Both raw text values AND classifier verdict exposed (parity with `MacroSurprisePanel` raw z + magnitude pattern).

### `routers/calendar.py` — NEW route

`GET /v1/calendar/recent-actuals` + 3 Pydantic shapes (`SurpriseClassificationOut` / `RecentActualOut` / `RecentActualsOut`).

`SurpriseStateLiteral = SurpriseState` re-export (code-reviewer SHOULD-FIX #2 — single source of truth, drift-protected by CI lockstep test).

### `tests/test_recent_actuals.py` (NEW, 22 tests)

5 test classes : `TestFetchRecentActuals` (13 — happy path + classifier wiring + state=unavailable + state=in_range + state=above_range + state=below_range + limit clamp + currency filter + lookback window + now injection + defensive null-skip + parse_failures propagation) + `TestRecentActualsRouter` (4 — Pydantic shape + lookback validation + limit validation + currency 422) + `TestAdr017Invariants` (5 — state literal alphabet + no-directional fields + backend Literal lockstep).

## Phase 2 — Frontend implementation (5 files)

### `lib/api.ts` — NEW types

`SurpriseState` (5 literal) + `SurpriseClassificationOut` + `RecentActualRow` + `RecentActuals` — wire shape mirrors backend Pydantic.

### `lib/recentActuals.ts` (NEW, ~115 LOC)

Pure-fn view-model : `SURPRISE_STATE_FR` (researcher-locked FR copy) + `NOTABLE_MAGNITUDE_PCT_THRESHOLD=5.0` + `fmtMagnitudePct` + `magnitudePctTone(pct, stateMeaningful)` + `shouldRenderStateBadge` + `fmtScheduledAtParis` + `fmtScheduledDateParis` + `isEmptyRecentActuals`.

### `components/briefing/RecentActualsPanel.tsx` (NEW, ~170 LOC)

Visual grammar parity with `<MacroSurprisePanel>` : header (`border-b · px-6 py-4 · font-serif text-lg`) + `<ul>` rows with `divide-y` + footer caveat band + motion-react `m.section` entry + ARIA semantic.

### `app/briefing/[asset]/page.tsx`

Promise.all gains `apiGet<RecentActuals>(...)` + JSX placement between `<MacroSurprisePanel>` and Géopolitique section.

### `__tests__/recentActuals.test.ts` (NEW, 26 tests)

`SURPRISE_STATE_FR` (3) + `fmtMagnitudePct` (5 post fix-cluster I1) + `magnitudePctTone` (4 — null + state-not-meaningful + state-meaningful-below-threshold + state-meaningful-above-threshold) + `shouldRenderStateBadge` (2) + `fmtScheduledAtParis` (3 — DST CET/CEST + malformed) + `fmtScheduledDateParis` (2) + `isEmptyRecentActuals` (4) + ADR-017 source-inspection CI (2 files × widened 24+ canonical regex) + backend-frontend lockstep (1).

## Phase 3 — Build gate + 4-reviewer parallel dispatch

### Build gate (MEASURED — doctrine #14)

- **pytest 148/148** (22 r145 + 47 r141 economic_event_surprise + 13 invariants_ichor + 31 r142 + 35 r144 reconciler)
- **vitest 369/369** (26 r145 + 343 cross-module)
- **tsc 0 errors** (strict + `exactOptionalPropertyTypes`)
- **eslint 0 warnings**
- **next build OK**
- **pre-commit hooks 2-pass** (doctrine #6) : ruff auto-fixed `timezone.utc` → `UTC` alias + ruff-format + prettier ; re-stage + re-commit clean.

### 4-reviewer concordance (doctrine #17 NEW visible UI = 4-reviewer parallel)

| Reviewer          | Verdict         | Critical/Red                                              | Applied                                                                                                   |
| ----------------- | --------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **trader**        | SHIP-WITH-FIXES | 0 RED + 3 YELLOW + 4 GREEN                                | Y1 sign-convention footer + Y2 unavailable disclosure subtitle                                            |
| **ui-designer**   | SHIP-WITH-FIXES | 0 CRITICAL + 3 IMPORTANT + 4 NIT + GREEN parity confirmed | I1 magnitude token shortened + I2 amber gated + I3 meta line trimmed                                      |
| **a11y**          | SHIP-WITH-FIXES | 0 CRITICAL + 1 IMPORTANT + 2 SHOULD + 2 NIT               | IMPORTANT-1 DROP `<li aria-label>` + NIT-1 `aria-hidden` on `·` + SHOULD-2 drop `title=`                  |
| **code-reviewer** | SHIP-WITH-FIXES | 0 CRITICAL + 3 SHOULD-FIX + 4 NICE                        | S1 impact downcast removed + S2 SurpriseStateLiteral re-export + S3 widened regex + N6/N7 docstring fixes |

### Concordant 2/4 fixes (lower bar per r143 NEW pattern doctrine #17 expansion)

- **ui-designer I2 + a11y SHOULD-1** : amber tone gated on `stateMeaningful` (no fabricated emphasis when range data missing + sidesteps contrast risk).
- **ui-designer N3 + a11y SHOULD-2** : drop `title="..."` tooltip (keyboard-inaccessible + redundant).

### Single-domain authority findings applied

- **a11y IMPORTANT-1** (single-domain a11y) : DROP `<li aria-label>` per ARIA 1.2 (clobbers visible-text SR reading + drops currency/impact/date for SR users). REPLACE with DOM-reading-order strategy.
- **a11y NIT-1** : `<span aria-hidden="true">·</span>` middot wrapper.
- **ui-designer I1** : magnitude token `+5.0% vs consensus` (19 chars) → `+5.0%` (5 chars). Fits 320px parity with MacroSurprisePanel `+1.8σ`.
- **ui-designer I3** : drop `· currency · impact` from row meta (currency in panel header, impact implicit since panel filters to high-tier).
- **trader Y1** : sign-convention anchored in footer caveat — `"+/− = position vs consensus, sans préjuger du sens marché"`.
- **trader Y2** : `unavailable` universal disclosure moved into subtitle (was buried in footer band, easy to miss).
- **code-reviewer S1** : remove silent impact downcast `r.impact if r.impact in (...) else "low"` fallback. Doctrine #11 calibrated honesty — Pydantic Literal fail-fasts on bad ORM data instead of fabricating "low".
- **code-reviewer S2** : `SurpriseStateLiteral = SurpriseState` re-export + `test_backend_state_literal_lockstep` invariant — 3-place lockstep (service Literal ↔ router re-export ↔ frontend type).
- **code-reviewer S3** : widen ADR-017 frontend regex from 4 patterns → 24+ canonical : EN bare/conditional imperatives + numeric TARGET/ENTRY + risk vocab + FR/ES/DE imperatives all forms (incl. `acheter|achète|achetez`).
- **code-reviewer N6+N7** : fix Cache-Control + empty-currency docstring lies + update test contract to match Pydantic 422 reality.

### Deferred r146 NIT batch

- ui-designer N1 footer caveat density split
- ui-designer N2 `<ul>` list-none defensive (verify globals.css resets list-style)
- a11y NIT-2 "30 jours" in heading (vs subtitle)
- code-reviewer #4 `shouldRenderStateBadge` indirection
- code-reviewer #5 `test_now_defaults_to_utc_when_omitted` weak assertion

## Phase 4 — Deploy DEFERRED r146 Phase 0

### R-DEPLOY-6 + lesson #24 stop-loss trigger

Attempted backend deploy via `redeploy-api.sh` — 3 consecutive SSH timeouts during step 4 (restart + healthcheck loop) :

```
[2026-05-22T19:46:15Z] Step 1: hard-check verified remote path
[2026-05-22T19:46:16Z] Step 2: backup remote package
[2026-05-22T19:46:17Z] Step 3: tar-over-ssh local package OK
[2026-05-22T19:46:20Z] Step 4: restart ichor-api; wait /healthz
ssh: connect to host 178.104.39.201 port 22: Connection timed out
```

Retried with `ConnectTimeout=15` then `ConnectTimeout=30` then `ConnectTimeout=60` — all 3 timed out. **Lesson #24 SSH-instability** (Hetzner sometimes drops SSH for 5-30min as observed across multiple sessions) triggered the **Steenbarger trader stop-loss pattern** : 2 failed attempts → revert and reformulate, NOT revenge-debug.

### Honest closure (doctrine #11)

- Code SHIPPED + PUSHED (commit `9abea76`) ✓
- Build gate FULLY GREEN ✓
- Deploy + Playwright empirical witness DEFERRED r146 Phase 0

**Parity with r142→r143 deferral pattern** : r142 deferred frontend deploy due to TS portability error ; r143 picked it up as Phase 1 work. Same shape : r146 Phase 0 = retry deploy + witness.

### r146 Phase 0 plan

1. SSH liveness check `ssh ichor-hetzner echo ok` (1 retry max)
2. `redeploy-api.sh` step 4 retry (the deploy package is already at `/opt/ichor/api/staging/` from r145 step 3 — just need restart)
3. `curl -sf /v1/calendar/recent-actuals?lookback_days=30&limit=3 | jq` empirical verify (expect 3 rows, state=unavailable, magnitude_pct populated)
4. `redeploy-web2.sh` for frontend
5. Playwright snapshot on `/briefing/EUR_USD?cb=r146` capturing `<RecentActualsPanel>` rendering 18 events

## Honest scope · what r145 does NOT do (doctrine #2)

- ❌ No new ADR (additive endpoint + tile + classifier wire — established patterns)
- ❌ No new migration (reuses r141 schema 0052)
- ❌ No range envelope provider (consensus poll aggregator deferred r146+)
- ❌ No EU/UK/JP `actual` providers (r146+ candidate via ECB SDMX / ONS / BoJ)
- ❌ No `actual_revised` column (T+24h overwrite deferred r146+)
- ❌ No `actual_source` column (single-provider acceptable today)
- ❌ No FF XML title-coverage CI invariant (r146 binding default)
- ❌ No Playwright empirical witness (deferred r146 Phase 0)

## r146 binding default candidates

1. ⭐ **AUTO-RECO** : retry r145 deploy via R-DEPLOY-6 + Playwright empirical witness on `/briefing/EUR_USD?cb=r146`. Effort S (already coded ; just deploy execution).
2. **FF XML title-coverage CI invariant** (r144 trader Y2(a) UPGRADED). Effort S-M.
3. **ADR-017 web2 caveat RTL regex** (deferred r143+r144). Effort S-M.
4. **`actual_source` column** (Critic-attribution when 2nd provider lands). Effort S.
5. **`actual_revised` T+24h overwrite column**. Effort S-M.
6. **Range envelope consensus-poll provider** (would auto-light up r145 state badges on the existing surface — high leverage on r145 infra). Effort M.
7. **EU `actual` reconciler via ECB SDMX** (mirror r144 pattern + R-WITNESS-EMPIRICAL discipline). Effort M.

## Doctrine + lesson alignment

- ✅ **Doctrine #1 R59-first** — 2 parallel sub-agents BEFORE code ; source-verbatim discovery (classifier computes magnitude independently) prevented an Option A miss-scope.
- ✅ **Doctrine #2 strict scope** — 1 round = 1 axis-5 visible surface CODE ; deploy + witness honest-deferred r146 (not panic-shipped).
- ✅ **Doctrine #4 SSOT** — `SurpriseStateLiteral = SurpriseState` re-export (no duplicate Literal definitions). `SURPRISE_STATE_FR` consumer-side SSOT for FR copy.
- ✅ **Doctrine #6 commit single-step, NOT amend** — pre-commit hooks 2-pass (ruff auto-fix + prettier) ; re-stage + re-commit clean.
- ✅ **Doctrine #9 dated §Impl APPEND, NO new ADR** (additive endpoint + tile + established patterns).
- ✅ **Doctrine #11 calibrated honesty** — impact downcast REMOVED ; `state=unavailable` honest empty when no range data ; deploy deferral documented not hidden.
- ✅ **Doctrine #14 build gate on COMMITTED shape** — pytest 148 + vitest 369 + tsc 0 + eslint 0 + next build OK BEFORE push.
- ✅ **Doctrine #17 4-reviewer NEW visible UI** — trader + ui-designer + a11y + code-reviewer parallel ; CONCORDANT 2/4 + single-domain authority applied.
- ✅ **Lesson #1 MEASURED not forecast** — 148 + 369 tests run + post-fix-cluster re-verified.
- ✅ **Lesson #22 worktree-mismatch absolute paths** — applied throughout.
- ✅ **Lesson #24 SSH-instability** — R-DEPLOY-6 attempted ; 3 timeouts → trader stop-loss → honest deferral.
- ✅ **Lesson #25 single-reviewer-domain-discipline** — a11y IMPORTANT-1 + code-reviewer S1+S2+S3 applied per discipline.
- ✅ **Lesson #34 lockstep CI-pin** — 3-place backend↔backend + backend↔frontend SurpriseState lockstep.
- ✅ **Lesson #37 DEMOTE framing** — `state=unavailable` is honest, no fabricated badge when range absent.
- ✅ **R-DEPLOY-6** — applied (step 3 succeeded ; step 4 SSH timeout triggered honest deferral).
- ✅ **R-WITNESS-EMPIRICAL r144 NEW** — the 7-step rule's post-deploy witness will run r146 Phase 0 ; r145 was pre-deploy review only.

## Mission Centrale axis impact

| #     | Axe                                         | Status pre-r145                      | Status post-r145                                                      |
| ----- | ------------------------------------------- | ------------------------------------ | --------------------------------------------------------------------- |
| 1     | Lecture Londres en cours                    | ✅ r123                              | ✅ unchanged                                                          |
| 2     | Calibrage NY 13h-16h                        | ✅ r123                              | ✅ unchanged                                                          |
| 3     | NY-window UI marker + holidays              | ✅ r132+r133                         | ✅ unchanged                                                          |
| 4     | Anticipation par profondeur                 | 🎯+1 r130                            | 🎯+1 unchanged                                                        |
| **5** | **Réactivité temps réel events 13h-16h NY** | 🎯+1 LEVEL DATA r144                 | **🎯+1 LEVEL DATA r144 + VISIBLE SURFACE CODE r145 ⭐** (deploy r146) |
| 6     | Apprentissage / conviction grounding        | ✅ CLOSED r142 + visual witness r143 | ✅ unchanged                                                          |
| 7     | Apprentissage autonomie                     | 🎯 LIVE                              | 🎯 LIVE unchanged                                                     |
| 8     | Manipulation watch                          | 🎯+1 PARTIAL r131                    | 🎯+1 PARTIAL unchanged                                                |

## Voie D held — 60 rounds streak

Zero `import anthropic` r145 (CI-guarded). Pure compute view-model + classifier wire ; same `fred_api_key` reused via r144 path ; no LLM call. Streak continues.
