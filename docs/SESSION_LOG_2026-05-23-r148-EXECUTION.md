# r148 — EXECUTION LOG — 2026-05-23

> Tier 4 hygiene + Tier 1 doctrine : polymarket factor name SSOT alignment +
> emission-vs-registry CI invariant + r147 carry-forward fix. **PIVOT** from
> paste-prompt v66 default candidate (a) "empirical reaction-beta backfill"
> because researcher web R59 disproved the methodological coherence. Anti-FOMO
> trader discipline + lesson #38 trader-claims-hypothesis-verify.

## TL;DR

r148 closes the polymarket factor-name SSOT defect carried since r142 LIVE +
the CI guard gap that allowed it to ship undetected. Pure defect fix + new
CI invariant + r147 carry-forward hygiene fix. Voie D held **63 rounds**.
No axis state change ; r148 is infrastructure correctness, not axis closure.

The CI guard gap is the highest-leverage piece : pre-r148 the only Brier
lockstep test checked registry-vs-registry equality (r142 lesson #34), never
inspected actual `Driver(factor=X)` emissions. The new r148 AST invariant
mechanically protects all 12 factor builders against the same bug class
going forward (one CI guard, every future builder protected).

## Phase 0 — R59 dual-audit (2 parallel sub-agents)

- **ichor-navigator** mapped the polymarket factor → Brier flow :
  `assess_confluence()` emits `Driver(factor=X)` → persisted to
  `session_card_audit.drivers` JSONB ; `brier_optimizer.py:283-321` does
  `arr = np.array([by_factor.get(name, 0.5) for name in factor_names])` —
  silent fall-through to neutral 0.5 ; runtime `_factor_weight()` similarly
  silent-defaults to 1.0 ; identified the CI guard gap (pre-r148 tests only
  checked registry-vs-registry equality, never inspected actual emissions).

- **researcher web** verified the academic literature on event-window
  reaction-betas (Lucca-Moench 2015 _JoF_ + Kurov-Halova-Wolfe-Gilbert 2019
  _JFQA_ + Acosta-Ajello-Bauer-Loria-Miranda-Agrippino 2025 SF Fed WP 2025-30
  - Pinchuk 2022 arXiv 2212.04525 + Casini-McCloskey 2024 arXiv 2406.15667)
  - pricing tiers of Polygon / Alpha Vantage / Dukascopy / Stooq as of
    May 2026 → recommended DEFER candidate #1 (methodologically incoherent
    as written ; Stooq/yfinance daily-bar cannot estimate 5-min intraday
    reaction-betas ; Stooq 5-min has only ~1 month of history vs 5y assumed).

## Phase 1 — Implementation (3 files, +107 / -2)

Commit `3191616` "fix(api): r148 polymarket factor name SSOT alignment +
emission-vs-registry CI invariant" :

1. **`apps/api/src/ichor_api/services/confluence_engine.py:414`** —
   `factor="polymarket"` → `factor="polymarket_overlay"` 1-line align to
   canonical name in `brier_optimizer.DEFAULT_FACTOR_NAMES` +
   `cli.run_brier_optimizer._FACTOR_NAMES`. 2-line r148 doctrine comment
   in local round-tag convention.

2. **NEW `apps/api/tests/test_invariants_ichor.py::test_r148_confluence_engine_driver_emissions_match_brier_registry`**
   (+91 LOC + `import ast`) — AST-parses `confluence_engine.py`, extracts
   every literal `Driver(factor=<str>, ...)` emission via `ast.walk`
   filtered on `ast.Call` with `func.id == "Driver"` or
   `func.attr == "Driver"`, asserts set-equality vs `DEFAULT_FACTOR_NAMES`.
   Fails loudly on dynamic (non-`ast.Constant`) factor values to prevent
   future silent breakage via f-string / variable / unpack patterns.

   **Empirically verified** to catch the bug : temporarily reverted the
   fix → test failed with diagnostic `"Emitted but missing from registry :
['polymarket']"` ; re-applied → test passes.

3. **`apps/api/tests/test_brier_optimizer_cli.py::test_factor_names_match_confluence_engine`**
   — added `"event_anticipation"` to hard-coded expected set (r147 carry-
   forward hygiene). r147 added `event_anticipation` to `_FACTOR_NAMES`
   but missed this parallel hand-maintained test ; the full apps/api suite
   has been at 2457 passed + 1 failed since r147 — r147's "214/214" claim
   was a tight subset, not the full suite. r148 docstring flags the test
   as tautology relative to the new AST invariant ; deletion candidate
   r149.

