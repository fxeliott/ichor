# r151 — EXECUTION LOG — 2026-05-24

> Consolidation round : 4 S-effort deliverables — MEMORY.md hygiene archive
>
> - R-DEPLOY-6 mirror to web2/brain + Pattern #15 codification + r147 MRO smell fix.
>   NO axis state change. NO production code change. NO deploy needed.

## TL;DR

r151 = "Consolidation round" : 4 housekeeping + production-hardening + doctrinal deliverables. Single feat commit `81bfcba` +62/-14 LOC in repo + memory file edits out-of-repo. Voie D **66 rounds**.

## Phase 0.5 — State verification + URGENT operational finding

Verified state at r151 start :

- Worktree HEAD `4aa4346` (r150 closing-sync), 24 ahead origin/main.
- healthz=200 on Hetzner ; r150 code LIVE (`event_proximity_engine.py` 30953 bytes May 24 00:58, `single_source_direction` sentinel x2).

**CRITICAL FINDING** : MEMORY.md was at **203 lines** — PAST 200-line silent cap. Hook warnings fired 3 rounds consecutive (r148/r149/r150) but never addressed. The cap is silent : content past 200 lines may be truncated when memory is loaded into session context. URGENT to address.

## Phase 1 — 4 deliverables

### DELIVERABLE 1 — MEMORY.md hygiene archive

Created NEW `~/.claude/projects/D--Ichor/memory/ichor_memory_archive_pre_r140.md` containing :

