# r146 — EXECUTION LOG — 2026-05-22

> **Status** : SHIPPED + DEPLOYED + WITNESSED + R-WITNESS-EMPIRICAL ROUND-2 FIX APPLIED.
> **Branch** : `claude/amazing-heyrovsky-80df1e` · **HEAD pre-r146** : `3fbc650` · **HEAD post-r146** : `7469e07` (+ closing-sync TBD)
> **Voie D streak** : 61 rounds.
> **No new migration** : pure r141 classifier defensive heuristic + r145 deploy retry.

## TL;DR

r146 closes r145 deferral (deploy + Playwright witness) AND applies R-WITNESS-EMPIRICAL round-2 fix-cluster (per r144 codified lesson) when the empirical witness revealed a NEW data-correctness bug class : unit-scale mismatch between FRED ALFRED bare numeric (`actual=115` for PAYEMS = 115K jobs) and FF abbreviated scale suffix (`forecast=65K` = 65000) → r141 classifier produced visible nonsense (`-99.8%` magnitude on the briefing).

**Mission centrale axis-5 VISIBLE SURFACE EMPIRICAL GREEN end-to-end** on public Hetzner via Playwright. 15 USD events rendered on `<RecentActualsPanel>` with full footer caveat + trader Y1 sign-convention anchor + 3 rows correctly showing `n/a` magnitude with `unit_scale_mismatch` sentinel (Building Permits / Housing Starts / NFP) and 12 rows showing legitimate magnitude_pct deviations.

Voie D held **61 rounds**.

## Phase 0 — SSH liveness probe + branch decision

SSH probe succeeded (Hetzner recovered from r145 transient outage). Branched to Phase 1A (retry r145 deploy) instead of Phase 1B fallback (local-only FF XML CI invariant).

## Phase 1A — Retry r145 deploy via R-DEPLOY-6 + curl empirical verify

