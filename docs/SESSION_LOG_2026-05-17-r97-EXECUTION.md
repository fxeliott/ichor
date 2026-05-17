# SESSION_LOG 2026-05-17 — r97 EXECUTION (ADR-099 §Tier-3 doc/infra-hygiene — vitest CI-gating + ADR README index back-fill)

**Round type:** Tier-3 autonomy-hardening continuation — the r96
SESSION_LOG / pickup v26 binding default ("Tier 3 continues, R59 first,
pick highest value/effort ; (a) doc/infra-hygiene recommended FIRST,
blast-radius LOW"). The standing-brief re-issuance = "continue"
(doctrine #10). Re-evaluated value/effort across (a) doc/infra-hygiene
/ (b) cron holiday-gate (HIGH blast) / (c) GBP Driver-3 (chicken-egg
multi-round) — no superior emergent gap (KeyLevels joke-market /
Pass-6 retry / MEMORY cap all < (a)'s value). No pivot. **CI-only,
ZERO Hetzner deploy** (the safest possible blast-radius — the dette had
been carried 5+ rounds since r91).

**Branch:** `claude/friendly-fermi-2fff71` (worktree
`D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`). **ZERO Anthropic
API** (pure dev-infra + docs, Voie D). ADR-017 N/A (no signal surface;
the new test even pins a BUY/SELL canary on the data-honesty SSOT).
Purely additive; zero backend / data-pool / 4-pass / collector /
alert-catalog change.

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work in
`friendly-fermi-2fff71`. Verified by tool: HEAD `4e4cc96` (r96), 61
ahead origin/main, 0 uncommitted, pushed, PR #138 OPEN. Live == the
prompt failsafe — zero divergence. 2 parallel read-only R59 sub-agents
mapped the EXACT real state (memory/prompt characterization treated as
hypothesis until file:line verified — doctrine #3).

## R59 reshaped the design (doctrine #3 — the memory note was wrong on 3 points)

The carried-forward flag said "vitest PRE-BROKEN repo-wide (vite/vitest
peer skew) ; `api.test.ts` breaks identically ; verdict + dataIntegrity

- fred-liveness + data_integrity tests don't run in CI". R59
  disentangled it:

1. **NOT repo-wide.** Scoped to `apps/web2` (the only JS test
   workspace). The "`api.test.ts`" is `apps/web2/__tests__/api.test.ts`,
   not a root file. Exact root cause: `vitest@4.1.5` peer-wants
   `vite ^6||^7||^8` but pnpm (with `strict-peer-dependencies=false`)
   silently linked the only store vite, `vite@5.4.21` (a phantom
   transitive — nothing declares `vite` directly) → vitest 4 imports
   `vite/module-runner`, a subpath that does not exist before Vite 6 →
   `ERR_PACKAGE_PATH_NOT_EXPORTED: ./module-runner` at startup. No
   structural Next/vite conflict (Next 15.5 = webpack/Turbopack, zero
   vite dep — hypothesis refuted).
2. **`fred-liveness` / `data_integrity` are PYTHON** (`apps/api/tests/
test_fred_liveness_check.py`, `test_data_pool_data_integrity.py`) —
   already gated by the existing `python` CI job (`ci.yml` pytest matrix
   incl. `apps/api`). The memory note conflated JS and Python tests; not
   in this round's JS scope (no scope-creep into a Python-CI change).
3. **The real autonomy-hardening value was a CI gap, not a local fix.**
   NO workflow ran web2 vitest at all (`ci.yml` Node job = lint /
   build / typecheck only). Fixing vite locally is half the job — the
   r91 `deriveVerdict` SSOT regression harness + the r96
   `deriveDataIntegrity` data-honesty SSOT were CI-invisible (the
   r91→r96 arc could silently drift). Completing the read/CI side IS
   the task (doctrine #1 "half-built capability" analogue), not creep.

## ADR-before-code decision — NO new ADR (doctrine #9)

ADR-099 §Tier-3 ("autonomy hardening") + `docs/decisions/README.md:86`
("Update the index above") are already the governing spec. r89/r90/r91
precedent: hygiene flags addressed without an ADR; r91 SESSION_LOG
explicitly reserved the back-fill as "a dedicated round". A redundant
ADR would violate doctrine #9. Instead — honest immutable-append:
ADR-099 §T3.2:154 carried NO DONE annotation despite r93→r96 closing
the silent-skip chain end-to-end (a real 4-round doctrinal-drift gap
R59 surfaced — same class as the stale README index). Appended a dated
`[r93→r97 DONE]` marker mirroring the existing §T3.1 `[r92 DONE]`
pattern (append, never rewrite history).

## What shipped (5 modified + 1 new ; one coherent causally-chained increment)

- **`apps/web2/package.json`** — `"vite": "^7.0.0"` added to
  devDependencies (alphabetical, between `typescript` and `vitest`).
  `pnpm install` → `pnpm-lock.yaml` regenerated. Lockfile diff verified
  **scoped**: `vite@5.4.21 → vite@7.3.3` + the embedded pnpm peer-hash
  rewrites in the vitest-ecosystem keys only (the 332-line churn is
  semantically ONE swap — the "churn outside vite/esbuild/rollup"
  filter returned EMPTY: zero unrelated package re-resolution).
- **NEW `apps/web2/__tests__/dataIntegrity.test.ts`** — first automated
  vitest harness for the r96 `lib/dataIntegrity.ts` data-honesty SSOT
  (`deriveDataIntegrity`), authored against the REAL module shape +
  the real `api.ts DegradedInput` interface (R59'd, not guessed).
  4 describe blocks: (1) tri-state binding contract incl. the verbatim
  `untracked` honesty literal + `untracked !== all_fresh` (the exact
  r96 distinctness assertion) + 3-pairwise-distinct ; (2) degraded-row
  mapping fidelity + FR singular/plural grammar + the documented
  defensive status-map fail-safe ; (3) count/rows invariants ; (4) a
  web2-local ADR-017 BUY/SELL canary over every rendered string.
- **`.github/workflows/ci.yml`** — NEW step `pnpm --filter @ichor/web2
test` in the Node job after typecheck (the SSOT harnesses now gate
  CI) + corrected the stale `apps/web` job comment (retired 2026-05-06)
  - job name `… + test`.
- **`docs/decisions/README.md`** — `## Index` back-filled 28 rows
  ADR-077→104 (stale since ADR-076 ; filenames citation-gated via
  `git ls-files` = 90 ADR files, all 28 + the 5 corrected hrefs
  verified-present, nothing >104) + corrected 5 pre-existing broken
  hrefs (010/035/036/038/040 — same table, same hygiene pass, not
  creep). ADR-098 + ADR-099 rendered **`Proposed`** (NOT rounded to
  Accepted — calibrated honesty, lesson #11 ; the coarse single-word
  Status column ; 098's full "PROPOSED-CORRECTED" nuance lives in the
  ADR file itself).
- **`docs/decisions/ADR-099-…md`** — §T3.2 dated `[r93→r97 DONE]`
  annotation (r93 ADR-103 runtime surface / r94 ADR-092 §r94
  recalibration / r95 ADR-104 persist / r96 ADR-104 §Implementation
  badge / r97 CI-gated the SSOT harnesses — r97's contribution honestly
  narrowed to CI-enforcement, NOT substantive chain work).

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE commit on the full diff. **0 RED / 1 YELLOW-1
(advisory, no code fix required) / GREEN-on-rest. Mergeable.**

- **A (test vs ADR-104 §Cross-endpoint) GREEN** — the core invariant
  `null→untracked must never read healthy` is pinned 3 ways
  (verbatim honesty literal + no-`à jour` + no-`fraîches`) ; a
  `null→all_fresh` or warning-drop regression fails loud. `untracked
!== all_fresh` double-pinned. ADR-017 canary adequate.
- **B (index honesty) GREEN** — independent spot-check of 8 rows: all
  titles/statuses/dates/filenames faithful ; 098/099 honestly
  `Proposed` ; all 5 corrected hrefs resolve to real files.
- **C (ADR-099 over-claim) GREEN** — annotation precise; r97 scoped to
  CI-enforcement only, not over-claimed as substantive chain work
  (lesson #11 satisfied).
- **D (scope/Voie D/ADR-017) GREEN** — one causally-chained increment;
  5-href fix legitimately in-scope (ADR-104:225-226 pre-reserved this
  exact back-fill round); `vite` dev-only (no runtime, no Anthropic
  SDK); test is a deterministic provenance assertion with a BUY/SELL
  canary.
- **YELLOW-1 APPLIED (honest scope-disclosure, no code change):** the
  harness guards the SSOT's tri-state honesty but, by construction,
  CANNOT guard the §Cross-endpoint clause "consume ONLY the card
  `/v1/sessions` field, NEVER fall back to `/v1/data-pool`" — that
  binding lives in `app/briefing/[asset]/page.tsx` wiring, not in the
  provenance-agnostic `deriveDataIntegrity` (which only receives a
  `DegradedInput[] | null` and cannot know provenance). This is an
  inherent and correct test-scope limit. **Applied** = stated
  explicitly here + in the pickup (do NOT imply full-contract
  coverage) ; flagged as a candidate future page-wiring integration
  test. No pre-merge fix required (advisory).

## Verification (3-witness equivalent for a CI/docs-hygiene round)

This round ships NO Hetzner-deployable behaviour change (CI-only,
explicitly N/A per the default). The "marche exactement" ground truth
for this round type is the harness actually running green under the CI
tool, not an SSH:

1. **Witness A — static/CI gate (the core proof):** from the worktree,
   `pnpm --filter @ichor/web2 test` → **vitest v4.1.5 : 5 test files
   passed (5), 68 tests passed (68)** (was a hard
   `ERR_PACKAGE_PATH_NOT_EXPORTED` startup crash before — vitest ran
   for the first time repo-wide). `pnpm --filter @ichor/web2 typecheck`
   → `tsc --noEmit` exit 0 (a first run surfaced 4 `TS2532
noUncheckedIndexedAccess` in the new test on `rows[0].x` accesses —
   self-caught, fixed TS-safe + lint-safe via a full-row `toEqual` +
   optional-chaining `?.`, NOT a non-null `!` the codebase doesn't use
   ; clean re-run). `pnpm --filter @ichor/web2 lint` → `eslint .
--max-warnings 0` exit 0. doctrine-#4: `pnpm --filter @ichor/web2`
   resolves the workspace in the worktree.
2. **Witness B — lockfile-scope verification:** `git diff
pnpm-lock.yaml` proven scoped to the vite 5→7 swap + its embedded
   peer-hash rewrites only (no unrelated re-resolution) → CI's
   `pnpm install --frozen-lockfile` will resolve identically.
3. **Witness C — citation-gated index correctness + independent
   audit:** every ADR filename/date back-filled was verified by
   `git ls-files` (tool-output, not memory) + the per-file `**Date**`
   grep ; ichor-trader independently re-spot-checked 8 rows + the 5
   corrected hrefs against the real files = honest, no
   misrepresentation.

## Flagged residuals (NOT fixed — scope discipline)

- **§Cross-endpoint no-sidecar clause is NOT automated-test-guarded**
  (ichor-trader YELLOW-1, honestly disclosed) — it remains ADR-prose +
  the r96 page diff guarded. Candidate: a future `page.tsx` wiring
  integration test (out of this SSOT-unit round's scope).
- **`api.test.ts` / the other 3 web2 tests now gate CI** — they were
  pre-existing and pass under vitest@4+vite@7 (no behavioural change ;
  this round only unblocked + wired them).
- Carried forward (r91→r96, now partly closed): the vitest/vite skew is
  **fixed** ; README index back-fill **done** ; remaining Tier-3:
  cron 365d/yr holiday-gate (HIGH blast-radius — register-cron/systemd
  2026-05-04 class, PRUDENCE + R59 + infra-auditor) ; GBP Driver-3
  (`IR3TIB01GBM156N` ingestion + R53 prod-DB liveness first,
  chicken-egg multi-round) ; Pass-6 occasional ADR-017-token retry
  (guard HELD) ; Dependabot 3 main vulns (r49 baseline) ; KeyLevelsPanel
  $5 polymarket joke market (backend data-quality round) ; MEMORY.md
  > cap consolidation. Then Tier 4 premium UI.

## Process lessons (durable)

- **R59 disentangles conflated memory (doctrine #3 reshapes design).**
  The carried flag conflated JS-vitest with Python-pytest and asserted
  "repo-wide" — R59 file:line proved web2-scoped + a precise phantom
  peer-major root cause. Acting on the memory note would have mis-sized
  the round (root pnpm.overrides instead of a 1-line web2 devDep).
- **"vitest pre-broken = flag NON fix" (doctrine #8) means flag in a
  FEATURE round — THIS dedicated hygiene round IS where it gets
  fixed.** Not scope-creep: it is its own pre-reserved round
  (ADR-104:225-226). The distinction is the round's identity, not the
  change's nature.
- **A CI/docs-hygiene round's ground-truth is the green harness run,
  not a manufactured SSH-deploy-verify.** Calibrated honesty about
  round type — don't invent a deploy-verify step that does not apply
  (mirror of r96's "run the project gate, separate the harness").
- **ichor-trader catches an inherent test-scope boundary even at
  0 RED.** The no-sidecar clause is page-wiring, not SSOT — stating it
  explicitly (not implying full-contract coverage) is the lesson-#11
  honest-scope move, applied in-doc.

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening continues**
— R59 first, pick highest value/effort: cron 365d/yr holiday-gate
(HIGH blast-radius — register-cron/systemd 2026-05-04 class, PRUDENCE +
R59 + infra-auditor + ichor-trader, reversible <30s, ONE consolidated
SSH ; the holiday/weekend logic already exists `services/market_session.py`
r78 + `/v1/calendar/session-status` — only the card-gen GATE on it is
missing) ; or GBP Driver-3 (`IR3TIB01GBM156N` ingestion + R53 prod-DB
liveness first — chicken-egg, multi-round) ; or the §Cross-endpoint
no-sidecar page-wiring integration test (the YELLOW-1 follow-up). Then
Tier 4 premium UI. The next `continue` executes this default unless
Eliot pivots.

**Session depth:** r97 = round 1 of a fresh post-/clear session — NOT
deep ; no /clear/handoff needed. pickup v26 + SESSION_LOG r95 + r96 +
this r97 are the current resume anchor (current through r97).
