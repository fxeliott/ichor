# r144 — EXECUTION LOG — 2026-05-22

> **Status** : SHIPPED + DEPLOYED + WITNESSED + CRON LIVE.
> **Branch** : `claude/amazing-heyrovsky-80df1e` · **HEAD pre-r144** : `6d35aae` · **HEAD post-r144** : `1c8e954` (+ closing-sync TBD)
> **Voie D streak** : 59 rounds (zero `import anthropic` ce round)
> **No new migration** : code + cron + feature flag seed only ; backend reuses r141 schema.

## TL;DR

r144 lights up the r141 dormant `economic_events.actual` column for US events via FRED ALFRED first-vintage backfill. Mission centrale axis-5 transitions from 🎯+1 LEVEL FOUNDATION r141 → 🎯+1 LEVEL DATA r144 (partial closure : US-only, 12/15 tier-1 events covered, 3 critical gaps documented).

Empirical witness on prod : 18 events populated on first backfill (CPI 3.78 / Core CPI 0.38 / NFP 115 BLS-PAYEMS / Unemployment Rate 4.3 / Claims 200K / JOLTS 6866 / AHE 0.34 / UoM 49.8). Cron timer LIVE (`ichor-actuals-reconciler.timer` next fire Sat 2026-05-23 01:15:12 CEST, 4×/day cadence). Voie D held 59 rounds.

**NEW lesson R-WITNESS-EMPIRICAL** codified : post-deploy empirical witness on real prod data is a SEPARATE review pass complementing pre-deploy 2-reviewer/4-reviewer dispatch. Reviewers caught Core Retail Sales + Trimmed Mean CPI collision class but missed ADP false-positive — only empirical dry-run revealed it.

## Phase 0 — R59 dual-audit (2 parallel sub-agents)

### researcher : FRED ALFRED API specifics 2026

Verified via WebSearch + primary FRED docs :

- **Base URL** : `https://api.stlouisfed.org/fred` (same host FRED + ALFRED)
- **Endpoint** : `GET /series/observations?series_id=X&realtime_start=YYYY-MM-DD&realtime_end=YYYY-MM-DD&api_key=K&file_type=json`
- **Auth** : same `fred_api_key` (env `ICHOR_API_FRED_API_KEY`) — no separate ALFRED key
- **Rate limit** : 120 req/min per key (community-corroborated)
- **Vintage semantic** : `realtime_start = realtime_end = D` returns snapshot known on day D = first-vintage release value (verified via GDP Q1 2014 worked example)
- **12 viable FRED series** mapped to tier-1 USD events ; 3 critical gaps :
  - ❌ ISM Manufacturing PMI (NAPM mnemonic archived, licensing-blocked)
  - ❌ ISM Services PMI (same licensing block)
  - ❌ ADP Employment Change (NPPTTL discontinued)
- **Top 3 risks** identified : series-ID drift (FRED renames silently) / title→series brittleness / first-vintage same-day revision (rare).

### feature-dev:code-explorer : established Ichor patterns

Mapped patterns to mirror :

- `httpx.AsyncClient` pattern from `collectors/fred.py:21` (single client reused across iterations)
- Bundesbank CLI canonical template at `cli/run_bundesbank_bund.py` (feature flag + dry-run + asyncio.run + `get_engine().dispose()` finally)
- 0.2s inter-request sleep from `collectors/fred.py:backfill_history` (free-tier rate limit ceiling)
- Broad `except Exception` + `log.warning` + return None graceful-degradation
- Frozen dataclass for result tally
- Targeted UPDATE (NOT piggy-backed on FF UPSERT — `forex_factory.py:persist_events` set\_= dict does NOT include `actual` → clean separation, zero race)
- Effort estimate S-M (4-6 hours)

## Phase 1 — Implementation (4 files +700 LOC)

### `services/economic_event_actuals_reconciler.py` (NEW, ~340 LOC)

Pure service. Key components :