Initial `redeploy-api.sh` hit SSH timeout at step 3 (tar-over-ssh long pipe — recurring lesson #24). Applied R-DEPLOY-6 manual decomposition :

1. `tar -czf /tmp/ichor-api-r145.tar.gz ichor_api` (local, 1.2MB)
2. `scp ichor-hetzner:/tmp/` (short call)
3. `ssh "tar -xzf + rsync + restart + healthz"` (short call) → `healthz=200`

Empirical curl verify : `curl /v1/calendar/recent-actuals?lookback_days=30&currency=USD&limit=3` returned 3 USD rows, first row :

```json
{
  "title": "Revised UoM Consumer Sentiment",
  "actual": "49.8",
  "forecast": "48.2",
  "magnitude_pct": 3.319502074688785,
  "state": "unavailable"
}
```

Math verify : `(49.8 - 48.2) / 48.2 * 100 = 3.32%` ✓ — classifier wired correctly + `state=unavailable` (no range provider yet) + `magnitude_pct` populated from FF point.

## Phase 1A frontend — `redeploy-web2.sh` + CF tunnel

Initial `redeploy-web2.sh` step 1+1b succeeded ; step 2 (long SSH `pnpm install + build`) timed out same SSH cluster. Decomposed manually :

1. `ssh "pnpm install --filter @ichor/web2..."` (859ms, success)
2. `ssh "pnpm --filter @ichor/web2 build"` (6.0s, success — compiled `<RecentActualsPanel>` chunk)
3. `ssh "systemctl restart ichor-web2 + healthz"` → local=200 on `/briefing` + `/briefing/EUR_USD`

CF tunnel restarted → quick-tunnel URL `https://financing-harvard-pick-nearby.trycloudflare.com`.

## Phase 1A Playwright empirical witness (initial — REVEALED BUG)

Playwright navigated to `/briefing/EUR_USD?cb=r146` + extracted the `<RecentActualsPanel>` content. **15 rows rendered correctly with full visual grammar** :

- ✅ Heading "Données publiées récentes · USD · 30 derniers jours"
- ✅ Subtitle disclosure of `unavailable` universal state (trader Y2)
- ✅ Footer caveat verbatim with sign-convention anchor (trader Y1)
- ✅ Row layout : title · date/time · actual · consensus · magnitude_pct

**BUT empirical witness ALSO revealed 3 visible-nonsense rows** :

| Event                      | actual   | consensus | rendered magnitude_pct | bug class           |
| -------------------------- | -------- | --------- | ---------------------- | ------------------- |
| Building Permits           | `1442.0` | `1.38M`   | `−99.9%`               | unit-scale mismatch |
| Housing Starts             | `1465.0` | `1.42M`   | `−99.9%`               | unit-scale mismatch |
| Non-Farm Employment Change | `115`    | `65K`     | `−99.8%`               | unit-scale mismatch |

Plus 3 UX-confusing-but-mathematically-correct rows (small-consensus amplification) : Industrial Production +126%, PPI +187%, Core PPI +379% — these are r147+ UX refinement scope, NOT correctness bugs.

**Root cause** : FRED ALFRED returns bare numeric in series-native units (PAYEMS = thousands of persons → 115 means 115K jobs). FF stores `forecast` with K/M/B suffixes parsed by `parse_economic_value()` to expanded ints (`65K` → 65000). The r141 classifier divides them as if same-scale → `(115 - 65000) / 65000 * 100 = -99.8%` which is visible nonsense.

This is **R-WITNESS-EMPIRICAL pattern firing exactly as codified r144** :

- Pre-deploy 4-reviewer dispatch ran in r145 (caught known issues but missed unit-scale class).
- Post-deploy empirical witness on real prod data caught it now.
- The lesson EXPLICITLY demands : "round-2 fix-cluster BEFORE flag stays ON for live cron". Cron is LIVE since r144.

## Phase 1B — R-WITNESS-EMPIRICAL round-2 fix-cluster

**Trader stop-loss challenge** : initial impulse was "defer to r147". HARDCORE QUESTIONED : visible nonsense to Eliot = user-trust broken instantly = unacceptable. R-WITNESS-EMPIRICAL codified rule explicitly demands SAME-ROUND fix-cluster, NOT next-round defer. The "defer" impulse was panic-defer to close the round cleanly, NOT trader discipline.

**Defensive heuristic added** to `classify_surprise()` :

```python
if abs(actual_f) > 1e-9:
    scale_ratio = max(abs(actual_f), abs(consensus_f)) / min(
        abs(actual_f), abs(consensus_f)
    )
    if scale_ratio > 100.0:
        parse_failures.add("unit_scale_mismatch")
    else:
        magnitude_pct = (actual_f - consensus_f) / abs(consensus_f) * 100.0
else:
    # Legitimate-zero actual : compute magnitude_pct honestly.
    magnitude_pct = (actual_f - consensus_f) / abs(consensus_f) * 100.0
```

**Why 100x threshold** : macro deviations beyond 100x consensus essentially never happen in tier-1 macro releases. Cleanly separates unit-scale bugs from legitimate large surprises. Verified empirically against the 15-row witness :

| Event                             | ratio  | action             |
| --------------------------------- | ------ | ------------------ |
| Building Permits 1442/1380000     | 957x   | SUPPRESS ✓         |
| Housing Starts 1465/1420000       | 969x   | SUPPRESS ✓         |
| NFP 115/65000                     | 565x   | SUPPRESS ✓         |
| Unemployment Claims 209000/210000 | 1.005x | PRESERVE ✓         |
| UoM 49.8/48.2                     | 1.03x  | PRESERVE ✓         |
| IP m/m 0.678/0.3                  | 2.26x  | PRESERVE (r147 UX) |
| PPI m/m 1.437/0.5                 | 2.87x  | PRESERVE (r147 UX) |

**Edge cases pinned by tests** : zero-actual (legitimate-zero, must NOT trip ratio test via div-by-zero — guarded by `abs(actual_f) > 1e-9` short-circuit, falls through to honest magnitude computation = -100% which is geometrically correct framing of "actual was 100% below consensus") + boundary tests at exact 100x (strict greater-than, must NOT trip) + just-above 100x (must trip).

**Architectural fix deferred r147** : r144 reconciler should normalize FRED native units to FF abbreviated convention before storage (per-series unit map : PAYEMS *1000, HOUST *1000, PERMIT \*1000, etc.). r146 ships the defensive UI-safe heuristic immediately while the data-layer fix lands.

**Tests** : 9 new regression cases in `test_economic_event_surprise.py` covering all 3 empirical-buggy classes + 4 legitimate-preserved cases + zero-actual edge + 100x boundary.

**Build gate (MEASURED — doctrine #14)** :

- pytest **157/157** (78 economic_event_surprise + 22 recent_actuals + 13 invariants_ichor + 31 r142 + 35 r144 reconciler)
- ADR-017 invariants all green
- ruff format clean (no auto-fix needed second pass)

## Phase 1B re-deploy via R-DEPLOY-6 + re-witness

3 short calls : local-tar → scp → ssh-extract+rsync+restart → healthz=200.

Re-curl verify on prod :

| Event                          | actual     | forecast  | magnitude_pct | parse_failures              |
| ------------------------------ | ---------- | --------- | ------------- | --------------------------- |
| Revised UoM Consumer Sentiment | 49.8       | 48.2      | +3.32%        | []                          |
| **Building Permits**           | **1442.0** | **1.38M** | **null**      | **[unit_scale_mismatch]** ✓ |
| **Housing Starts**             | **1465.0** | **1.42M** | **null**      | **[unit_scale_mismatch]** ✓ |
| Unemployment Claims            | 209000     | 210K      | -0.48%        | []                          |
| Industrial Production m/m      | 0.678      | 0.3%      | +126.0%       | []                          |
| ... (10 more rows)             | ...        | ...       | ...           | ...                         |
| **Non-Farm Employment Change** | **115**    | **65K**   | **null**      | **[unit_scale_mismatch]** ✓ |

**Playwright re-witness GREEN** on `/briefing/EUR_USD?cb=r146b` :

- 15 rows rendered
- **3 rows showing `n/a` magnitude** (exactly the 3 unit-scale bug class)
- 12 rows showing legitimate magnitude_pct
- All other visual grammar intact

Screenshot archived `r146b_briefing_eur_usd_recent_actuals_panel_post_round2_fix.png`.

## Mission centrale axis impact

| #     | Axe                                         | Status pre-r146                                  | Status post-r146                                                                                                              |
| ----- | ------------------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| 1     | Lecture Londres en cours                    | ✅ r123                                          | ✅ unchanged                                                                                                                  |
| 2     | Calibrage NY 13h-16h                        | ✅ r123                                          | ✅ unchanged                                                                                                                  |
| 3     | NY-window UI marker + holidays              | ✅ r132+r133                                     | ✅ unchanged                                                                                                                  |
| 4     | Anticipation par profondeur                 | 🎯+1 r130                                        | 🎯+1 unchanged                                                                                                                |
| **5** | **Réactivité temps réel events 13h-16h NY** | 🎯+1 LEVEL DATA r144 + VISIBLE SURFACE CODE r145 | **🎯+1 LEVEL DATA r144 + VISIBLE SURFACE LIVE r145/r146 + ROUND-2 UNIT-SCALE FIX r146 ⭐** (deployed + empirically witnessed) |
| 6     | Apprentissage / conviction grounding        | ✅ CLOSED r142 + visual witness r143             | ✅ unchanged                                                                                                                  |
| 7     | Apprentissage autonomie                     | 🎯 LIVE                                          | 🎯 LIVE unchanged                                                                                                             |
| 8     | Manipulation watch                          | 🎯+1 PARTIAL r131                                | 🎯+1 PARTIAL unchanged                                                                                                        |

**axis-5 now EMPIRICALLY GREEN end-to-end on public surface** — Eliot can see r144's 18 actuals + r141's classifier + magnitude_pct on `/briefing/[asset]` with honest empty (`n/a`) on the 3 unit-scale bug rows.

## Honest scope · what r146 does NOT do (doctrine #2)

- ❌ No new ADR (additive defensive heuristic + deploy retry — established patterns).
- ❌ No new migration.
- ❌ No upstream reconciler unit normalization (r147+ proper architectural fix : per-series unit map normalizing FRED native to FF convention BEFORE storage ; r146 only adds defensive UI-safe heuristic at classifier level).
- ❌ No fix for small-consensus amplification UX (IP / PPI / CPI showing +126% / +187% / etc. — mathematically correct geometric distance but UX-confusing for small absolute ratios ; r147 UX refinement scope).
- ❌ No EU/UK/JP `actual` providers.
- ❌ No FF XML title-coverage CI invariant (r147 candidate).
- ❌ No `actual_source` / `actual_revised` columns.

## r147 binding default candidates

1. ⭐ **AUTO-RECO : r144 reconciler unit normalization** — proper architectural fix for the unit-scale bug class. Per-series unit map (PAYEMS *1000 = "{n}K", HOUST *1000, PERMIT \*1000, etc.) applied at reconciler ingest BEFORE storage. Re-runs the r144 backfill cleanly + sets up future r147+ EU/UK reconcilers to follow same discipline. The r146 defensive heuristic stays as belt-and-suspenders. Effort M.
2. **Small-consensus amplification UX refinement** — IP / PPI / CPI showing +126% / +187% / etc. are mathematically correct but UX-confusing. Options : (a) when `|consensus_value| < 1`, render `+0.4 ppts` ("percentage points") instead of `+126%` ; (b) add a secondary token "(0.4 ppts vs consensus)" alongside the % ; (c) suppress magnitude_pct for small-ratio consensus. Effort S-M, requires copy + classifier convention work.
3. **FF XML title-coverage CI invariant** (r144 trader Y2(a) UPGRADED). Effort S-M.
4. **ADR-017 web2 caveat RTL regex** (deferred r143+r144+r145+r146). Effort S-M.
5. **`actual_source` column** (Critic-attribution multi-provider). Effort S.
6. **`actual_revised` T+24h overwrite column**. Effort S-M.
7. **Range envelope consensus-poll provider** — HIGH LEVERAGE (auto-lights state badges + amber emphasis on existing r145 surface). Effort M.
8. **EU `actual` reconciler via ECB SDMX** (mirror r144 + R-WITNESS-EMPIRICAL discipline + new unit-normalization pattern from r147 #1). Effort M.

## Doctrine + lesson alignment

- ✅ **Doctrine #1 R59-first** — Phase 0 SSH liveness probe BEFORE deploy retry, prevented blind re-attempt.
- ✅ **Doctrine #2 strict scope** — 1 round = r145 deferral closure + R-WITNESS-EMPIRICAL round-2 fix (NOT a new feature).
- ✅ **Doctrine #6 commit single-step, NOT amend** — `7469e07` round-2 fix is separate commit from r145 feat.
- ✅ **Doctrine #9 dated §Impl APPEND, NO new ADR** (additive defensive heuristic + deploy retry).
- ✅ **Doctrine #11 calibrated honesty** — `n/a` rendered HONESTLY on unit-scale-mismatch rows + `unit_scale_mismatch` sentinel surfaced in `parse_failures` for downstream observability.
- ✅ **Doctrine #14 build gate on COMMITTED shape** — 157/157 pytest BEFORE push + deploy.
- ✅ **Lesson #1 MEASURED not forecast** — empirical Playwright witness BOTH pre-fix (revealed bug) AND post-fix (verified suppression).
- ✅ **Lesson #22 worktree-mismatch absolute paths** — applied throughout.
- ✅ **Lesson #24 SSH-instability** — R-DEPLOY-6 manual decomposition applied successfully BOTH for backend (step 3 timeout) AND frontend (step 2 timeout).
- ✅ **Lesson #37 DEMOTE framing** — `n/a` is honest absence when classifier can't trust the comparison ; NOT fabricated comparison.
- ✅ **R-DEPLOY-6** — applied 2× successfully this round.
- ✅ **R-WITNESS-EMPIRICAL r144 NEW** — the codified 7-step rule executed exactly as designed : (1) pre-deploy review ✓ r145 / (2) deploy flag OFF N/A (feature flag not used for the panel since it's additive UI) / (3) seed = N/A / (4) dry-run on prod ✓ Playwright witness / (5) inspect output for unexpected mappings ✓ (3 unit-scale rows) / (6) round-2 fix-cluster ✓ defensive heuristic + tests + re-deploy + re-witness / (7) flag ON / live cron unchanged.

## Voie D held — 61 rounds streak

Zero `import anthropic` r146. Pure compute defensive heuristic + deploy retry ; no LLM call. Streak continues.

## Empirical witness archive

- `.playwright-mcp/page-2026-05-22T20-16-05-769Z.yml` — initial r146a witness (revealed unit-scale bug)
- `r146_briefing_eur_usd_recent_actuals_panel.png` — initial screenshot (with `−99.9%` visible nonsense)
- `.playwright-mcp/page-2026-05-22T20-22-56-407Z.yml` — post-fix r146b witness
- `r146b_briefing_eur_usd_recent_actuals_panel_post_round2_fix.png` — post-fix screenshot (with `n/a` on bug rows)
- CF tunnel URL : `https://financing-harvard-pick-nearby.trycloudflare.com/briefing/EUR_USD`
