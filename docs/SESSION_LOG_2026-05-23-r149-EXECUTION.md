# r149 — EXECUTION LOG — 2026-05-23

> Tier 4 axis-4 +1 LEVEL extension — Engine 8 AUD/CAD/JPY title-fragment
> coverage + defensive negative-list + event-class consistency CI invariant.
> NO PIVOT — paste-prompt v67 #1 ⭐ AUTO-RECO stayed binding default after
> dual-audit returned clean actionable scope + empirical prod DB ground truth
> confirmed value (8 AUD high+med + 11 CAD high+med events / 30d in prod).

## TL;DR

r149 extends Engine 8 from 18 to 37 title patterns covering USD/EUR/GBP/AUD/
CAD/JPY central bank decisions + Tankan + per-country CPI variants. Closes
r148 binding default candidates #1 ⭐ (AUTO-RECO) + #4 (delete tautological
test) + #7-in-CODE (r148 emission-vs-registry pattern extended to Engine 8
via `TestR149EventClassConsistencyInvariant`).

Voie D held **64 rounds**. Mission centrale axis-4 +1 LEVEL r147+r149.

The new event-class consistency invariant is the highest-leverage piece :
it MECHANIZES the r148 pattern (emission ⊆ registry) for a SECOND
architectural surface, transforming the doctrinal observation into a generic
SSOT-protection technique applicable to any future registry-driven mapping
pattern in Ichor.

## Phase 0 — R59 dual-audit (2 parallel sub-agents)

- **researcher web** verbatim FF XML extraction `https://nfs.faireconomy.media/ff_calendar_thisweek.xml` 2026-05-22 — 29 AUD/CAD/JPY rows extracted ; canonical title strings verified ; **RBNZ "Official Cash Rate" (NZD) substring-collision with RBA "Cash Rate" (AUD) identified** ; baselines per Vojtko-Dujava SSRN 5384407 + Quantpedia 2024 : RBA/BoC ~25bp, Tankan ~15bp ; documented **Vojtko-Dujava NEGATIVE pre-drift for RBA/BoC** (sign-flip vs FOMC).

- **ichor-navigator** mapped event_proximity_engine current state (18 r147 patterns) + Ichor 6-asset universe + USD_JPY/AUD_USD tracked-no-card via `config.py:151-161` + collector non-filtering behavior (AUD/CAD/JPY events ARE in DB pre-r149, just unmapped) + recommended r149 test pattern + SQL probe template.

**Empirical ground truth** (prod DB SSH probe via `ssh ichor-hetzner "sudo -u ichor psql ichor"`) :

- AUD : 8 high+med events / 30d (Cash Rate, RBA Rate Statement, RBA Press Conference, RBA Monetary Policy Statement, Statement on Monetary Policy, Employment Change, Unemployment Rate, Wage Price Index q/q).
- CAD : 11 high+med events / 30d (Overnight Rate, BOC Rate Statement, CPI m/m, Median/Trimmed/Common CPI, Employment Change, Unemployment Rate, BOC Gov Macklem Speaks, Ivey PMI, Retail Sales m/m).
- **JPY : 0 high + 0 medium events in 90 days**. FF marks JPY events as `low` empirically. r149 JPY mapping is FUTURE-PROOFING under current `_impact_multiplier()=0.0 for low` filter.

## Phase 1 — Implementation (3 files, +418 / -51 LOC)

Commit `3815f3d` "feat(api): r149 Engine 8 AUD/CAD/JPY title-fragment extension + defensive negative-list + event-class consistency CI invariant" :