## Phase 2 — 2-reviewer concordance (doctrine #17 backend-LLM-data-pool class)

| Reviewer      | Verdict        | Findings                               |
| ------------- | -------------- | -------------------------------------- |
| ichor-trader  | SHIP-WITH-FIX  | 0 RED + 3 YELLOW + GREEN ADR-017 chain |
| code-reviewer | READY TO MERGE | 0 CRITICAL + 1 SHOULD-FIX + 2 NICE     |

**Concordance** : both reviewers flagged the SAME single concern — "30-day
Brier rolling-window historical JSONB contamination" (trader Y1 = code-
reviewer SHOULD-FIX). **RESOLVED EMPIRICALLY** via pre-emptive SSH probe :
`SELECT COUNT(*) FROM session_card_audit WHERE drivers::text LIKE '%"factor":
"polymarket"%'` returns **0** across the entire DB history. `_factor_polymarket()`
has returned None on every prod card since r142 LIVE (no `_POLY_KEYWORDS`
match-impact fired for any persisted asset/snapshot) ; production-side bug
exposure = nil ; rolling-window contamination concern is moot.

Trader Y2 (per-asset transmission empirical witness) = natural Phase 3.5
R-WITNESS-EMPIRICAL probe on next session-card cron fire.

Trader Y3 (empirical magnitude probe SQL) = answered pre-review by the same
SSH probe above.

Code-reviewer GREEN ratings : AST walk completeness verified across all 12
`Driver(...)` call sites ; set-equality semantics confirmed correct (subset
would hide registry-without-emission drift) ; dynamic-emission detection
correct for `ast.JoinedStr` (f-strings) + `ast.Name` (variable refs) ; error
message actionability + comment style + ruff/prettier risk all GREEN.

## Phase 3 — Build gate + Deploy + R-WITNESS-EMPIRICAL