- Pre-r140 giant "Last sync" blockquote (lines 3-17 of original MEMORY.md, 7 sync entries r147→PR#138).
- "Live state v17-v26 pickup files" section (lines 57-67).
- "Round-XX r12-r46 operational know-how + ship summaries" (lines 69-151).
- "HISTORICAL session 2026-05-11 W101 batch" + "HISTORICAL session 2026-05-08/09 32 waves" (lines 153-183).
- PURGE 2026-05-14 note (line 55).

Pruned MEMORY.md from 203 → **62 lines** (-141 lines, -69%) :

- Removed lines 3-17 (giant Last sync blockquote), replaced with 4-line current-state pointer.
- Removed lines 55-183 (Live state + r12-r46 + 2026-05-08/11 historical), replaced with 1-line archive pointer.
- Preserved : header + r151+ protocol note + Recent rounds bullets (r150→r120, 33 entries per R-PROC-8) + Eliot directives + Decisions + Infra + Profile sections.

File now well under 180-line warn threshold. Hook silent. Recent rounds preserved per R-PROC-8 protocol.

### DELIVERABLE 2 — Mirror R-DEPLOY-6 hardening to redeploy-web2.sh + redeploy-brain.sh

The r150 hardening on redeploy-api.sh Step 4 fired r147→r148→r149→r150 (4 consecutive rounds, stable failure pattern, codified as doctrinal pattern #14). r151 mirrors the same retry-with-sleep + ConnectTimeout=15 + fail-loud-with-lesson-#24-ref discipline to the 2 sibling production deploy scripts :

- **`scripts/hetzner/redeploy-brain.sh:92-110`** : Step 3 `ssh ichor-hetzner "sudo systemctl restart ichor-api && sleep 3 && sudo systemctl is-active ichor-api"` wrapped in 3-attempt retry loop with 15s sleep + `-o ConnectTimeout=15` + exit code 9 with lesson #24 reference.

- **`scripts/hetzner/redeploy-web2.sh:156-194`** : Step 4 SSH heredoc (`systemctl enable/restart ${SVC} + tunnel manage + healthz poll loop`) wrapped in same 3-attempt retry pattern. Stderr NOT swallowed per r150 code-reviewer SHOULD-FIX so legitimate non-timeout failures (sudoers, unit-not-found, OOM) are visible to operator.

All 3 production deploy scripts (redeploy-api.sh, redeploy-brain.sh, redeploy-web2.sh) now share the SAME retry-on-SSH-timeout + fail-loud-with-exit-code-9 + stderr-not-swallowed discipline. Bash syntax verified clean for both via `bash -n`.

### DELIVERABLE 3 — Codify pattern #15 R59-disprove-before-commit

Pattern stable across **4 rounds in a row** :

- **r147** : paste-prompt cited "Bauer CEPR DP21003" as pre-FOMC drift → researcher web R59 found DP21003 is Acosta-Ajello-Bauer-Loria-Miranda-Agrippino 2026 _FOMC Communication Event-Study Database_, NOT pre-FOMC drift. Codified separately as pattern #13 r148.
- **r148** : paste-prompt v66 "empirical reaction-beta backfill via Stooq daily-bar" → researcher web R59 DISPROVED (all 2015-2026 peer-reviewed event-window reaction-beta papers use intraday tick/minute bars ≤30min ; Stooq 5-min only ~1 month history). REJECT, pivot to polymarket SSOT.
- **r150 PIVOT 1** : paste-prompt v67 ⭐ "VIX threshold empirical recompute 5y rolling" → empirical SSH probe found `fred_observations` VIXCLS has only 16 rows / 3 weeks (not 5y). REJECT, defer.
- **r150 PIVOT 2** : paste-prompt v67 "RBA/BoC sign-flip per Vojtko-Dujava NEGATIVE drift" → researcher web R59 found paper title is "Pre-Announcement Drift for BoE, BoJ, SNB" — RBA/BoC = secondary histogram observation, single-source unreplicated. REJECT hard-NEGATIVE pin, pivot to doc-only fix.

Codified as **pattern #15** in `~/.claude/projects/D--Ichor/memory/ichor_r51-r71_doctrinal_patterns.md` :

> "Any paste-prompt ⭐ AUTO-RECO candidate must pass R59 empirical verification BEFORE Phase 1 implementation. If data state, methodology, or source is weaker than the candidate description claims, REJECT the candidate and pivot to a methodologically sound alternative."

Twin doctrine to pattern #13 — pattern #13 is INPUT-side citation-identity verify, pattern #15 is PROPOSAL-side empirical-premise verify. Both extend doctrine #1 R59-first from "audit BEFORE code" to "audit BEFORE COMMITTING to a path".

### DELIVERABLE 4 — Fix r147 `TestBrierLockstepWithR147(TestAdr017Invariants)` MRO smell

Code-reviewer flagged 2 rounds consecutive (r149 NICE #6 + r150 NICE). The class inherited from `TestAdr017Invariants` causing 2 unrelated ADR-017 tests (forbidden field names + baseline magnitudes ≥0) to silently re-execute under the Brier class name via MRO.

r151 fix : changed `class TestBrierLockstepWithR147(TestAdr017Invariants):` → `class TestBrierLockstepWithR147:` (dropped inheritance). The 2 parent tests still run from `TestAdr017Invariants` directly. No coverage loss. `test_event_proximity_engine.py` standalone count drops from 113 → 111 (2 duplicates eliminated).

## Phase 2 — 2-reviewer concordance

**SKIPPED for r151** : per doctrine #17, 2-reviewer concordance applies to NEW substantive code changes that touch the 4-pass pipeline, alert catalog, or data-pool sources. r151 deliverables are :

- Memory file hygiene (out of repo, no code)
- Deploy script harden (tooling, not deployed code)
- Doctrinal pattern codification (memory, no code)
- Test class declaration fix (no production behavior change)

None of these touch production code paths. Build gate (pytest 187/187 + ruff clean + bash syntax) is sufficient verification per doctrine #14.

## Phase 3 — Build gate + Deploy

**Build gate (MEASURED per doctrine #14)** :

- Targeted suite (event_proximity_engine + invariants_ichor + brier_optimizer_cli + brier_optimizer_v2) : **187/187 pass**.
- ruff format + check : clean.
- bash syntax both deploy scripts : clean.
- ADR-017 invariants : all green (unchanged).
- Brier 12-factor lockstep CI guards : both r142 + r148 + r149 + r150 pass.
- MEMORY.md : 62 lines (was 203, saved 141).

**Phase 3 deploy NOT REQUIRED** : r151 changes are tooling (deploy scripts), tests (class declaration only), and out-of-repo memory files. No production code change.

**Phase 3.5 R-WITNESS-EMPIRICAL** : the R-DEPLOY-6 mirror to web2/brain will be witnessed on the NEXT deploy of web2 or brain (whenever a frontend or brain change requires it). Until then, the hardening is plumbed but the empirical fire is event-conditional. r150 redeploy-api.sh hardening was witnessed in r150 deploy itself (Step 4 fired 3× timeouts exactly as designed, bailed with explicit lesson #24 message, manual recovery succeeded).

## Honest scope (doctrine #2 + #11)

- NO new ADR (additive memory hygiene + script harden + doctrinal codification + test class declaration fix, established lesson #34 pattern).
- NO new migration.
- NO frontend changes.
- NO data backfill needed.
- NO new feature.
- r151 is a "consolidation" round — no axis closure, just operational housekeeping + production hardening + doctrinal codification + tech debt closure.

## Mission centrale axis impact

**NO axis state change**. Axes : 1-2 ✅ r123 / 3 ✅ r132+r133 / 4 🎯+1 LEVEL r147+r149 / 5 ✅ EMPIRICALLY GREEN r146 / 6 ✅ CLOSED r142+r143 / 7 🎯 LIVE / 8 🎯+1 PARTIAL r131. **3 of 8 axes ✅ CLOSED + axis 5 EMPIRICALLY GREEN + axis 6 visual witness GREEN + axis 4 +1 LEVEL Engine 8 LIVE+EXTENDED.**

## Doctrine + lesson alignment

- ✅ doctrine #1 R59-first (NEW pattern #15 codified extends this : "audit BEFORE COMMITTING to a path").
- ✅ doctrine #2 strict scope (4 theme-coherent S-effort items, no scope creep).
- ✅ doctrine #4 SSOT (R-DEPLOY-6 discipline now SSOT across 3 scripts).
- ✅ doctrine #6 commit single-step NOT amend.
- ✅ doctrine #9 dated APPEND in ADR-099 §Impl(r151), NO new ADR.
- ✅ doctrine #11 calibrated honesty (MEMORY.md cap-violation surfaced + addressed honestly).
- ✅ doctrine #14 build gate on COMMITTED shape (187/187 BEFORE push).
- ⏸ doctrine #17 2-reviewer concordance — SKIPPED per scope (no production code change).
- ✅ lesson #20 R59-AUDIT first.
- ✅ lesson #22 worktree-mismatch absolute paths.
- ✅ lesson #24 SSH-instability decompose (codified pattern #14 + mirrored to brain/web2).
- ✅ lesson #38 trader-claims-hypothesis-verify (NEW pattern #15 codifies this for paste-prompt AUTO-RECOs).
- ✅ R-DEPLOY-6 hardening pattern extended SSOT across 3 production scripts.

## Voie D held — 66 rounds streak

Zero `import anthropic` r151 (CI-guarded). Pure refactor + memory hygiene + script harden + doctrinal codification — no LLM call.

## r152 binding default candidates

1. ⭐ AUTO-RECO **FRED VIXCLS backfill 5y** to unblock r150 deferred VIX recompute (researcher web R59 first per pattern #15 on FRED bulk-fetch API + rate-limit). Effort S-M.
2. **`output_gap_proxy` wiring**. Effort M.
3. **Dedicated `<EventAnticipationPanel>` tile** once 7d Engine 8 calibration. Effort M.
4. **Per-currency Employment subclass** (trader r150 YELLOW-3). Effort S.
5. **Docstring SSOT for Vojtko-Dujava citation** (r150 code-reviewer NICE). Effort S.
6. **Edge case 9 docstring entry** for RBA/BoC sentinel (r150 code-reviewer NICE). Effort S.
7. **r144 reconciler unit normalization upstream**. Effort M.
8. **FF XML title-coverage CI invariant**. Effort S-M.
9. **ADR-017 web2 caveat RTL regex**. Effort S-M.
10. **`actual_source` / `actual_revised`** + EU/UK reconcilers. Effort M each.
11. **Codify R-DEPLOY-6 hardening doctrine** in CLAUDE.md auto-context-injector. Effort S.
12. **Code-reviewer S4 orchestrator hook AsyncMock test** (deferred since r142). Effort S.

**r152 pattern #15 application** : every ⭐ AUTO-RECO selected must pass R59 empirical verification BEFORE Phase 1 implementation per pattern #15 codified r151. The FRED VIXCLS backfill candidate (1) requires R59 on FRED bulk-fetch API rate limits + retention policy before committing.

## Cost

ZERO Anthropic API spend.