- **`TITLE_FRAGMENT_TO_SERIES`** : 19-entry tuple. Canonical FF title substring → FRED series_id + optional units transform (`chg`/`pch`/`pc1`/`None`). Order matters (Core CPI before generic CPI). Case-insensitive substring match.
- **`TITLE_FRAGMENT_BLOCKED`** (NEW r144) : 8-entry negative-list short-circuit. Catches collision class : ADP / Trimmed Mean CPI / Median CPI / Supercore CPI / Sticky-Price CPI / Core Retail Sales / PCE Price Index Ex- / Nonfarm Productivity / Unit Labor Costs.
- **`map_title_to_series(title)`** : pure-fn. Negative-list short-circuit checked BEFORE positive dispatch (per r144 code-reviewer S1+S2 + round-2 fix).
- **`fetch_alfred_actual(series_id, release_date, api_key, *, client, units)`** : async httpx wrapper to `/series/observations`. Mirrors `collectors/fred.py:fetch_latest` graceful-degradation (broad except + structured log + return None).
- **`reconcile_actuals(session, *, api_key, lookback_days=14, settle_minutes=15, currency="USD", dry_run=False)`** : main. SELECTs `currency='USD' AND actual IS NULL AND scheduled_at <= now()-15min AND scheduled_at > now()-14d` + sequential per-event loop with 0.2s sleep + targeted UPDATE (ADDITIVE only, never touches `forecast_min/max` or `fetched_at` per r144 code-reviewer S3 fix). Returns `ReconcilerResult` frozen dataclass.
- **`ReconcilerResult`** : frozen dataclass 6 counters (examined / updated / skipped_unmapped / skipped_no_scheduled_at / skipped_fetch_failed / skipped_no_value).

### `cli/run_economic_event_actuals_reconcile.py` (NEW, ~140 LOC)

Bundesbank canonical pattern. Feature flag `actuals_reconciler_enabled` (default OFF). Exit codes 0 success / 1 feature flag OFF / 2 ICHOR_API_FRED_API_KEY empty. CLI args `--dry-run` / `--lookback-days` / `--settle-minutes` / `--currency`.

### `tests/test_economic_event_actuals_reconciler.py` (NEW, ~430 LOC, 35 tests)

5 test classes :

- **TestMapTitleToSeries** (12 tests) : NFP variants + Core CPI before headline + AHE mappings + blocked fragments incl. ADP + Trimmed Mean CPI + Core Retail Sales + Productivity stats + unknown title None + case-insensitive + impact suffix
- **TestTitleFragmentTableInvariants** (4 tests) : frozen tuple + ≥12 distinct series + units canonical + NO BUY/SELL tokens + Core CPI before generic CPI order
- **TestTitleFragmentBlockedTable** (NEW r144, 3 tests) : frozen + ≥5 entries + no BUY/SELL tokens
- **TestFetchAlfredActual** (7 async tests) : happy path + units passthrough + empty observations + FRED "." marker + HTTP 404 + network error + string-form pass-through
- **TestReconcilerResult + TestModuleConstants** (6 tests) : frozen + required fields + FRED_BASE + sleep + lookback + settle pinned

### `scripts/hetzner/register-cron-actuals-reconciler.sh` (NEW, ~70 LOC, chmod +x)

Systemd timer `OnCalendar=*-*-* 01,07,13,19:15:00 Europe/Paris` (4×/day offset 15min from FF collector fires) + `RandomizedDelaySec=120` + `Persistent=true` + `SuccessExitStatus=0 1 2`.

## Phase 2 — Build gate + 2-reviewer concordance

### Build gate (MEASURED — doctrine #14)

