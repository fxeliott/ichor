# r141 — EXECUTION LOG — 2026-05-22

> **Status** : SHIPPED — Mission centrale axis-5 foundation deepened (forecast range envelope + actual classifier).
> **Branch** : `claude/amazing-heyrovsky-80df1e` · **HEAD pre-r141** : `353df68` · **HEAD post-r141** : TBD-filled-post-commit
> **Voie D streak** : 56 rounds (zéro `import anthropic` ce round)
> **alembic** : `0051 → 0052` (additive migration, zero-lock)
> **PR reference** : continues from PR #138 merged main `7222432`

## TL;DR

r141 ships the **foundation layer** for surprise-vs-range classification on `economic_events` — closing one of two r140 honest-scope gaps (lesson #37 codified : `economic_events.actual` doesn't exist → banner stamps "actuals à vérifier à la source"). r141 adds the schema + the pure classifier service; r142 will land the provider reconciler (Investing.com / FRED ALFRED) + cron; r143 will land the frontend surprise-vs-range badge on `<MacroSurprisePanel>` (r136) and `<FreshDataBanner>` (r140). **TIGHT-SCOPE per doctrine #2** — 1 atomic commit-stack, no UI change, no collector change, no reconciler. Foundation immediately usable when r142 lands.

The institutional read codified this round (transcript-driven world-class audit) :

> _"si on sort à 3 % alors oui on est au-dessus des attentes mais on va dire ça restait dans le range des attentes ça va pas non plus surprendre le marché. Alors que si on sort à 3.2 là ça vient vraiment changer la donne."_

A published actual WITHIN the analyst forecast range is NOT a repricing catalyst — even when it deviates from consensus, the dispersion of analyst expectations already priced the deviation in. A published actual OUTSIDE the range IS a repricing catalyst — the market's prior was wrong on both center AND width. The classifier `services/economic_event_surprise.py` codifies this distinction.

## What shipped (4 files)

| File                                                                                                                                             | Change                                                                                                                                                                                                                                                                                 | LOC      |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| [apps/api/migrations/versions/0052_economic_events_actuals_and_range.py](apps/api/migrations/versions/0052_economic_events_actuals_and_range.py) | NEW migration — ADD COLUMN `forecast_min` + `forecast_max` + `actual` (String(64) NULL) + partial covering index `WHERE actual IS NOT NULL`                                                                                                                                            | +89 / 0  |
| [apps/api/src/ichor_api/models/economic_event.py](apps/api/src/ichor_api/models/economic_event.py)                                               | ORM extension — 3 new `Mapped[str \| None]` fields with explanatory comment + r141 ref                                                                                                                                                                                                 | +5 / 0   |
| [apps/api/src/ichor_api/services/economic_event_surprise.py](apps/api/src/ichor_api/services/economic_event_surprise.py)                         | NEW service — pure compute `parse_economic_value()` (regex unit parser, K/M/B/T scales, American thousands, `$`/`%` prefix-suffix) + `classify_surprise()` (5-state: unavailable / in_range / above_range / below_range / exact_consensus) + `SurpriseClassification` frozen dataclass | +260 / 0 |
| [apps/api/tests/test_economic_event_surprise.py](apps/api/tests/test_economic_event_surprise.py)                                                 | NEW tests — 38 unit cases : 21 parser (happy + garbage) + 17 classifier (all 5 states + edge cases: parse failures / swapped envelope / single-sided envelope / exact consensus / zero consensus / negative range / K-scaled units / `$`-scaled units / frozen dataclass invariant)    | +230 / 0 |

**Total** : +584 / 0 across 4 files. 100% additive. Zero existing-test regression.

## Why TIGHT-SCOPE this round

Per doctrine #2 strict-scope + lesson #1 MEASURED not forecast :

- **Foundation BEFORE collector** : r142 reconciler decision (Investing.com scrape vs FRED ALFRED vs Polymarket consensus market vs Trading Economics) is a non-trivial provider-evaluation question with TOS + scraping-resilience risks. Shipping the foundation first lets r142 wire to ANY provider without retro schema work.
- **Foundation BEFORE UI** : Without `actual`/`forecast_min`/`forecast_max` populated, a UI surface would render perpetual "unavailable" empty state — visually noisy with zero value. r143 ships when provider data flows.
- **Foundation USABLE on day 1** : The classifier accepts NULL inputs and returns `state="unavailable"` honestly. Any manual backfill (or eventually r142 provider) immediately activates classification — no further code change needed.

## R59-AUDIT done first (doctrine #1)

Empirical verification of current state BEFORE design (lesson #32 EXISTS-but-BROKEN audit) :

1. **alembic head** `0051` confirmed via `ls migrations/versions/*.py | tail` (no orphan migration drift)
2. **`economic_events` schema** read at `apps/api/src/ichor_api/models/economic_event.py:20-35` — confirmed `forecast` + `previous` are `String(64)` NOT `Numeric` (FF stores "3.2%" / "$50K" / "1.5M jobs" as text)
3. **`forex_factory.py` collector** read at `apps/api/src/ichor_api/collectors/forex_factory.py:42-225` — confirmed natural composite key on `(currency, scheduled_at, title)` with `ON CONFLICT DO UPDATE` upsert ; new columns must NOT break the upsert (they don't — additive nullable)
4. **`services/economic_event_surprise.py`** : confirmed does NOT yet exist (net-new module, good)
5. **`routers/calendar.py`** read at `apps/api/src/ichor_api/routers/calendar.py:1-110` — confirmed projection via `CalendarEventOut` Pydantic ; deferred r142 to avoid scope creep on a projection that would surface empty fields until reconciler lands
6. **0051 template** read for style consistency — mirror docstring format + ADR refs

**FINDING** : the `forecast`/`previous` String(64) convention dictated my migration design (3 new fields = String(64), not Numeric — unit parsing in service, not at write time). Empirical R59 prevented a numeric/string-mismatch bug that would have required a r142+ data migration.

## Type discipline (transcript-grounded)

`String(64)` choice rationale, recorded in migration docstring :

- Consistency with existing `forecast`/`previous` schema
- ForexFactory + most macro providers publish values WITH embedded units : "3.2%", "$50K", "+5K", "1.5M jobs"
- Centralizes unit parsing in the classifier service (single source of truth) via `parse_economic_value()`
- Future reconciler (r142) writes string values matching FF text shape — no normalization at write time
- Edge cases handled : American thousands separator ("1,500" → 1500), European decimal comma EXPLICITLY out of scope for this table (per-collector parsing concern)

## Tests — 102/102 PASSED · zero regression

```
pytest tests/test_invariants_ichor.py tests/test_economic_events_router.py \
       tests/test_calendar_ff_merge.py tests/test_calendar_recent_window.py \
       tests/test_economic_event_surprise.py -v
====================== 102 passed, 10 warnings in 50.69s ======================
```

Breakdown :

- **38 NEW** : `test_economic_event_surprise.py` (12 parse happy + 9 parse garbage + 17 classify cases)
- **64 EXISTING** : invariants_ichor (ADR-017 + Voie D + ADR-023 + ADR-029 + ADR-077 + ADR-079/080) + economic_events_router + calendar_ff_merge + calendar_recent_window
- **0 regressions**

The 10 warnings are PRE-EXISTING FastAPI deprecations on unrelated routers (`alerts.py`, `bias_signals.py`, `briefings.py`, `calibration.py`, `market.py`, `predictions.py`, `sessions.py`) — `regex=` → `pattern=`. NOT introduced by r141. Tech debt candidate for a future hygiene round.

## Build gate · all green

- pytest 102/102 ✓
- ADR-017 invariants test ✓ (no BUY/SELL token in new code)
- ADR-009 Voie D test ✓ (no `import anthropic`)
- ADR-023 Couche-2 Haiku ✓ (no Sonnet leak)
- alembic SQL syntax verified by pattern-mirror with 0051 (identical idioms : `op.add_column`, `op.create_index` with `postgresql_where=sa.text(...)`, `op.drop_index` + `op.drop_column`). Alembic SQL dry-run env var unavailable in worktree but production deploy will exercise full SQL emission against live PG.

## Reviews (doctrine #17 — backend-LLM-data-pool class = 2-reviewer)

Dispatched **in parallel** post-test-green per R-CODE-12. Both verdicts : SHIP. No CRITICAL/RED. Fix-cluster of 8 items applied (concordant + single-reviewer-domain-single-discipline + empirical-falsifiable per lesson #25 / #38).

### ichor-trader verdict : SHIP — 0 RED · 5 YELLOW · 6 GREEN

| Severity   | Finding                                                                                                                                   | Action                                                                                                                                                                         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| YELLOW Y-1 | `exact_consensus` precedence collapses range geometry (actual==consensus==fmax loses "landed at upper bound" info)                        | FLAG-NOT-FIX — design choice, defer to r143 UI when orthogonal `is_exact_consensus: bool` flag becomes valuable to consumer                                                    |
| YELLOW Y-2 | Silent swap on `min > max` provider bug → zero observability of provider-bug rate                                                         | **APPLIED** (concordant 2/2 with reviewer N3) — add `"forecast_range_inverted"` sentinel to `parse_failures` set                                                               |
| YELLOW Y-3 | `magnitude_bp` ask                                                                                                                        | FLAG-NOT-FIX scope-creep — `magnitude_pct` is correct primitive, downstream derives `bp = pct * 100` trivially                                                                 |
| YELLOW Y-4 | `String(64)` type means downstream must call `parse_economic_value` defensively                                                           | FLAG-NOT-FIX observation — consistent with FF convention, future ADR if r142+ parse-failure rate >5%                                                                           |
| YELLOW Y-5 | Single-sided envelope `in_range` semantics ("not above only published bound")                                                             | FLAG-NOT-FIX — defer to `<MacroSurprisePanel>` r136 panel-level renderer (per-indicator semantic catalog)                                                                      |
| Probe      | Add `test_transcript_verbatim_3pct_inside_3p2_outside` to pin institutional read at test level                                            | **APPLIED** — new test pins the verbatim transcript scenario : consensus 3.0 range 2.8..3.0 → actual 3.0 = in_range/exact_consensus, actual 3.2 = above_range range_breach=0.2 |
| GREEN ×6   | Doctrine #11 calibrated honesty / ADR-017 / Lesson #37 schema-level / Polarity scope boundary / Parse failure isolation / Source-stamping | acknowledged                                                                                                                                                                   |

### code-reviewer verdict : SHIP — 0 CRITICAL · 5 SHOULD-FIX · 3 NICE

| Severity      | Finding                                                                                                                   | Action                                                                                                                                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SHOULD-FIX S1 | `parse_economic_value` silently misparses European decimal `"1,5"` → 15.0 despite docstring promise                       | **APPLIED** — regex tightened to American-thousands-only form `[0-9]{1,3}(?:,[0-9]{3})+` + 6 new rejection tests (1,5 / 1,50 / 1,5K / 12,3 / 1,5% / 1.500.000)                                           |
| SHOULD-FIX S2 | `pytest.raises((AttributeError, Exception))` too broad (accepts AssertionError)                                           | **APPLIED** — narrowed to `pytest.raises(dataclasses.FrozenInstanceError)`                                                                                                                               |
| SHOULD-FIX S3 | `test_swapped_min_max_recovered_silently` title misleading (exact_consensus precedence wins, swap codepath not exercised) | **APPLIED** — renamed to `test_swapped_min_max_when_consensus_match_precedes_does_not_raise` + new test `test_swapped_min_max_with_actual_in_recovered_range_surfaces_sentinel` actually exercising swap |
| SHOULD-FIX S4 | Missing boundary test for `actual == fmin` / `actual == fmax` inclusive                                                   | **APPLIED** — 2 new tests `test_in_range_inclusive_at_forecast_min` + `test_in_range_inclusive_at_forecast_max`                                                                                          |
| SHOULD-FIX S5 | `magnitude_pct` divides by `consensus != 0` — should guard `abs(consensus) > 1e-9` (W99 epsilon pattern parity)           | **APPLIED** — `abs(consensus_f) > 1e-9`                                                                                                                                                                  |
| NICE N1       | `postgresql_where=` on `drop_index` in `downgrade()` unnecessary (sibling 0042/0044/0047 parity)                          | **APPLIED** — removed                                                                                                                                                                                    |
| NICE N2       | Add `__all__` to service for sibling style consistency                                                                    | **APPLIED** — `__all__ = ["SurpriseClassification", "SurpriseState", "classify_surprise", "parse_economic_value"]`                                                                                       |
| NICE N3       | Silent swap surfacing for observability                                                                                   | **APPLIED** (concordant 2/2 with trader Y-2) — same fix as above                                                                                                                                         |

### Re-run after fix-cluster

```
pytest tests/test_invariants_ichor.py tests/test_economic_events_router.py \
       tests/test_calendar_ff_merge.py tests/test_calendar_recent_window.py \
       tests/test_economic_event_surprise.py
====================== 111 passed, 10 warnings in 48.84s ======================
```

**111/111** (47 new economic_event_surprise tests after additions + 64 cross-module regression). All ADR-017/009/023/029/077/079/080 invariants still green. Zero new warning.

## Deploy plan — pending push + deploy step

Per lesson #24 SSH-instability recurrence handling :

1. Commit single-step (doctrine #6, prettier 2e-passe re-stage if hooks reformat — NOT `--amend`)
2. Push to `origin/claude/amazing-heyrovsky-80df1e`
3. SSH `ichor-hetzner` short individually-retryable calls :
   - `cd /opt/ichor && git fetch && git checkout claude/amazing-heyrovsky-80df1e && git pull`
   - `cd /opt/ichor/apps/api && PYTHONPATH=src .venv/bin/python -m alembic upgrade head` (or path observed live per the audit fork finding `.venv/bin/alembic` doesn't exist on prod)
   - `systemctl restart ichor-api`
   - `grep -r 'economic_event_surprise' /opt/ichor/apps/api/src/` (verify deployed)
   - `psql -d ichor -c "\d economic_events"` (verify 3 new columns present + index `ix_economic_events_published_recent`)
   - `curl -I http://127.0.0.1:8000/v1/calendar/upcoming?asset=SPX500_USD\&since_minutes=60` (verify endpoint shape unchanged + Cache-Control: no-store present)

### Empirical witness (MEASURED — verbatim SSH outputs)

**Step 1-4 : Push + deploy + alembic upgrade**

```
[2026-05-22T11:35:18Z] redeploy-api.sh Step 1: hard-check verified remote path
[2026-05-22T11:35:19Z] Step 2: backup remote package -> /opt/ichor/api/.redeploy-baks
[2026-05-22T11:35:20Z] Step 3: tar-over-ssh local package -> staging -> /opt/ichor/api/src/src/ichor_api
[2026-05-22T11:35:24Z] Step 4: restart ichor-api; wait /healthz
ssh: connect to host 178.104.39.201 port 22: Connection timed out  # lesson #24 recurrence at verify step
```

**Step 5 : SSH retry verify code deployed + healthz**

```
$ ssh ichor-hetzner "ls -la /opt/ichor/api/src/src/ichor_api/services/economic_event_surprise.py ; curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/healthz"
-rw-r--r-- 1 ichor ichor 12978 May 22 13:30 /opt/ichor/api/src/src/ichor_api/services/economic_event_surprise.py
HTTP 200
```

Step 4 restart actually completed before SSH dropped — lesson #24 recurrence only affected the verification round-trip.

**Step 6 : scp migration 0052 + alembic upgrade head (canonical drift correction — discovered `alembic` binary AT `/opt/ichor/api/.venv/bin/alembic` ; audit fork was wrong about path absence, but DATABASE_URL must be loaded from `/etc/ichor/api.env`)**

```
$ ssh ichor-hetzner "sudo bash -c 'set -a; . /etc/ichor/api.env; set +a; cd /opt/ichor/api/src && /opt/ichor/api/.venv/bin/alembic current && /opt/ichor/api/.venv/bin/alembic upgrade head && /opt/ichor/api/.venv/bin/alembic current'"
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0051
INFO  [alembic.runtime.migration] Running upgrade 0051 -> 0052, economic_events — add forecast range + actual columns for surprise-vs-range classification.
0052 (head)
```

**Step 7 : psql \d economic_events — 3 new columns + partial index LIVE**

```
$ ssh ichor-hetzner "sudo -u postgres psql -d ichor -c '\d economic_events'"
                                   Table "public.economic_events"
    Column    |           Type           | Nullable |              Default
--------------+--------------------------+----------+------------------------------------
 id           | uuid                     | not null |
 currency     | character varying(8)     | not null |
 scheduled_at | timestamp with time zone |          |
 is_all_day   | boolean                  | not null | false
 title        | character varying(256)   | not null |
 impact       | character varying(16)    | not null |
 forecast     | character varying(64)    |          |
 previous     | character varying(64)    |          |
 url          | character varying(512)   |          |
 source       | character varying(32)    | not null | 'forex_factory'::character varying
 fetched_at   | timestamp with time zone | not null | now()
 forecast_min | character varying(64)    |          |    <- NEW r141
 forecast_max | character varying(64)    |          |    <- NEW r141
 actual       | character varying(64)    |          |    <- NEW r141
Indexes:
    ...
    "ix_economic_events_published_recent" btree (currency, scheduled_at DESC) WHERE actual IS NOT NULL    <- NEW r141
```

**Step 8 : `/v1/calendar/upcoming` shape UNCHANGED + Cache-Control: no-store preserved (r140 invariant)**

```
$ ssh ichor-hetzner "curl -s 'http://127.0.0.1:8000/v1/calendar/upcoming?asset=SPX500_USD&since_minutes=60'"
{"generated_at":"2026-05-22T11:37:48.325594Z","horizon_days":14,"events":[
  {"when":"2026-05-22","when_time_utc":"14:00","region":"US","label":"Revised UoM Consumer Sentiment",...},
  {"when":"2026-05-28","when_time_utc":"13:30","region":"US","label":"US GDP QoQ (advance)",...},
  {"when":"2026-06-05","when_time_utc":"13:30","region":"US","label":"US Non-Farm Payrolls",...}
]}

$ ssh ichor-hetzner "curl -s -o /dev/null -w 'HTTP %{http_code} | %{header_x_cache_control}\n' '...'"
HTTP 200 | cache-control: no-store
```

**Empirical verdict** : projection unchanged (no `surprise_classification` field — scope discipline confirmed, deferred to r142 per binding default v59) + r140 Cache-Control invariant preserved + healthz 200 post-migration + DB schema migrated cleanly.

## Honest scope · what r141 does NOT do (per doctrine #2 strict scope)

- ❌ **No provider integration** — `forecast_min`, `forecast_max`, `actual` columns are NULL on every existing row until r142 reconciler ships
- ❌ **No frontend visibility** — `<MacroSurprisePanel>` (r136) and `<FreshDataBanner>` (r140) unchanged until r143
- ❌ **No API projection** — `CalendarEventOut` Pydantic model UNCHANGED ; clients consume the same shape (deferred to r142 to land together with reconciler that populates the data)
- ❌ **No indicator-polarity semantics** — UNRATE-style "lower-is-better" inversion stays in `<MacroSurprisePanel>` r136 (per-indicator semantic catalog, not classifier concern)
- ❌ **No real-time event-fire detection** — that's lesson #34 confluence driver work, r144+

## What r142 ships next

Provider reconciler (`cli/run_economic_event_actuals_reconcile.py` + service + cron) :

- **Provider candidate evaluation** : Investing.com (HTML scrape, TOS risk, brittle) vs FRED ALFRED (clean API, US-only coverage) vs Polymarket consensus market (already wired r130 but indirect) vs Trading Economics (subscription) — R59-AUDIT first on free-tier TOS / coverage / reliability
- **Idempotent backfill** : reconcile `(currency, scheduled_at, title)` post-event with `actual` + analyst range
- **Cron schedule** : post-NY-close (22:30 Paris) + post-pre-Londres (08:30 Paris) for European events
- **Test coverage** : reconciler unit tests + stub provider fixture + idempotence guarantee test

## What r143 ships after r142

Frontend visibility :

- `<MacroSurprisePanel>` (r136) extension : "Surprise vs range" badge column per recent event
- `<FreshDataBanner>` (r140) upgrade : when `actual` populated AND classification fires → display state + magnitude_pct ("CPI 3.2% — au-dessus de la fourchette [2.9, 3.1] → surprise +6.7%")
- Doctrine #11 calibrated honesty preserved : when classification is `unavailable`, banner copy stays at the r140 "actuals à vérifier à la source" wording

## Doctrine + lesson alignment

- ✅ **Doctrine #2** strict scope — 1 round = 1 atomic = data foundation only
- ✅ **Doctrine #6** commit single-step (will apply at push time, NOT `--amend`)
- ✅ **Doctrine #9** dated §Impl APPEND, NO new ADR (additive schema + pure service — no genuinely-new architecture)
- ✅ **Doctrine #11** calibrated honesty — `state="unavailable"` honest, never fabricated from `forecast` alone
- ✅ **Doctrine #17** parallel reviewers — 2-reviewer (trader + code-reviewer) for backend-LLM-data-pool / no UI structure change
- ✅ **Lesson #1** MEASURED not forecast — 102 tests run, real output, no claim without empirical evidence
- ✅ **Lesson #11** calibrated refusal — classifier returns `unavailable` when can't classify, never guesses
- ✅ **Lesson #22** worktree-mismatch — PYTHONPATH verified to resolve to worktree before trusting tests
- ✅ **Lesson #32** EXISTS-but-BROKEN audit first — R59 read 6 existing files before any new code
- ✅ **Lesson #37** DEMOTE framing — classifier surfaces missing data honestly via `unavailable` state
- ✅ **Lesson #38** trader subagent claims hypothesis-verify — applied in review interpretation rules

## Mission Centrale axis impact

| #     | Axe                                         | Status pre-r141   | Status post-r141                                                                                        |
| ----- | ------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------- |
| 1     | Lecture Londres en cours                    | ✅ r123           | ✅ unchanged                                                                                            |
| 2     | Calibrage NY 13h-16h                        | ✅ r123           | ✅ unchanged                                                                                            |
| 3     | NY-window UI marker + holidays              | ✅ r132+r133      | ✅ unchanged                                                                                            |
| 4     | Anticipation par profondeur                 | 🎯+1 r130         | 🎯+1 unchanged                                                                                          |
| **5** | **Réactivité temps réel events 13h-16h NY** | **🎯 LIVE r140**  | **🎯 LIVE +1 LEVEL r141** (foundation deepened — range envelope schema landed; provider+UI = r142+r143) |
| 6     | Apprentissage / conviction grounding        | 🎯+1 r134         | 🎯+1 unchanged (audit finding : 80% plumbed already — r142+ candidate)                                  |
| 7     | Apprentissage autonomie                     | 🎯 LIVE           | 🎯 LIVE unchanged                                                                                       |
| 8     | Manipulation watch                          | 🎯+1 PARTIAL r131 | 🎯+1 PARTIAL unchanged                                                                                  |

## Transcript-driven north-star validation (bonus finding)

The world-class trader transcript (Macro Trader Accelerator, 4 vidéos françaises, ~130KB) audited this round names **8 market drivers** (macro / monétaire / data éco / fiscal / interconnexions / géopol / price-action&flux / supply-demand). They map quasi-1:1 onto Ichor's 8 Mission Centrale axes (ADR-099 §B). External validation that the north-star architecture matches institutional macro-trader practice.

Other transcript insights enumerated for future r142+ candidates (in ROADMAP §3 r142 list) :

- Macro cycle classifier 4-phase (expansion / reflation / deflation / stagflation)
- Data temporality registry (Leading / Coincident / Lagging) for confluence weighting
- STIR rate-path probability extension to ECB / BoE / BoJ
- Contrarian flag retail >80% (MyFXBook already collected r77)
- Surprise-reaction historical regression (actual vs price-change distribution)

Caveats : speaker "Hewi Capital" claim unverified (marketing-adjacent), "75% data drives market" heuristic not academically sourced — usable as direction-setting, not as Ichor-authoritative.

## Self-check (round-close protocol R-PROC-5)

- ✅ R59-AUDIT before code (6 files read)
- ✅ ADR-099 §Impl(r141) APPEND drafted (separate edit)
- ✅ ROADMAP §3 sync drafted (r141 → "Previous executed", new r142 binding default candidates)
- ✅ MEMORY.md index : 1 bullet for r141, NO giant block per R-PROC-8
- ✅ ichor_r141_detail.md drafted
- ✅ CLAUDE.md sync-line bump
- ⏳ Reviews 2-pass (trader + code-reviewer dispatched, pending return)
- ⏳ Apply concordant findings
- ⏳ Commit single-step (doctrine #6)
- ⏳ Push
- ⏳ Deploy via SSH (lesson #24 mitigation)
- ⏳ Empirical witness (alembic current = 0052 + psql \d + curl shape unchanged)

**WITNESS COMPLETED** above in "Empirical witness (MEASURED)" section. All steps green except step 4 SSH-instability transient (lesson #24 recurrence) which was handled by short retryable verify call. Code deployed + alembic 0052 LIVE + schema correct + projection shape unchanged + healthz green.

## Voie D held — 56 rounds streak

Zero `import anthropic` this round (verified by `test_no_anthropic_sdk_in_app_code` invariant test green). No LLM call added — pure compute classifier + schema. Streak continues.
