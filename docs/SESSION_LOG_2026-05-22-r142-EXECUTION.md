# r142 — EXECUTION LOG — 2026-05-22

> **Status** : SHIPPED — Mission centrale axis-6 ✅ FULLY CLOSED.
> **Branch** : `claude/amazing-heyrovsky-80df1e` · **HEAD pre-r142** : `59ede2e` · **HEAD post-r142** : `26bf596`
> **Voie D streak** : 57 rounds (zero `import anthropic` ce round)
> **alembic** : `0052` (no new migration — code-only changes, drivers JSONB column from 0026 already in prod)

## TL;DR

r142 wires the engine-computed confluence drivers from `services/confluence_engine.py:assess_confluence()` into the `session_card_audit.drivers` JSONB column (was always NULL pre-r142) and surfaces them as a 4th tile "Drivers explicites" on `<ConvictionGroundingPanel>` (`/briefing/[asset]`). Mission centrale axis-6 ("Apprentissage / conviction grounding") transitions from 🎯+1 LEVEL r134 to ✅ FULLY CLOSED. The r134 panel was deliberately built around 3 grounding dimensions (mechanisms + scenarios + critic verdict) because the engine drivers were never wired — verified empirically in r134's lib JSDoc : _"confluence_drivers is null in every production card — verified empirically against /v1/sessions/EUR_USD on 2026-05-21"_. r142 unblocks that deferred dimension.

## R59-AUDIT-FIRST (doctrine #1 + lesson #32)

**2 parallel sub-agents dispatched** at session start :

1. **feature-dev:code-explorer** verified the audit-finding claim "80% plumbed already" from the paste-prompt v60 :
   - `Driver(factor, contribution, evidence, source)` dataclass at `confluence_engine.py:62-73` ✓
   - migration `0026_session_card_drivers.py` (drivers JSONB on session_card_audit) ✓
   - `SessionCard.drivers: list[dict[str, Any]] | None = None` at `types.py:162` ✓
   - `drivers=_dump_list(card.drivers)` persistence at `persistence.py:55` ✓
   - GAP CONFIRMED : `assess_confluence` called by `data_pool.py:4439` + `routers/confluence.py:128` + `cli/snapshot_confluence.py:44`, NEVER from `run_session_card.py` orchestrator path. `card.drivers` always None in prod.
   - Brier lockstep already OK : `services/brier_optimizer.py:DEFAULT_FACTOR_NAMES` ↔ `cli/run_brier_optimizer.py:_FACTOR_NAMES` identical 11 entries incl. `inflation_surprise` r137 — lesson #34 already respected.
   - Effort estimate : S-M, upper end of M (~3-4 dev-hours). Confidence MEDIUM (hidden complexities : double-call risk + wrong-column extractor + ADR-017 framing).

2. **researcher** doing R59 audit on the alternative r142 default candidate (provider reconciler for `economic_events.actual`, per paste-prompt v60 §1 "AUTO-RECOMMENDED") :
   - **Investing.com** : BLOCKED (hostile ToS storage clause + CF 2026 stack requires residential proxies + hallucinated-data risk under bot mitigation).
   - **FRED ALFRED** : PARTIAL viable (US-only `actual` ; NO `forecast_min`/`forecast_max` — ALFRED is vintage archive, not analyst-poll surface).
   - **Polymarket** : SKIP (binary YES/NO contracts, no analyst range — already wired r130 as indirect proxy).
   - **Trading Economics** : SKIP (subscription tier required, violates Voie D budget guard).
   - ⭐ **CRITICAL DISCOVERY** : `forex_factory.py:18-19` collector docstring lists only `<forecast>` + `<previous>`, but underlying FF XML schema MAY carry `<actual>` post-event (community parsers consistently include it). Free, respects existing FF rate-limit envelope (2 downloads / 5min combined ; r142 cron schedule 4 fires/day well under). Hard-gate on T+15min smoke test after a recent NFP/CPI fire. **Deferred to r143** as the lower-risk path.

