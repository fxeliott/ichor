# r150 — EXECUTION LOG — 2026-05-23

> Tier 1 calibrated-honesty + Tier 4 Engine 8 extension + Deploy infrastructure :
> single-source disclosure + AUD/CAD Employment class + R-DEPLOY-6 Step-4 hardening.
> **TWO HARDCORE PIVOTS** via R59 in one round — paste-prompt candidates #1 (VIX) AND #2
> (RBA/BoC sign-flip CODE) BOTH disproved, lesson #38 trader-claims-hypothesis-verify
> applied twice. Pivoted to documentation-only fix + Engine 8 Employment extension +
> deploy script harden.

## TL;DR

r150 demonstrated the R59-disprove-before-commit pattern across TWO pivots in a single
round :

- **PIVOT 1** (Phase 0.5) : VIX threshold empirical recompute REJECTED — VIXCLS DB has only 16 obs / 3 weeks (not 5y as candidate described).
- **PIVOT 2** (researcher web R59) : RBA/BoC sign-flip CODE REJECTED — Vojtko-Dujava paper title is "BoE/BoJ/SNB", RBA/BoC is secondary histogram, single-source unreplicated.

Pivoted to : (a) documentation honesty fix + parse_failures sentinel for RBA/BoC events ;
(b) AUD/CAD Employment Change explicit mapping (new "Employment" event class 20bp baseline) ;
(c) R-DEPLOY-6 Step-4 SSH-timeout hardening (3-attempt retry + ConnectTimeout=15 + lesson #24
codification as pattern #14 in memory). **R-DEPLOY-6 hardening empirically witnessed in r150
deploy itself** — Step 4 fired 3× timeouts, script bailed with explicit lesson #24 message,
manual recovery succeeded.

Voie D held **65 rounds**. Mission centrale axes unchanged (NO axis state change).

## Phase 0.5 — Empirical SSH probe + PIVOT 1

Probed `fred_observations` for VIXCLS data to validate candidate #1 ⭐ AUTO-RECO premise :

```sql
SELECT percentile_cont(0.50) AS p50, percentile_cont(0.75) AS p75,
       MIN(observation_date), MAX(observation_date), COUNT(*) AS n
FROM fred_observations
WHERE series_id='VIXCLS' AND observation_date >= now() - interval '5 years';
```

**Result** : n=16, range 2026-04-30 → 2026-05-21 (~3 weeks), p50=17.41, p75=18.00, min=16.76, max=18.43.

The candidate description claimed "5y rolling window" but the data state is ~3 weeks. Implementing the rolling recompute would replace the robust long-run Kurov 2021 hardcoded values (p50=18.0, p75=24.0) with biased micro-sample values from a low-vol regime — artificially amplifying Engine 8 signal under current VIX conditions. **Same methodological error class as r148 candidate #1 daily-bar reaction-beta** which researcher web R59 disproved (Stooq 5-min only ~1 month of history). PIVOT 1 triggered.

## Phase 0 — R59 dual-audit (2 parallel sub-agents)

- **ichor-navigator** scoped the sign computation path : `event_proximity_engine.py:541` `signed = magnitude_unsigned * business_cycle_sign` ; line 543 derives `expected_drift_direction` from sign ; 4 implementation options evaluated, recommended approach (D) `effective_sign = business_cycle_sign * (-1 if event_class in {"RBA","BoC"} else +1)` compose. **APPROACH NOT IMPLEMENTED per PIVOT 2 below**.

- **researcher web** triple-verified Vojtko-Dujava SSRN 5384407 (June 2025) :
  - Paper title is actually **"Pre-Announcement Drift for BoE, BoJ, SNB"** (NOT RBA/BoC).
  - RBA/BoC NEGATIVE drift appears only as **secondary histogram observation** (commodity-exporter divergence hypothesis).
  - **Single source, unreplicated**, working paper (71 downloads, no peer review).
  - **Zero independent confirmation** in Kurov / Boyd-Hu-Jagannathan / BIS / RBA / BoC research.
  - Recommendation (B) WEAK — **DO NOT pin hard NEGATIVE -25bp magnitude** based on single source.

PIVOT 2 triggered. Same pattern as r147 Bauer DP21003 hallucination + r148 daily-bar : R59 disproves AUTO-RECO premise BEFORE Phase 1 implementation.

## Phase 1 — Implementation (single feat commit `9ee664e` +343 / -26 LOC)

1. **`apps/api/src/ichor_api/services/event_proximity_engine.py`** :
   - Module docstring lines 46-52 : updated Vojtko-Dujava citation to accurately reflect paper title + single-source weakness + lesson #38/#11 framing.
   - `EVENT_CLASS_BASELINE_BP` comment 118-130 : single-source disclosure + r150 sign-flip-deferred-indefinitely note.
   - `assess_event_proximity()` docstring "RBA/BoC PRE-DRIFT DIRECTION" honest-scope block rewritten.
   - NEW `"Employment": 20.0` baseline (aligned NFP per labor-market literature).
   - `_TITLE_TO_EVENT_CLASS` : NEW patterns `("employment change", "Employment")` + `("unemployment rate", "Employment")` ordered AFTER NFP-specific to preserve first-match-wins.
   - Runtime `caveat` string for `event_class in ("RBA","BoC")` updated : `"Drift pre-event RBA/BoC : source unique non-répliquée (Vojtko-Dujava SSRN 5384407 — sign-flip secondaire vs BoE/BoJ/SNB)"`.
   - **Trader YELLOW-2 + code-reviewer SHOULD-FIX #1 CONCORDANT** : added `parse_failures.add("single_source_direction")` sentinel for RBA/BoC events — mirrors r141 `SurpriseClassification.parse_failures` pattern, enables mechanical downstream filtering instead of caveat-string regex parsing.

2. **`apps/api/tests/test_event_proximity_engine.py`** (+343 LOC, 17 new tests across 5 classes) :
   - `TestR150EmploymentClassMapping` (5) : bare Employment Change AUD/CAD + Unemployment Rate + 2 NFP regression.
   - `TestR150NfpMappingPriorityProtected` (4 — trader YELLOW-4) : first-match-wins discipline + NFP-priority defensive pin + Employment Change edge cases.
   - `TestR150VojtkoDujavaSingleSourceDisclosure` (3) : RBA/BoC caveat contains "source unique non-répliquée" + "BoE/BoJ/SNB" + FOMC regression.
   - `TestR150SingleSourceDirectionSentinel` (3 — trader YELLOW-2 + code-reviewer SHOULD-FIX #1) : RBA/BoC events emit sentinel mechanically + FOMC regression.
   - `TestR150EmploymentBaseline` (2) : pin Employment=20bp + NFP magnitude consistency.

3. **`scripts/hetzner/redeploy-api.sh:107-130`** (Step 4 hardening) :
   - Decomposed single `${SSH} "sudo systemctl restart ${SVC}"` into 3-attempt retry loop with 15s sleep + `-o ConnectTimeout=15` per attempt + explicit `fail` exit code 9 with lesson #24 reference.
   - **Code-reviewer SHOULD-FIX #2** : dropped `2>/dev/null` so legitimate non-timeout failures (sudoers, unit-not-found, OOM) leak to stderr.
   - Pattern fired r147→r148→r149→**r150 (4th consecutive round)**.

4. **`~/.claude/projects/D--Ichor/memory/ichor_r51-r71_doctrinal_patterns.md`** (memory file, out of repo) : NEW **pattern #14** codifying R-DEPLOY-6 Step-4 SSH-timeout decompose rule with explicit recommended discipline for ANY future deploy script touching ichor-hetzner.

## Phase 2 — 2-reviewer concordance (doctrine #17 backend-LLM-data-pool)

| Reviewer      | Verdict         | Findings                                 |
| ------------- | --------------- | ---------------------------------------- |
| ichor-trader  | SHIP-WITH-FIXES | 0 RED + 4 YELLOW + 4 GREEN               |
| code-reviewer | READY TO MERGE  | 0 CRITICAL + 2 SHOULD-FIX + 3 NICE/GREEN |

**Concordance applied** :

- **trader YELLOW-2 = code-reviewer SHOULD-FIX #1** : missing `parse_failures` sentinel for single-source RBA/BoC disclosure. Caveat string-only honesty is asymmetric (visible to user, invisible to Brier/frontend). **APPLIED** via `parse_failures.add("single_source_direction")` mirroring r141 `SurpriseClassification.parse_failures`. 3 new tests `TestR150SingleSourceDirectionSentinel` verify the sentinel + FOMC regression.
- **trader YELLOW-4** : first-match-wins drift risk on future FF NFP rebrand. **APPLIED** via NEW `TestR150NfpMappingPriorityProtected` (4 tests pinning NFP priority + Employment Change edge cases + country-suffix variant).
- **trader YELLOW-7** (magnitude weakening for RBA/BoC) : two options offered, chose option (b) keep 25bp + sentinel (option a would under-weight if Vojtko-Dujava actually right ; option b preserves signal + flags weakness mechanically via sentinel from YELLOW-2 fix).
- **code-reviewer SHOULD-FIX #2** : `2>/dev/null` over-suppresses errors in retry loop. **APPLIED** : dropped suppression, stderr leaks through.

**Deferred r151+** : trader YELLOW-3 per-currency Employment subclass (US-NFP 200K vs AUD/CAD ~20K swings) + code-reviewer NICE docstring SSOT for Vojtko-Dujava + edge-case-9 docstring entry + r147 `TestBrierLockstepWithR147(TestAdr017Invariants)` MRO smell.

## Phase 3 — Build gate + Deploy + R-WITNESS-EMPIRICAL

**Build gate (MEASURED per doctrine #14)** :

- Full `apps/api` pytest : **2506 passed + 34 skipped, exit 0** (was 2493 r149 + 13 net r150 = 2506).
- Targeted suite : 182/182 (event_proximity 113/113 + invariants_ichor 45/45 + brier_optimizer_cli 3/3 + brier_optimizer_v2 27/27).
- `test_event_proximity_engine.py` standalone : 113/113 (96 r149 baseline + 17 r150 new).
- ruff format + check : clean.
- ADR-017 invariants : all green.
- Brier 12-factor lockstep CI guards : both r142 registry-vs-registry + r148 emission-vs-registry pass.
- r149 event-class consistency invariant : pass (Employment ∈ both emissions + registry).

**Deploy via R-DEPLOY-6 (hardened) — EMPIRICALLY WITNESSED** : new retry loop fired EXACTLY as designed. Output :

```
Step 4 attempt 1/3 failed (timeout OR non-zero exit, see stderr above), sleep 15s + retry
Step 4 attempt 2/3 failed (timeout OR non-zero exit, see stderr above), sleep 15s + retry
Step 4 attempt 3/3 failed (timeout OR non-zero exit, see stderr above), sleep 15s + retry
FATAL: Step 4 SSH restart failed 3 attempts (lesson #24 SSH-instability cluster) — manual intervention required
```

Bailed after 3 attempts with explicit lesson #24 message + clear stderr leakage (no `2>/dev/null` swallowing). Manual recovery via 30s SSH sleep + direct restart succeeded : `SSH_OK ubuntu-16gb-nbg1-1` + `healthz=200` + `sample=200`. Code on prod verified : `event_proximity_engine.py` 30953 bytes timestamp `May 23 22:58 UTC` + grep `"Employment"` = 3 occurrences + grep `single_source_direction` = 2 occurrences.

**The R-DEPLOY-6 hardening is now empirically validated** — it bailed cleanly when SSH was truly down, AND surfaced the failure mode in stderr per code-reviewer SHOULD-FIX #2.

**Phase 3.5 R-WITNESS-EMPIRICAL** : prod DB probe `SELECT title FROM economic_events WHERE currency IN ('AUD','CAD') AND scheduled_at > now() AND scheduled_at < now() + interval '14 days' AND impact IN ('high','medium')` returns 0 rows. Next AUD/CAD rate decision ~3-4 weeks (typical monthly cadence). Genuine witness for the new Employment class + RBA/BoC sentinel pending event-conditional fire (analogous to r147+r149 Engine 8 weekend pattern).

## Honest scope (doctrine #2 + #11)

- NO new ADR (additive documentation honesty + Employment class extension + script harden + memory codification, established lesson #34 pattern).
- NO new migration.
- NO frontend changes.
- NO data backfill needed.
- RBA/BoC sign-flip CODE implementation DEFERRED INDEFINITELY pending peer-reviewed replication of Vojtko-Dujava.
- Per-currency Employment subclass DEFERRED r151+ (trader YELLOW-3 cold-start acceptable).
- r147 `TestBrierLockstepWithR147(TestAdr017Invariants)` MRO smell DEFERRED r151+ (NOT r149/r150-introduced).
- VIX threshold empirical recompute DEFERRED until ≥1 year VIXCLS data accumulated OR FRED bulk backfill.

## Mission centrale axis impact

**NO axis state change** — r150 is calibrated-honesty documentation + Engine 8 Employment class extension + deploy infrastructure hardening, not axis closure.

Axes : 1-2 ✅ r123 / 3 ✅ r132+r133 / 4 🎯+1 LEVEL r147+r149 / 5 ✅ EMPIRICALLY GREEN r146 / 6 ✅ CLOSED r142+r143 / 7 🎯 LIVE / 8 🎯+1 PARTIAL r131.

## NEW pattern observation r150 (r151 codification candidate)

The **R59-disprove-before-commit pattern** is now stable across **4 rounds in a row** :

- **r147** : Bauer CEPR DP21003 paper-identity hallucination caught via researcher web R59 (codified as pattern #13 in r148).
- **r148** : daily-bar reaction-beta methodology disproved (5-min vs daily-bar mismatch, no 5y Stooq history).
- **r150 PIVOT 1** : VIX 5y rolling recompute disproved (only 3 weeks of data in `fred_observations`).
- **r150 PIVOT 2** : RBA/BoC sign-flip disproved (single-source paper, secondary observation, no peer review).

**Codification candidate r151 as pattern #15** : "any paste-prompt ⭐ AUTO-RECO candidate must pass R59 empirical verification BEFORE Phase 1 implementation ; reject if data state / methodology / source is weaker than candidate description claims". Twin doctrine to pattern #13 (citation-identity verify) — pattern #13 is INPUT-side (verify the citation), pattern #15 would be PROPOSAL-side (verify the proposal's premise).

## Doctrine + lesson alignment

- ✅ doctrine #1 R59-first (TWO pivots applied this round + dual-audit sub-agents).
- ✅ doctrine #2 strict scope (3 themes : documentation honesty + Engine 8 extension + deploy harden ; tightly bounded).
- ✅ doctrine #4 SSOT (Vojtko-Dujava citation in 3 sites kept consistent ; r151 candidate to SSOT-extract).
- ✅ doctrine #6 commit single-step NOT amend (1 feat commit + 1 closing-sync commit).
- ✅ doctrine #9 dated APPEND in ADR-099 §Impl(r150), NO new ADR.
- ✅ doctrine #11 calibrated honesty (TWO PIVOTS demonstrate the discipline scales ; sentinel surfaces weakness mechanically).
- ✅ doctrine #14 build gate on COMMITTED shape (2506/2506 BEFORE push).
- ✅ doctrine #17 2-reviewer concordance.
- ✅ lesson #20 R59-AUDIT first.
- ✅ lesson #22 worktree-mismatch absolute paths.
- ✅ lesson #24 SSH-instability decompose (codified as pattern #14 + script hardened + empirically witnessed in r150 deploy).
- ✅ lesson #34 lockstep CI-pin (Employment ∈ both emissions + registry).
- ✅ lesson #37 DEMOTE framing (RBA/BoC sign-flip NOT implemented, surfaced honestly via caveat + sentinel).
- ✅ lesson #38 trader-claims-hypothesis-verify (applied TWICE in r150 via PIVOT 1 + PIVOT 2).
- ✅ R-DEPLOY-6 Step-4 SSH-timeout decompose (codified as pattern #14 + empirically witnessed).

## Voie D held — 65 rounds streak

Zero `import anthropic` r150 (CI-guarded). Pure compute documentation + pattern extension + AST/sentinel invariants + SSH/SQL probe + sub-agent dispatch + bash script harden. Streak continues.

## Cost

ZERO Anthropic API spend.