- **pytest 193/193 pass** (35 r144 + 158 cross-module : 47 r141 economic_event_surprise + 13 invariants_ichor + 41 session_card_extractors + 3 drivers_column + others). Zero regression on r141/r142/r143.
- **ADR-017 invariants all green** on the new module (no BUY/SELL tokens in `TITLE_FRAGMENT_TO_SERIES` nor `TITLE_FRAGMENT_BLOCKED`).
- **pre-commit hooks** : ruff auto-fix 8 errors first pass (sort imports + format) ; re-stage + re-commit cleanly on 2nd pass (doctrine #6).

### Reviews (doctrine #17 — backend-LLM-data-pool class = 2-reviewer)

#### ichor-trader verdict : SHIP-WITH-FIXES — 0 RED + 4 YELLOW + GREEN majority

| Severity     | Finding                                                      | Action                                                                                                                    |
| ------------ | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| YELLOW Y1    | `log.debug` on skipped_unmapped too quiet for ops audit      | **APPLIED** : promoted to `log.info`                                                                                      |
| YELLOW Y2(a) | CI invariant FF XML coverage %                               | DEFERRED r145 (upgraded to BINDING DEFAULT post-round-2)                                                                  |
| YELLOW Y2(b) | `"federal funds rate"` fragment drag on FOMC sub-events      | **REJECTED** : empirical check confirms FF "Federal Funds Rate" event is distinct from FOMC Statement/Press Conf, no drag |
| YELLOW Y2(c) | Average Hourly Earnings tier-1 unmapped                      | **APPLIED** : added AHETPI mappings                                                                                       |
| YELLOW Y3    | No `actual_source` column for Critic-attribution             | DEFERRED r145 (single-provider today acceptable)                                                                          |
| YELLOW Y4    | lookback_days=14 tight for GDP quarterly                     | DOC : add RUNBOOK entry for `--lookback-days 90` catch-up                                                                 |
| GREEN        | DFEDTARU correct upper-bound match for FF Federal Funds Rate | docstring lock added                                                                                                      |
| GREEN        | First-vintage idempotency correct trader-grade discipline    | acknowledged                                                                                                              |

#### code-reviewer verdict : SHIP-WITH-FIXES — 3 SHOULD-FIX + 10 NICE + 0 RED

| Severity               | Finding                                                                                                                 | Action                                                |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| SHOULD-FIX S1 CRITICAL | `"Core Retail Sales m/m"` falsely matches `"retail sales m/m"` → RSAFS (headline). Data correctness regression          | **APPLIED** : `TITLE_FRAGMENT_BLOCKED` negative-list  |
| SHOULD-FIX S2 CRITICAL | `"Trimmed Mean CPI y/y"` falsely matches `"cpi y/y"` → CPIAUCSL. Same collision class                                   | **APPLIED** : `TITLE_FRAGMENT_BLOCKED`                |
| SHOULD-FIX S3 CRITICAL | `fetched_at = now` on UPDATE overwrites FF audit timestamp                                                              | **APPLIED** : removed from `update().values()`        |
| NICE N1                | `shouldShowSoftCalibrationCaveat` analog — single-consumer helper                                                       | N/A — different round                                 |
| NICE N6                | `event.scheduled_at is None` counted as `skipped_unmapped`                                                              | **APPLIED** : added `skipped_no_scheduled_at` counter |
| NICE N8                | Docstring says "matching FF text shape" but FRED returns bare numeric                                                   | **APPLIED** : reworded docstring                      |
| NICE N7                | SuccessExitStatus 0 1 2 anomalous vs canonical 0 1                                                                      | DOC : explained in script docstring                   |
| GREEN ×8               | ADR-017 / Voie D / idempotency / feature flag / httpx lifecycle / rate-limit / UPDATE no race / ReconcilerResult frozen | acknowledged                                          |

#### Concordance

- **CONCORDANT 2/2** : trader Y2 (b/c) + code-reviewer S1 + S2 → collision class fixes applied via `TITLE_FRAGMENT_BLOCKED`
- **Single-domain code-reviewer** : S3 `fetched_at` overwrite — DATA CORRECTNESS authority → APPLIED
- **Single-domain trader** : Y1 log.info promotion — ADR-017 observability authority → APPLIED
- **r145 deferrals** : Y2(a) FF XML coverage CI / Y3 actual_source / Y4 RUNBOOK / N1 / r144 ADR-017 web2 RTL (carried from r143)

## ROUND-2 POST-DEPLOY EMPIRICAL-WITNESS AUDIT FIX (NEW pattern observation)

Pre-deploy 2-reviewer dispatch caught Core Retail Sales + Trimmed Mean CPI false-positives. Deployed backend via R-DEPLOY-6. Seeded feature flag = true. Ran empirical dry-run on prod 30-day window :

```
$ sudo bash -c '. /etc/ichor/api.env; cd /opt/ichor/api/src && /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_economic_event_actuals_reconcile --dry-run --lookback-days 30 --currency USD'
...
[info] alfred.reconcile.updated  currency=USD dry_run=True release_date=2026-05-06 series_id=PAYEMS title='ADP Non-Farm Employment Change' value=178
...
```

**FALSE-POSITIVE DETECTED** : `'ADP Non-Farm Employment Change'` matched substring `'non-farm employment change'` → mapped PAYEMS (BLS official) instead of being SKIPPED (per researcher R59 audit ADP is NPPTTL discontinued, NOT in mapping). **Silent data corruption risk** — same collision class as code-reviewer S1+S2 but missed by 2-reviewer dispatch and revealed ONLY by empirical witness against real prod data.

**Round-2 fix-cluster applied** :

- Added `"adp"` to `TITLE_FRAGMENT_BLOCKED`
- Added `"nonfarm productivity"` + `"unit labor costs"` defensive blocks (BLS productivity stats sharing "nonfarm" substring with NFP)
- Adversarial probe tests updated to pin the new blocks
- 79/79 tests pass post round-2

Commit `1c8e954` shipped + re-deployed via R-DEPLOY-6.

### Re-witness dry-run post round-2 fix

```
[info] alfred.reconcile.complete examined=108 lookback_days=30 skipped_fetch_failed=0 skipped_no_value=0 skipped_unmapped=90 updated=18
OK · examined=108 updated=18 unmapped=90 fetch_failed=0 no_value=0
```

- ADP correctly moved from `updated` to `skipped_unmapped` (count 89 → 90)
- `skipped_fetch_failed` went from 1 → 0 (the failing fetch was the ADP collision causing FRED to query for a date not in PAYEMS vintage history)
- Total update count = 18 (correctly NFP via BLS-PAYEMS not ADP)

### NEW pattern observation : R-WITNESS-EMPIRICAL

Pre-deploy 2-reviewer/4-reviewer dispatch is INSUFFICIENT to catch all collision-class data-correctness bugs. Reviewers can spot KNOWN patterns but ADP false-positive was missed by 2 reviewers and revealed ONLY by empirical dry-run on real prod data. **Codified rule** :

1. Pre-deploy : full 2-reviewer (backend-LLM-data-pool) OR 4-reviewer (NEW visible UI) dispatch + fix-cluster
2. Deploy to prod with feature flag OFF
3. Seed flag = true
4. Run CLI `--dry-run --lookback-days N` on prod data
5. Inspect `alfred.reconcile.updated` log events for unexpected mappings
6. IF new collisions discovered → apply round-2 fix-cluster + commit + re-deploy + re-witness
7. ONLY THEN leave flag ON for live cron

Mirror of r142 + r143's empirical witness pattern but EXTENDED to "round-2 fix-cluster if witness reveals new issues".

## Phase 3 — LIVE backfill + cron registration

### LIVE backfill (non-dry-run, 30-day window)

```
[info] alfred.reconcile.complete examined=108 lookback_days=30 skipped_fetch_failed=0 skipped_no_value=0 skipped_unmapped=90 updated=18
OK · examined=108 updated=18 unmapped=90 fetch_failed=0 no_value=0
```

### Empirical psql verify

```
$ sudo -u postgres psql -d ichor -c "SELECT COUNT(*) FILTER (WHERE actual IS NOT NULL) FROM economic_events WHERE currency='USD' AND scheduled_at > now() - interval '30 days';"
 non_null
----------
       18
```

**Sample populated events** :

| FF title                      | release_date | FRED series | value   | units |
| ----------------------------- | ------------ | ----------- | ------- | ----- |
| CPI y/y                       | 2026-05-12   | CPIAUCSL    | 3.77925 | pc1   |
| Core CPI m/m                  | 2026-05-12   | CPILFESL    | 0.37646 | pch   |
| Prelim UoM Consumer Sentiment | 2026-05-08   | UMCSENT     | 49.8    | level |
| Average Hourly Earnings m/m   | 2026-05-08   | AHETPI      | 0.34247 | pch   |
| Non-Farm Employment Change    | 2026-05-08   | PAYEMS      | 115     | chg   |
| Unemployment Rate             | 2026-05-08   | UNRATE      | 4.3     | level |
| Unemployment Claims           | 2026-05-07   | ICSA        | 200000  | level |
| JOLTS Job Openings            | 2026-05-05   | JTSJOL      | 6866    | level |

### Cron timer LIVE

```
$ sudo bash /tmp/register-cron-actuals-reconciler.sh
Created symlink /etc/systemd/system/timers.target.wants/ichor-actuals-reconciler.timer → /etc/systemd/system/ichor-actuals-reconciler.timer.
=== Installed FRED ALFRED actuals reconciler timer (r144) ===
NEXT                            LEFT LAST PASSED UNIT                           ACTIVATES
Sat 2026-05-23 01:15:12 CEST 5h 2min -    -      ichor-actuals-reconciler.timer ichor-actuals-reconciler.service
```

Next fire `Sat 2026-05-23 01:15:12 CEST`. 4×/day cadence : 01:15 / 07:15 / 13:15 / 19:15 Paris (offset 15min from FF collector fires 03/09/15/21h to ensure FF has upserted event row first).

## Honest scope · what r144 does NOT do (per doctrine #2)

- ❌ **No new ADR** (additive service + cron, established patterns inherited — doctrine #9 dated §Impl(r144) APPEND)
- ❌ **No new migration** (uses r141 schema unchanged)
- ❌ **No frontend changes** (UI surface for r141 surprise classifier is r145+ candidate dependency)
- ❌ **No `forecast_min`/`forecast_max` writes** (analyst-range envelope needs different provider class)
- ❌ **No T+24h revision overwrite** (first-vintage preserved ; `actual_revised` column deferred r145+)
- ❌ **No EU/UK/JP/AU/CA `actual`** (ECB/ONS/BoJ/RBA/StatCan APIs deferred r145+)
- ❌ **No `actual_source` column** (single-provider acceptable, multi-provider needs Critic-attribution column r145+)
- ❌ **No FF XML title-coverage CI invariant** (upgraded to r145 binding default after round-2 ADP collision)

## r145 binding default candidates

1. ⭐ **FF XML title-coverage CI invariant** (trader Y2(a) UPGRADED to BINDING DEFAULT post-round-2). Effort S-M.
2. **ADR-017 web2 caveat RTL regex** (deferred r143+r144). Effort S-M.
3. **`actual_source` column** (trader Y3). Effort S.
4. **`actual_revised` T+24h overwrite column** (trader Y3+Y4). Effort S-M.
5. **API projection + frontend visibility for r141 surprise classifier** — now data flowing. Effort M.

## Doctrine + lesson alignment

- ✅ **Doctrine #1 R59-first** — 2 parallel sub-agents (researcher + code-explorer) verified API + patterns BEFORE code
- ✅ **Doctrine #2 strict scope** — 1 round = 1 axis-5 partial closure ; 4 YELLOW + 1 RUNBOOK + ADR-017 RTL deferred r145
- ✅ **Doctrine #4 SSOT** — `TITLE_FRAGMENT_TO_SERIES` single source ; `parse_economic_value` reused from r141 not duplicated
- ✅ **Doctrine #6 commit single-step, NOT amend** — pre-commit hooks 2-pass on feat commit
- ✅ **Doctrine #9 dated §Impl APPEND, NO new ADR** (additive service, established patterns)
- ✅ **Doctrine #11 calibrated honesty** — 3 critical gaps DOCUMENTED, never fabricated mappings ; `actual` stays NULL for unmapped/blocked events
- ✅ **Doctrine #14 build gate on COMMITTED shape** — pytest 193/193 + ADR-017 invariants green BEFORE deploy
- ✅ **Doctrine #17 2-reviewer (backend-LLM-data-pool class)** — trader + code-reviewer parallel
- ✅ **Lesson #1 MEASURED not forecast** — 35 r144 + 158 cross-module tests run, empirical dry-run + LIVE backfill + psql verify
- ✅ **Lesson #22 worktree-mismatch absolute paths** — applied throughout
- ✅ **Lesson #24 SSH-instability** — N/A r144 (R-DEPLOY-6 from r142 applied empirically successful, no SSH timeout)
- ✅ **Lesson #25 single-reviewer-domain-discipline** — code-reviewer S3 + trader Y1 applied per discipline
- ✅ **Lesson #34 lockstep CI-pin** — N/A (no new factor added, no Brier registry update needed)
- ✅ **Lesson #37 DEMOTE framing** — ISM/ADP/CCI/Trimmed Mean CPI/Core Retail Sales explicitly UNMAPPED + DOCUMENTED ; never fabricated
- ✅ **R-DEPLOY-6** (lesson #24 mitigation r142) — applied for backend deploy
- ✅ **NEW R-WITNESS-EMPIRICAL r144** — post-deploy empirical witness as separate review pass + round-2 fix-cluster if collisions discovered

## Mission Centrale axis impact

| #     | Axe                                         | Status pre-r144                      | Status post-r144                                                   |
| ----- | ------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------ |
| 1     | Lecture Londres en cours                    | ✅ r123                              | ✅ unchanged                                                       |
| 2     | Calibrage NY 13h-16h                        | ✅ r123                              | ✅ unchanged                                                       |
| 3     | NY-window UI marker + holidays              | ✅ r132+r133                         | ✅ unchanged                                                       |
| 4     | Anticipation par profondeur                 | 🎯+1 r130                            | 🎯+1 unchanged                                                     |
| **5** | **Réactivité temps réel events 13h-16h NY** | 🎯+1 LEVEL FOUNDATION r141           | **🎯+1 LEVEL DATA r144 ⭐** (partial US-only, 18 events populated) |
| 6     | Apprentissage / conviction grounding        | ✅ CLOSED r142 + visual witness r143 | ✅ unchanged                                                       |
| 7     | Apprentissage autonomie                     | 🎯 LIVE                              | 🎯 LIVE unchanged                                                  |
| 8     | Manipulation watch                          | 🎯+1 PARTIAL r131                    | 🎯+1 PARTIAL unchanged                                             |

**r144 makes axis-5 ACTIONABLE** — the r141 dormant schema is now flowing real data (18 events / 30-day window for US tier-1 macro releases). Future r145+ candidates : API projection of `magnitude_pct` + UI surface on `<MacroSurprisePanel>` (now data exists to display).

## Voie D held — 59 rounds streak

Zero `import anthropic` this round (CI-guarded). Pure compute service + httpx async to `api.stlouisfed.org` with existing `fred_api_key` ; no paid API ; no LLM call. Streak continues.

## NEW lesson codified r144 : R-WITNESS-EMPIRICAL

**Pre-deploy reviewers + post-deploy empirical witness on prod data are SEPARATE review passes**. 2-reviewer / 4-reviewer dispatch catches KNOWN collision/correctness classes ; ONLY empirical witness against real prod data reveals NEW collisions (e.g. r144 ADP false-positive missed by 2 reviewers, caught by dry-run on 108 prod events). Apply as :

1. Pre-deploy : 2/4-reviewer dispatch + fix-cluster
2. Deploy with feature flag OFF
3. Seed flag = true
4. Run `--dry-run --lookback-days N` on prod data
5. Inspect structured log for unexpected mappings
6. IF new collisions found → round-2 fix-cluster + re-commit + re-deploy + re-witness
7. THEN leave flag ON for live cron

Candidate r145 doctrine #17 expansion : codify R-WITNESS-EMPIRICAL as the explicit post-deploy review pass requirement for cron-fired data-correctness changes.