**Decision** : ship axis-6 conviction driver-wiring (Option B from paste-prompt v60 §2). Closes a Mission axis FULLY (🎯+1 → ✅ transition) vs partial axis-5 +1 LEVEL DATA from the reconciler. Internal work, zero external dependency, fixes a discovered bug (`extract_confluence_drivers` reads `claude_raw_response` not `row.drivers`), unblocks the r134 deliberate-deferral. The FF XML `<actual>` reconciler becomes r143 binding default candidate #2.

## What shipped (9 files, +828 / -38)

| File                                                         | Change                                                                                                                                                                                                                                                                     | LOC delta |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `apps/api/src/ichor_api/cli/run_session_card.py`             | Module-top import of `assess_confluence` + orchestrator hook after `compose_key_levels_snapshot` ; default `regime="all"` to match `data_pool.py:4439` (R1 CRITICAL fix) ; passes `engine_drivers` via single `model_copy(update=...)` ; graceful-degradation on exception | +40 / -5  |
| `apps/api/src/ichor_api/schemas.py`                          | `ConfluenceDriver` extended with optional `evidence` + `source` (back-compat) + NEW `extract_engine_drivers` TRI-STATE helper + `from_orm_row` engine-first / LLM-fallback resolution                                                                                      | +103 / -8 |
| `apps/api/src/ichor_api/services/confluence_engine.py`       | `Driver.contribution` docstring stripped of "positive = long bias" verbatim + reframed as INTERNAL aggregation artifact (UI strips sign per r142 boundary)                                                                                                                 | +18 / -3  |
| `apps/api/tests/test_invariants_ichor.py`                    | 3 NEW r142 invariant tests (trader probe-tests #2 + #4 + #5)                                                                                                                                                                                                               | +114 / 0  |
| `apps/api/tests/test_session_card_extractors.py`             | 11 NEW r142 tests                                                                                                                                                                                                                                                          | +177 / -5 |
| `apps/web2/lib/api.ts`                                       | `ConfluenceDriverSchema` extended with `evidence?` + `source?`                                                                                                                                                                                                             | +7 / 0    |
| `apps/web2/lib/convictionGrounding.ts`                       | NEW constants + `ConfluenceDriverLite` + extended `ConvictionGrounding` + `deriveEngineDrivers` filter chain + extended `empty` flag                                                                                                                                       | +90 / -3  |
| `apps/web2/components/briefing/ConvictionGroundingPanel.tsx` | 4th tile after CRITIC VERDICT block ; ABSOLUTE-MAGNITUDE display ; whitespace-nowrap ; lang="en" wrap ; rich aria-label                                                                                                                                                    | +51 / -10 |
| `apps/web2/__tests__/convictionGrounding.test.ts`            | 12 NEW r142 vitest cases                                                                                                                                                                                                                                                   | +190 / -1 |

## Build gate (MEASURED, no forecast — doctrine #14)

- **pytest 158/158 pass** : 47 r141 economic_event_surprise + 3 drivers_column + 13 invariants_ichor incl. **3 NEW r142** + 41 extractors incl. **11 NEW r142** + cross-module regression. Zero regression on r141. ADR-017+009+023+029+077+079/080 invariants all green.
- **vitest 314/314 pass** across 14 test files : 24 r134 convictionGrounding base + **12 NEW r142** + cross-module.
- **tsc 0 errors** (strict mode incl. `exactOptionalPropertyTypes: true` + `noUncheckedIndexedAccess: true`).
- **eslint 0 warnings**.
- **next build OK** (full route table generated).
- **pre-commit hooks** : ruff format + prettier reformatted 2 files first pass ; re-staged + re-committed (doctrine #6 2-pass, NOT amend) ; all 13 hooks green incl. Ichor doctrinal invariants on second pass.

## Reviews (doctrine #17 — NEW visible UI 4-reviewer class)

4 reviewers dispatched in parallel post-test-green : ichor-trader + ui-designer + accessibility-reviewer + code-reviewer. All returned SHIP-WITH-FIXES.

### code-reviewer verdict : SHIP-WITH-FIXES — 1 CRITICAL · 5 SHOULD · 4 NICE

| Severity                                                                                            | Finding                                                                                                                                                                                                                                    | Action                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| CRITICAL R1                                                                                         | `assess_confluence` called with DIFFERENT regime values : hook passed `regime=quadrant` (post-Pass-4), data_pool passes default `regime="all"` (pre-Pass-1, regime unknown). Diverges weights / drivers between LLM-input and persistence. | **APPLIED** — hook now uses default `regime="all"` to match data_pool ; comment documents the timing constraint + r143+ regime-keyed evaluation deferred                                       |
| SHOULD-FIX S1 + S5                                                                                  | Tri-state design coherence — `extract_engine_drivers` collapsed `[]` to `None` + persistence collapsed `[]` to `None` → post-r142 cards with 0 drivers above threshold silently behave like legacy pre-r142 cards and trigger LLM fallback | **APPLIED** — extract returns `[]` for empty ; persistence drops `or None` collapse ; `from_orm_row` distinguishes `None`=legacy-fallback from `[]`=honest-absence-no-fallback ; tests updated |
| SHOULD-FIX S2                                                                                       | Late import inside try-block                                                                                                                                                                                                               | **APPLIED** — `assess_confluence` hoisted to module top                                                                                                                                        |
| SHOULD-FIX S3                                                                                       | Switch `evidence != null` to `source != null` filter                                                                                                                                                                                       | **REJECTED** — engine `Driver` has `evidence: str` non-optional + `source: str                                                                                                                 | None`optional, so`evidence != null` IS the more reliable engine marker (S3 had contract backwards). Pinned by trader probe-test #2 CI invariant |
| SHOULD-FIX S4                                                                                       | No orchestrator hook unit test (40 new LOC with zero unit test)                                                                                                                                                                            | **DEFERRED r143** — empirical witness post-deploy via curl `/v1/sessions/EUR_USD&limit=1` covers integration                                                                                   |
| NICE ×4 (N1 dedup, N2 KISS frontend O(n log n), N3 backend symmetric filter, N4 ADR-099 §Impl note) | acknowledged ; N1 acceptable, N2 GREEN, N3 documented, N4 planned closing-sync                                                                                                                                                             |

### ichor-trader verdict : SHIP-WITH-FIXES — 1 RED · 4 YELLOW · 5 GREEN · 5 probe-tests

| Severity      | Finding                                                                                                                                                                                                                                                                      | Action                                                                                                                                                                                                                                                                            |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RED-1         | ADR-017 framing leak : `Driver.contribution` docstring "positive = long bias, negative = short" + signed UI display reads as long-instruction. Footer "pas un signal" stamp does NOT bind numeric "+0.45" away from its long-bias meaning when the engine defines it as such | **APPLIED — trader fix option (a)** : UI strips sign and displays ABSOLUTE MAGNITUDE only ; engine docstring reframed to clarify INTERNAL aggregation artifact ; new CI invariant `test_r142_confluence_engine_driver_docstring_strips_directional_phrase` pins the docstring fix |
| YELLOW-1      | Evidence text not surfaced on UI                                                                                                                                                                                                                                             | **FLAG-NOT-FIX r143+** — would expand UI scope, deferred                                                                                                                                                                                                                          |
| YELLOW-2      | Anti-skill pocket leak (EUR_USD/usd_complacency n=13 + XAU_USD/usd_complacency n=19)                                                                                                                                                                                         | **FLAG-NOT-FIX r143+** — needs design call ; r143 candidate to wire `pocket_skill_reader.delta` cross-ref                                                                                                                                                                         |
| YELLOW-3      | Double-call of `assess_confluence`                                                                                                                                                                                                                                           | **FLAG-NOT-FIX r143+** — accept duplicate cost, r143 can consolidate                                                                                                                                                                                                              |
| YELLOW-4      | Engine-only filter `evidence != null` structural not contractual                                                                                                                                                                                                             | **APPLIED** via trader probe-test #2 CI invariant + ConfluenceDriver dataclass docstring marking `evidence` NON-OPTIONAL contract for engine entries                                                                                                                              |
| Probe-test #1 | ADR-017 regex against rendered tile HTML                                                                                                                                                                                                                                     | **DEFERRED r143** — needs RTL setup                                                                                                                                                                                                                                               |
| Probe-test #2 | Engine-only filter contract                                                                                                                                                                                                                                                  | **APPLIED** — `test_r142_extract_engine_drivers_every_entry_has_evidence`                                                                                                                                                                                                         |
| Probe-test #3 | Anti-skill pocket leak guard                                                                                                                                                                                                                                                 | **DEFERRED r143** (matches YELLOW-2)                                                                                                                                                                                                                                              |
| Probe-test #4 | Driver docstring source-inspection                                                                                                                                                                                                                                           | **APPLIED** — `test_r142_confluence_engine_driver_docstring_strips_directional_phrase`                                                                                                                                                                                            |
| Probe-test #5 | Lockstep registry guard                                                                                                                                                                                                                                                      | **APPLIED** — `test_r142_brier_optimizer_factor_names_lockstep`                                                                                                                                                                                                                   |

### ui-designer verdict : SHIP-WITH-FIXES — 2 IMPORTANT · 4 NIT · 6 GREEN

| Severity    | Finding                                                                                                | Action                                                                                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| IMPORTANT-1 | Detail line wraps mid-token on mobile viewport ≤ sm (`vix_term −0.32` splits across lines)             | **APPLIED** — `whitespace-nowrap` per `factor magnitude` token via per-driver span (line wraps between drivers, never mid-token)                                         |
| IMPORTANT-2 | Big mono number semantics drift — `3` count collides with adjacent Confluence's `3 méc.` rhythm        | **APPLIED** — big number suffix `3 drv.` mirrors Confluence count rhythm (rejected ui-designer Fix A "show `+0.55` as headline" because it would AGGRAVATE trader RED-1) |
| NIT-1       | `tabular-nums` on single digit no-op                                                                   | acknowledged, single-digit doesn't break                                                                                                                                 |
| NIT-2       | Doubly defensive empty guard                                                                           | acknowledged (TS narrowing requirement)                                                                                                                                  |
| NIT-3       | snake_case factor names read literally by FR SR                                                        | **APPLIED** (3/4 concordant with a11y + trader) — aria-label `replace(/_/g, " ")`                                                                                        |
| NIT-4       | "driver" anglicism                                                                                     | flagged-not-fix (consistent with visible label)                                                                                                                          |
| GREEN ×6    | U+2212 minus / no diverging bars / monochrome / flex-wrap robust / engine-only filter / honest absence | acknowledged                                                                                                                                                             |

### accessibility-reviewer verdict : SHIP-WITH-FIXES — 1 IMPORTANT · 3 SHOULD · 4 GREEN

| Severity    | Finding                                                                                                                              | Action                                                                                                                                              |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| IMPORTANT-1 | aria-label loses count magnitude + signed contributions vs visible text (first tile whose visible payload is RICHER than aria-label) | **APPLIED** — aria-label now includes per-driver magnitudes spoken                                                                                  |
| SHOULD-2    | U+2212 read-aloud reliability across screen readers                                                                                  | **APPLIED** — sign STRIPPED from UI entirely per trader RED-1 fix (this concern obsoleted)                                                          |
| SHOULD-3    | snake_case factor names spoken by FR SR                                                                                              | **APPLIED** (3/4 concordant) — aria-label snake_case → space + `<span lang="en">` wraps inline factor names (SC 3.1.2 Language of Parts + SC 1.3.1) |
| SHOULD-4    | "Drivers explicites" jargon vs panel heading                                                                                         | flagged ; keep current label (preserves visible/aria consistency per ui-designer NIT-4)                                                             |
| GREEN ×4    | SC 1.4.3 Contrast / SC 1.4.10 Reflow / SC 4.1.2 role="group" / SC 4.1.3 not-a-live-region                                            | acknowledged                                                                                                                                        |

### Fix-cluster summary

**Applied** : 1 CRITICAL + 1 RED + 5 SHOULD/IMPORTANT + 3/4-concordant aria-label + 3 trader probe-tests pinned as CI invariants + engine docstring update.

**Flag-not-fix r143+** : trader YELLOW-1 evidence-text UI, YELLOW-2 anti-skill-pocket-leak (matches probe-test #3), YELLOW-3 double-call consolidation, code-reviewer S4 AsyncMock test, trader probe-test #1 RTL-rendered-HTML-regex.

**Rejected** : code-reviewer S3 (S3 had the contract direction backwards — `evidence` is the non-optional engine marker, not `source`).

## Re-run after fix-cluster

- pytest 158/158 pass (no regression on the 144 prior + all 14 new r142 tests green)
- vitest 314/314 pass (no regression on the 302 prior + all 12 new r142 tests green)
- tsc 0 errors
- eslint 0 warnings
- next build OK

## Deploy (lesson #24 SSH-instability handled via NEW R-DEPLOY-6 mitigation)

`redeploy-api.sh` step 3 (`tar-over-ssh` long-lived pipe) failed 3× on SSH timeout — same failure mode documented r137-r141. R-DEPLOY-6 NEW mitigation : decompose into 3 short retryable calls.

**Step-by-step trace** :

1. `tar czf /tmp/ichor_api_r142.tar.gz --exclude='__pycache__' ichor_api` (local, < 1s) ✓
2. `scp /tmp/ichor_api_r142.tar.gz ichor-hetzner:/tmp/` (transient short SSH, 5s) ✓
3. Short SSH call : `mkdir staging + tar xzf + sudo rsync --delete + sudo chown ichor` ✓ → DEPLOY_RSYNC_OK
4. Short SSH call : `sudo systemctl restart ichor-api && sleep 3 && curl /healthz` ✓ → healthz=200

### Empirical witness backend (MEASURED)

```
$ ssh ichor-hetzner "sudo bash -c 'set -a; . /etc/ichor/api.env; set +a; cd /opt/ichor/api/src && /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_session_card EUR_USD pre_londres --dry-run'"
2026-05-22 15:52:47 [info] brain.pass1.done       conf=72.0 quadrant=haven_bid
2026-05-22 15:52:47 [info] brain.pass2.done       asset=EUR_USD bias=short conv=65.0
2026-05-22 15:52:47 [info] brain.pass3.done       n_counter=1 revised=50.0
2026-05-22 15:52:47 [info] brain.pass4.done       n_conditions=1
2026-05-22 15:52:47 [info] brain.critic.done      conf=1.0 n_findings=0 verdict=approved
2026-05-22 15:52:48 [info] session_card.persisted asset=EUR_USD duration_ms=32000 id=faa8d081-3e1e-487c-abb7-2d819a5abc4a session_type=pre_londres verdict=approved
OK · session_card_audit row written
```

```
$ curl http://127.0.0.1:8000/v1/sessions?asset=EUR_USD&limit=1
id: faa8d081-3e1e-487c-abb7-2d819a5abc4a
asset: EUR_USD
confluence_drivers count: 7
sample drivers (first 3):
[
  {"factor": "microstructure_ofi", "contribution": 0.052, "evidence": "Lee-Ready OFI 4h = +0.05 (signed_volume=+2107 / total=40843)", "source": "polygon_intraday:EUR_USD@4h_ofi"},
  {"factor": "daily_levels",       "contribution": -0.029, "evidence": "spot 1.16033 at 46% of PDH-PDL range (1.15750-1.16360)", "source": "polygon_intraday:EUR_USD@daily_levels"},
  {"factor": "funding_stress",     "contribution": -0.040, "evidence": "stress_score = +0.10 (>0 = stress, USD haven)", "source": "empirical_model:funding_stress"}
]
```

**Empirical verdict** : r142 orchestrator hook EMPIRICALLY POPULATES `card.drivers` with 7 engine drivers including factor + signed contribution + evidence + source. Each driver passes the engine-only filter `evidence != null`. All drivers in this sample are below the `|0.2|` threshold so the UI tile would render honest silent absence — but the FOUNDATION is wired end-to-end : a card with strong drivers above threshold would surface them.

### Frontend Hetzner deploy DEFERRED

`redeploy-web2.sh` failed at the `pnpm build` step on a pre-existing TS portability emit error :

```
./app/admin/error.tsx:10:25
Type error: The inferred type of 'AdminError' cannot be named without a reference to '.pnpm/@types+react@19.2.14/node_modules/@types/react'. This is likely not portable. A type annotation is necessary.
```

File `apps/web2/app/admin/error.tsx` dated 2026-05-07 (Phase B.5d) — NOT r142-introduced. Likely surfaced by recent dependabot @types/react bump. Out of r142 scope per doctrine #2 strict scope. Documented as r143 binding default candidate #1 (1-line fix).

r142 frontend code IS committed + pushed + locally validated (tsc 0 + vitest 36/36 + next build OK). CF Pages auto-deploy on PR merge will ship the public surface.

## Honest scope · what r142 does NOT do (per doctrine #2)

- ❌ **No new ADR** — additive wire-existing-machinery work, doctrine #9 dated §Impl(r142) APPEND
- ❌ **No new migration** — drivers JSONB column from 0026 (Sprint 16) already in prod
- ❌ **No new lesson** in the form of empirical surprise — R-DEPLOY-6 is the codified operational upgrade to lesson #24
- ❌ **No regime-keyed weight evaluation** — hook uses default `regime="all"` to match data_pool ; r143+ candidate to refactor Pass-1-then-replay-data_pool
- ❌ **No anti-skill pocket gating** — trader YELLOW-2 deferred to r143+ (pocket_skill_reader cross-ref)
- ❌ **No evidence text on UI tile** — trader YELLOW-1 deferred to r143+
- ❌ **No FF XML `<actual>` reconciler** — R59-discovered path, r143 binding default candidate #2
- ❌ **No frontend Hetzner deploy** — pre-existing build issue blocks `redeploy-web2.sh`, r143 binding default candidate #1 (1-line fix)

## What r143 ships next (binding default candidates)

1. **admin/error.tsx return-type annotation** ⭐ AUTO-RECOMMENDED (unblocks r142 frontend Hetzner deploy + future web2 deploys). 1-line fix. Effort S.
2. **`forex_factory.py` XML `<actual>` parse-and-persist** ⭐ R59-DEFERRED-PATH (closes r141 dormant infrastructure ; lights up `economic_events.actual` for ~70% of FF-listed events globally). Hard-gate on T+15min smoke test post-NFP/CPI. Effort S-M.
3. **Trader probe-test #1 ADR-017 regex against rendered HTML** via RTL setup. Effort S-M.
4. **Trader YELLOW-2 anti-skill pocket leak guard** via `pocket_skill_reader.delta` cross-ref. Effort M.
5. **Code-reviewer S4 orchestrator hook AsyncMock unit test**. Effort S.

## Doctrine + lesson alignment

- ✅ **Doctrine #1 R59-first** — 2 parallel sub-agents (code-explorer + researcher) audited both option A (reconciler) and option B (driver-wiring) empirically before scope decision
- ✅ **Doctrine #2 strict scope** — 1 round = 1 axis closure ; 4 YELLOW + 1 pre-existing build issue + 1 S4 test deferred to r143
- ✅ **Doctrine #6 commit single-step, NOT amend** — pre-commit hooks reformatted 2 files first pass ; re-staged + re-committed cleanly on 2nd pass
- ✅ **Doctrine #9 dated §Impl APPEND, NO new ADR** (additive wire-existing-machinery — no genuinely-new architecture)
- ✅ **Doctrine #11 calibrated honesty** — engine drivers are an INDEPENDENT second opinion, NOT a fabricated decomposition of `conviction_pct` ; honest silent absence when topDrivers empty
- ✅ **Doctrine #14 build gate on COMMITTED shape** — full pytest + vitest + tsc + eslint + next build green BEFORE deploy
- ✅ **Doctrine #17 parallel reviewers (4-reviewer NEW visible UI class)** — trader + ui-designer + a11y + code-reviewer dispatched in single message
- ✅ **Lesson #1 MEASURED not forecast** — 158 backend + 314 frontend tests run, empirical witness card `faa8d081` confirmed populated
- ✅ **Lesson #22 worktree-mismatch absolute paths** — applied throughout sub-agent prompts + verified `python -c 'import X; print(X.__file__)'` resolves to worktree
- ✅ **Lesson #24 SSH-instability** — NEW R-DEPLOY-6 mitigation upgrade (decompose long-lived `tar-over-ssh` into 3 short retryable calls)
- ✅ **Lesson #25 single-reviewer-domain-discipline** — a11y findings applied even without 2/4 concordance because WCAG IS the reviewer's discipline ; code-reviewer R1 applied as the single critical correctness authority
- ✅ **Lesson #34 confluence-driver-Brier-tunable** — NOT triggered (r142 adds zero new factor ; lockstep verified empirically by code-explorer + pinned by NEW CI invariant `test_r142_brier_optimizer_factor_names_lockstep`)
- ✅ **Lesson #35 envelope-the-shape changes are breaking** — `ConfluenceDriver` extended via OPTIONAL fields (back-compat preserved) ; vitest cross-module 314/314 confirms no consumer broke

## Mission Centrale axis impact

| #     | Axe                                      | Status pre-r142            | Status post-r142                                              |
| ----- | ---------------------------------------- | -------------------------- | ------------------------------------------------------------- |
| 1     | Lecture Londres en cours                 | ✅ r123                    | ✅ unchanged                                                  |
| 2     | Calibrage NY 13h-16h                     | ✅ r123                    | ✅ unchanged                                                  |
| 3     | NY-window UI marker + holidays           | ✅ r132+r133               | ✅ unchanged                                                  |
| 4     | Anticipation par profondeur              | 🎯+1 r130                  | 🎯+1 unchanged                                                |
| 5     | Réactivité temps réel events 13h-16h NY  | 🎯+1 LEVEL FOUNDATION r141 | 🎯+1 unchanged (r143 reconciler will deepen to +1 LEVEL DATA) |
| **6** | **Apprentissage / conviction grounding** | 🎯+1 r134                  | **✅ FULLY CLOSED r142** ⭐                                   |
| 7     | Apprentissage autonomie                  | 🎯 LIVE                    | 🎯 LIVE unchanged                                             |
| 8     | Manipulation watch                       | 🎯+1 PARTIAL r131          | 🎯+1 PARTIAL unchanged                                        |

**r142 is the 3rd Mission centrale axis to reach ✅ CLOSED** (after axes 1-2 r123 + axis 3 r132+r133). 3 of 8 axes CLOSED ; 5 of 8 remain 🎯+1 LEVEL or LIVE-PARTIAL.

## Voie D held — 57 rounds streak

Zero `import anthropic` this round (CI-guarded by `test_no_anthropic_sdk_imports` invariant). No LLM call added — pure compute orchestrator hook + frontend extension. Streak continues.

## R-DEPLOY-6 NEW operational lesson codified

**Lesson #24 mitigation upgrade** : when `redeploy-api.sh` step 3 `tar-over-ssh` pipe fails 3+× on SSH timeout, decompose into 3 short retryable calls :

1. `tar czf /tmp/X.tar.gz -C <local-repo-root> --exclude='__pycache__' <package>` (local, no SSH)
2. `scp /tmp/X.tar.gz ichor-hetzner:/tmp/` (transient short SSH, ~5s, individually retryable)
3. `ssh ichor-hetzner "mkdir -p staging && tar xzf /tmp/X.tar.gz -C staging && sudo rsync -a --delete staging/<package>/ <stable-path>/ && sudo chown -R ichor:ichor <stable-path> && sudo systemctl restart <service>"` (single short SSH, ~10s, retryable)

Each call < 15s vs the 30-60s long-lived pipe failure mode. Pattern applied successfully r142 after 3 attempted retries of the canonical `redeploy-api.sh` failed at step 3.