**Build gate (MEASURED per doctrine #14)** :

- Full `apps/api` pytest : **2458 passed + 34 skipped, exit 0**
  (was 2457 passed + 1 r147 carry-forward failed = 2458 collected ; both
  green post-r148).
- Targeted modules : 197/197.
- ruff format + check : clean.
- ADR-017 invariants : all green.
- Brier 12-factor lockstep CI guards : both r142 registry-vs-registry AND
  new r148 emission-vs-registry pass.

**Deploy via R-DEPLOY-6 (lesson #24 SSH-timeout fired, recovered)** :
`scripts/hetzner/redeploy-api.sh` Step 1-3 completed (hard-check + backup

- tar-over-ssh rsync into `/opt/ichor/api/src/src/ichor_api`) ; Step 4
  (`sudo systemctl restart ichor-api`) hit `ssh: connect to host port 22:
Connection timed out` (lesson #24 recurrence). Manual completion via
  direct SSH after liveness probe (`SSH_OK ubuntu-16gb-nbg1-1`) : restart
- healthz=200 + sample=/v1/geopolitics/briefing=200 ✓. Code on prod disk
  verified `factor="polymarket_overlay"` at line 416 with timestamp
  `May 23 14:22 UTC`.

**Phase 3.5 R-WITNESS-EMPIRICAL** : next `ichor-session-cards-ny_mid.timer`
fire `Sat 2026-05-23 17:01:17 CEST` (= 15:01:17 UTC, ~2h11 from deploy
completion) will exercise the polymarket factor path with the new canonical
name. Empirically witnessable post-fire via :

```sql
SELECT COUNT(*) FROM session_card_audit
WHERE created_at > '2026-05-23 15:00:00 UTC'
  AND drivers::text LIKE '%polymarket_overlay%';
```

Today's polymarket factor will likely return None (per `_factor_polymarket()`
empirical pattern observed in last 45 prod cards) ; the GENUINE witness for
the fix will come when polymarket actually fires (event-conditional, expected
when `_POLY_KEYWORDS` keyword-impact match triggers on a recent polymarket
snapshot question).

## Honest scope (doctrine #2 + #11)

- NO new ADR (additive 1-line fix + new CI invariant + r147 carry-forward
  hygiene, established lesson #34 pattern)
- NO new migration
- NO frontend changes
- NO data backfill needed (0 historical rows had the buggy literal —
  zero-exposure SQL probe per doctrine #11)
- Deletion of now-tautological `test_factor_names_match_confluence_engine`
  deferred r149 (one round buffer for new invariant to stabilize)
- The r147 carry-forward fix surfaces + closes the latent "214/214 was
  subset" discrepancy honestly

## Mission centrale axis impact

**No axis state change** — r148 is doctrinal hygiene + Brier infrastructure
correctness, not axis closure. The polymarket factor (axis-4 + axis-8
contributor) is now Brier-weighted correctly for future weights ; the new
emission-vs-registry CI invariant protects all 12 factors (every Mission
axis touching the confluence pipeline) against the same class of bug going
forward.

Axes : 1-2 ✅ r123 / 3 ✅ r132+r133 / 4 🎯+1 LEVEL r147 / 5 ✅ EMPIRICALLY
GREEN r146 / 6 ✅ CLOSED r142+r143 / 7 🎯 LIVE / 8 🎯+1 PARTIAL r131.

**3 of 8 axes ✅ CLOSED + axis 5 EMPIRICALLY GREEN + axis 6 visual witness
GREEN + axis 4 +1 LEVEL Engine 8 LIVE.**

## NEW lesson r147 codified r148

**citation-identity-verify-via-web-R59-before-pin** appended as pattern #13
to `~/.claude/projects/D--Ichor/memory/ichor_r51-r71_doctrinal_patterns.md`.
Codifies doctrine #11 calibrated-honesty extension on EXTERNAL fact
verification (distinct from lesson #38 INTERNAL claim verification). Every
academic citation pinned into Ichor doctrine / ADR / paste-prompt / code
comment requires URL primary-source verification at codify time.

## NEW pattern observation r148 (r149 codification candidate)

**emission-vs-registry lockstep is a necessary complement to registry-vs-
registry lockstep** when a factor-builder-like pattern exists. Set-equality
between two registries (lesson #34 r142) is INSUFFICIENT if a third site
(the emission) can drift independently. The r148 AST-walk invariant adds
the missing third-place lockstep mechanically. Apply pattern to any future
architectural element where N+1 lockstep sites might form. Codify as lesson
#39 in r149.

## Doctrine + lesson alignment

- ✅ doctrine #1 R59-first (2 parallel sub-agents BEFORE code)
- ✅ doctrine #2 strict scope (defect fix + CI guard + carry-forward
  hygiene ; no scope creep into reaction-beta backfill ; documentation-only
  for the historical concern per doctrine #11)
- ✅ doctrine #4 SSOT (lockstep extended to emission-vs-registry)
- ✅ doctrine #6 commit single-step NOT amend (ruff-format pre-applied
  before stage)
- ✅ doctrine #9 dated APPEND in ADR-099 §Impl(r148), NO new ADR
- ✅ doctrine #11 calibrated honesty (zero-exposure empirically verified
  BEFORE writing closing-sync, not assumed)
- ✅ doctrine #14 build gate on COMMITTED shape (2458/2458 BEFORE push)
- ✅ doctrine #17 2-reviewer concordance (backend-LLM-data-pool class)
- ✅ lesson #20 R59-AUDIT first (pre-emptive SQL probe answered Y1+Y3
  before reviewers returned)
- ✅ lesson #22 worktree-mismatch absolute paths
- ✅ lesson #24 SSH-instability decompose (R-DEPLOY-6 manual completion
  after script Step 4 timeout)
- ✅ lesson #34 lockstep CI-pin (extended emission-vs-registry)
- ✅ lesson #38 trader-claims-hypothesis-verify (paste-prompt v66 candidate
  #1 daily-bar regression disproved by researcher web R59 ; rejected per
  anti-FOMO trader discipline)
- ✅ R-DEPLOY-6 (Step 4 SSH-timeout decompose pattern applied)
- ⏳ R-WITNESS-EMPIRICAL (probe scheduled for 15:01 UTC cron fire)

## Voie D held — 63 rounds streak

Zero `import anthropic` r148 (CI-guarded). Pure compute factor name
alignment + AST invariant + SSH/SQL probe + sub-agent dispatch (sub-agents
are Claude Code internal, not Anthropic API consumption per Voie D
distinction). Streak continues.

## Cost

ZERO Anthropic API spend.