1. **`apps/api/src/ichor_api/services/event_proximity_engine.py`** :
   - `EVENT_CLASS_BASELINE_BP` extended with `"RBA": 25.0, "BoC": 25.0, "Tankan": 15.0` + Vojtko-Dujava + Quantpedia 2024 inline citations + r150+ note on RBA/BoC NEGATIVE-drift sign-flip not yet implemented.
   - `_TITLE_TO_EVENT_CLASS` extended with 19 new entries : 5 RBA (rba monetary policy statement, rba press conference, rba rate statement, statement on monetary policy, cash rate) + 4 BoC (boc monetary policy report, boc press conference, boc rate statement, overnight rate) + 2 BoJ-broadening (boj press conference, boj summary of opinions) + 1 Tankan + 6 CPI variants (trimmed mean cpi, trimmed cpi, median cpi, common cpi, tokyo core cpi, national core cpi) + 1 generic `monetary policy statement` fallback for JPY bare-title BoJ decisions.
   - NEW `_TITLE_FRAGMENT_BLOCKED: frozenset[str] = frozenset({"official cash rate"})` defensive negative-list checked BEFORE positive matching (RBNZ collision guard).
   - `_map_title_to_event_class()` docstring updated to descriptive form (avoid drift on count) covering USD/EUR/GBP/AUD/CAD/JPY.
   - `assess_event_proximity()` honest-scope docstring blocks updated : TITLE MAPPING COVERAGE r149 + JPY IMPACT FILTER GAP + RBA/BoC PRE-DRIFT DIRECTION.
   - Runtime `caveat` string adds RBA/BoC direction-not-implemented disclosure when `event_class in ("RBA","BoC")` (trader YELLOW-1 + code-reviewer SHOULD-FIX #2 concordant fix).

2. **`apps/api/tests/test_event_proximity_engine.py`** (+302 LOC, 39 new tests across 6 classes) :
   - `TestR149AudCadJpyTitleMapping` : 20 mapping tests.
   - `TestR149RegressionExistingMappingsUnchanged` : 8 tests verifying r147 USD/EUR/GBP/BoJ mappings preserved by pattern reordering.
   - `TestR149NewBaselineKeys` : 4 baseline pin tests (RBA=25, BoC=25, Tankan=15 + r147 baselines unchanged).
   - `TestR149BlockedListCollisionGuard` : 3 RBNZ blocker tests.
   - `TestR149RbaBocDirectionCaveatSurfaced` : 3 tests (RBA caveat contains direction disclosure, BoC mirror, FOMC regression test confirms RBA/BoC caveat does NOT leak to FOMC).
   - `TestR149EventClassConsistencyInvariant` : 1 NEW invariant — r148 emission-vs-registry pattern extended to Engine 8 (every mapped class has baseline entry, subset-not-equality because registry has fall-through baselines without title patterns).

3. **`apps/api/tests/test_brier_optimizer_cli.py`** (-32 LOC) : DELETED `test_factor_names_match_confluence_engine` (r148 docstring flagged as tautology). Safety property preserved by transitive closure : r142 + r148 invariants ⇒ `emitted == _FACTOR_NAMES` strictly stronger than the deleted hand-maintained parallel test.

## Phase 2 — 2-reviewer concordance (doctrine #17 backend-LLM-data-pool class)

| Reviewer      | Verdict        | Findings                                 |
| ------------- | -------------- | ---------------------------------------- |
| ichor-trader  | SHIP-WITH-FIX  | 0 RED + 5 YELLOW + GREEN ADR-017 chain   |
| code-reviewer | READY WITH FIX | 0 CRITICAL + 2 SHOULD-FIX + 6 NICE/GREEN |

**Concordance** : both reviewers flagged the SAME root cause from different angles :

- **trader YELLOW-1** = **code-reviewer SHOULD-FIX #2** : RBA/BoC NEGATIVE pre-drift (Vojtko-Dujava SSRN 5384407) NOT encoded — runtime `direction="up"` for an event class whose literature-cited expectation is `down`. Doctrine #11 calibrated-honesty signal weakened. **APPLIED** : added runtime `caveat` string conditional on `event_class in ("RBA","BoC")` surfacing the direction-not-implemented honestly + added 3 caveat-surfacing tests (`TestR149RbaBocDirectionCaveatSurfaced`) verifying the fix.

- **code-reviewer SHOULD-FIX #1** : docstring count drift ("~30 high-impact event titles (r149 = r147 18 + 12 new)" — actual count was wrong). **APPLIED pre-emptively** before code-reviewer returned : changed to descriptive form ("all high-impact event titles for USD/EUR/GBP/AUD/CAD/JPY central banks + tier-1 macro") to avoid count drift.

- **trader YELLOW-3** : stale honest-scope docstring ("AUD/CAD-specific events fall through" pre-r149) + missing JPY low-impact filter note. **APPLIED** : three new honest-scope blocks (TITLE MAPPING COVERAGE r149 + JPY IMPACT FILTER GAP + RBA/BoC PRE-DRIFT DIRECTION).

- **trader YELLOW-2** : RBNZ regression test pin already covered by `TestR149BlockedListCollisionGuard`.

- **trader YELLOW-4** (shared CPI baseline 20bp for 6 currency-variants) + **YELLOW-5** (Employment Change fall-through to `high_other` 10bp) : acknowledged as conservative cold-start priors per lesson #37 ; r150+ candidates for per-currency calibration.

- **code-reviewer NICE-TO-HAVE #6** : pre-existing r147 `TestBrierLockstepWithR147(TestAdr017Invariants)` MRO inheritance smell (NOT r149-introduced) — r150+ candidate.

- **code-reviewer GREEN** : AST/trace verifications all hold (ECB / RBA / BoJ first-match-wins order verified ; "Trimmed Mean CPI" vs "Trimmed CPI" substring distinction safe ; "Official Cash Rate" blocker non-colliding with "Cash Rate") ; test deletion safety transitive argument verified ; subset-not-equality semantics correct for the consistency invariant (registry has fall-through baselines without patterns).

## Phase 3 — Build gate + Deploy + R-WITNESS-EMPIRICAL

**Build gate (MEASURED per doctrine #14)** :

- Full `apps/api` pytest : **2493 passed + 34 skipped, exit 0** (was 2458 r148 + 35 r149 net = +39 new r149 tests − 1 deletion + r142/r148/r149 invariant retains − adjustments = 2493).
- Targeted modules (event_proximity_engine + invariants_ichor + brier_optimizer_cli + brier_optimizer_v2) : 141/141.
- `test_event_proximity_engine.py` standalone : 96/96 (57 r147 + 39 r149 new).
- ruff format + check : clean.
- ADR-017 invariants : all green.
- Brier 12-factor lockstep CI guards : both r142 registry-vs-registry + r148 emission-vs-registry pass.
- NEW r149 event-class consistency invariant : pass.

**Deploy via R-DEPLOY-6 (lesson #24 SSH-timeout fired, recovered)** :

`scripts/hetzner/redeploy-api.sh` Step 1-3 completed (hard-check + backup + tar-over-ssh rsync into `/opt/ichor/api/src/src/ichor_api`) ; Step 4 (`sudo systemctl restart ichor-api`) hit `ssh: connect to host 178.104.39.201 port 22: Connection timed out` ; first manual SSH retry ALSO timed out ; SECOND retry after 15-second sleep succeeded → `SSH_OK ubuntu-16gb-nbg1-1` + manual `systemctl restart` + `healthz=200` + sample `/v1/geopolitics/briefing=200` ✓. Code on prod disk verified : `event_proximity_engine.py` 28242 bytes timestamp `May 23 19:43 UTC` + grep `"RBA"` = 8 occurrences + grep `Tankan` = 7 occurrences.

**NEW pattern observation r149** : lesson #24 SSH-timeout has now fired r147→r148→r149 **3 consecutive rounds** on Step 4 of `redeploy-api.sh`. This is a stable failure pattern, not a transient outage. **R-DEPLOY-6 explicit rule codification overdue** — r150 candidate to add explicit SSH liveness probe + retry-with-sleep BEFORE Step 4 (or refactor the script to decompose Step 4 into 3 short retryable SSH calls per the original R-DEPLOY-6 codification of r142).

**Phase 3.5 R-WITNESS-EMPIRICAL** : prod DB upcoming events probe `SELECT title FROM economic_events WHERE currency IN ('AUD','CAD') AND scheduled_at > now() AND scheduled_at < now() + interval '14 days' AND impact IN ('high','medium')` returns **0 rows**. The next RBA/BoC event window is ~3-4 weeks out (typical monthly rate-decision cadence). **GENUINE witness for r149 mapping** will come when next AUD/CAD rate decision arrives + session-card cron fires + driver populates `event_anticipation` with `event_class="RBA"` or `"BoC"` (verifiable via `SELECT drivers FROM session_card_audit WHERE drivers::text LIKE '%event_anticipation%' AND (drivers::text LIKE '%RBA%' OR drivers::text LIKE '%BoC%')`). Until then, the code is plumbed but the empirical fire is event-conditional per honest scope (analogous to r147 Engine 8 weekend-Memorial-Day pattern that took until 17:01 UTC cron + a real high-impact event window to actually exercise the new code path).

## Honest scope (doctrine #2 + #11)

- NO new ADR (additive title patterns + new baselines + defensive negative-list + new CI invariant, established lesson #34 pattern).
- NO new migration.
- NO frontend changes.
- NO data backfill needed (collector already ingests AUD/CAD/JPY events ; only mapping was missing).
- RBA/BoC NEGATIVE drift direction NOT implemented — caveat surfaced honestly via runtime `caveat` string, r150+ candidate for per-event-class sign override.
- JPY mapping is future-proofing under FF `low` impact filter (0/90d empirical) ; r150+ candidate to elevate JPY impact handling OR alternative provider.
- AUD/CAD Employment Change falls through to `high_other` 10bp (conservative cold-start prior) ; r150+ candidate for explicit mapping with currency-specific baselines.
- Per-currency CPI baseline magnitude calibration deferred r150+ (r149 uses shared 20bp for 6 variants per literature priors).

## Mission centrale axis impact

**axis-4 🎯+1 LEVEL r147 → axis-4 🎯+1 LEVEL r147+r149** (Engine 8 coverage broadened from 18 to 37 title patterns covering USD/EUR/GBP/AUD/CAD/JPY central-bank decisions + Tankan + per-country CPI variants ; AUD/CAD events will fire correctly when next rate decision arrives).

Mission centrale axes : 1-2 ✅ r123 / 3 ✅ r132+r133 / **4 🎯+1 LEVEL r147+r149 ⭐** / 5 ✅ EMPIRICALLY GREEN r146 / 6 ✅ CLOSED r142+r143 / 7 🎯 LIVE / 8 🎯+1 PARTIAL r131.

**3 of 8 axes ✅ CLOSED + axis 5 EMPIRICALLY GREEN + axis 6 visual witness GREEN + axis 4 +1 LEVEL Engine 8 LIVE+EXTENDED.**

## NEW lesson r148 codified r149 IN-CODE

The emission-vs-registry lockstep pattern (r148 doctrinal observation) is now MECHANIZED for Engine 8 via `TestR149EventClassConsistencyInvariant`. This is the SECOND instance of the pattern :

- **r148** : Brier `DEFAULT_FACTOR_NAMES` ↔ `Driver(factor=X)` emissions (AST inspection of confluence_engine.py).
- **r149** : Engine 8 `EVENT_CLASS_BASELINE_BP` ↔ `_TITLE_TO_EVENT_CLASS`-emitted classes (dict inspection of the mapping tuple).

The pattern is now codifiable as a **generic doctrine #4 SSOT extension** : when a registry-driven mapping pattern exists (`X[key]` lookup where `key` comes from an enumerated set), the consumer-side emissions MUST be set-checked against the canonical-side registry via AST/dict inspection. Subset-not-equality where registry has legitimate keys-without-emissions (fall-through defaults).

**Candidate r150** : explicit codification as **lesson #39** in `~/.claude/projects/D--Ichor/memory/ichor_r51-r71_doctrinal_patterns.md`.

## Doctrine + lesson alignment

- ✅ doctrine #1 R59-first (2 parallel sub-agents BEFORE code).
- ✅ doctrine #2 strict scope (axis-4 +1 LEVEL extension + 3 related items : new CI invariant + delete tautology + caveat fix ; all linked to Engine 8 theme).
- ✅ doctrine #4 SSOT (Engine 8 emission ↔ registry lockstep mechanized).
- ✅ doctrine #6 commit single-step NOT amend.
- ✅ doctrine #9 dated APPEND in ADR-099 §Impl(r149), NO new ADR.
- ✅ doctrine #11 calibrated honesty (RBA/BoC direction-not-implemented surfaced via runtime caveat + JPY 0/90d filter gap documented).
- ✅ doctrine #14 build gate on COMMITTED shape (2493/2493 BEFORE push).
- ✅ doctrine #17 2-reviewer concordance (backend-LLM-data-pool class).
- ✅ lesson #20 R59-AUDIT first.
- ✅ lesson #22 worktree-mismatch absolute paths.
- ✅ lesson #24 SSH-instability decompose (R-DEPLOY-6 manual completion after Step 4 timeout — 3rd consecutive round, codification overdue).
- ✅ lesson #34 lockstep CI-pin (extended to Engine 8 event-class consistency).
- ✅ lesson #37 DEMOTE framing (RBA/BoC NEGATIVE drift not implemented, surfaced honestly).
- ✅ lesson #38 trader-claims-hypothesis-verify (researcher web R59 verbatim extraction empirically grounded all paste-prompt claims).
- ✅ R-DEPLOY-6 SSH-timeout decompose pattern applied (3rd round).
- ⏳ R-WITNESS-EMPIRICAL probe pending next AUD/CAD rate decision (~3-4 weeks out).

## Voie D held — 64 rounds streak

Zero `import anthropic` r149 (CI-guarded by `test_no_anthropic_sdk_imports_in_production` in `test_invariants_ichor.py`). Pure compute title-mapping + AST invariant + sub-agent dispatch + SSH/SQL probe (sub-agents are Claude Code internal, not Anthropic API consumption per Voie D distinction). Streak continues.

## Cost

ZERO Anthropic API spend.
