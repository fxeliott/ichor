# SESSION_LOG 2026-05-17 — r91 EXECUTION (ADR-099 §T2.2)

**Round type:** feature increment — ADR-099 **Tier 2 = confluence
re-weight by source independence** (the per-round default from the r90
SESSION_LOG / pickup v26). The **highest-blast-radius change in the
codebase**: it mutates the deterministic synthesis SSOT
(`apps/web2/lib/verdict.ts` `deriveVerdict`) consumed by 2 presentations
× 5 assets (cockpit `VerdictRow` + deep-dive `VerdictBanner`). Handled
under explicit PRUDENCE (ADR-avant-code + byte-identical regression
proof + ichor-trader review).

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(pure deterministic re-expression, Voie D). ADR-017 held — the
re-worded confluence strings are empirically `ADR-017 CLEAN` live on
prod (cockpit + deep-dives). Only the `confluence` VerdictPart changed;
every other `VerdictSummary` field byte-identical by construction.

## The flaw fixed (ADR-099 §T2.2 "overconfidence trap")

Old confluence: unweighted vote `[biasSign (Pass-2), skewSign (Pass-6),
contrarian (retail)]` → `allBull/allBear` on ≥2 aligned signals →
"signaux alignés / **haute confluence**". But `biasSign` and `skewSign`
are BOTH the SAME Claude 4-pass analysis of the SAME card (the Pass-6
scenario distribution is conditioned on the same regime/thesis driving
the Pass-2 bias) — their agreement is internal consistency, NOT
independent corroboration. So two correlated signals alone (every index
— SPX500/NAS100 — has NO retail source) triggered spurious "haute
confluence": one analytical read echoed twice, sold to the trader as
strong multi-signal confluence. Same calibrated-honesty failure class as
r84 (pocket-skill badge) and r89 (themed-source fix).

## What shipped (3 files, frontend SSOT)

- **NEW `docs/decisions/ADR-102-confluence-source-independence-reweight.md`**
  — thin ADR (Status: Accepted) implementing the already-Accepted
  ADR-099 §T2.2.
- **MOD `apps/web2/lib/verdict.ts`** — the `confluence` block only
  (~:193-259). `biasSign`/`skewSign`/`asymCoherent` are READ as copies,
  never mutated (they also feed `confiance` — which MUST stay
  byte-identical).
- **NEW `apps/web2/__tests__/verdict.test.ts`** — the **first automated
  verdict regression harness** (the r71 byte-identical invariant was a
  manual R59 check until now — this mechanises it).

**Model:** collapse Pass-2 `biasSign` + Pass-6 `skewSign` into one
`claudeVote` (agreement = expected internal consistency, not
corroboration; on bias≠skew the Pass-2 read anchors + `claudeCoherent=
false`). The MyFXBook retail `contrarian` is the only structurally
_independent_ source (`indepAvailable = myfxPair !== null` → false for
indices). Classification: `claudeVote` neutral → "confluence partielle";
independent source confirms `claudeVote` → "signaux alignés" (the ONLY
genuine high confluence); independent source opposes → "signaux en
conflit"; `claudeVote` directional but no independent confirm (retail
neutral OR index) → **"source unique (Claude seule)"** (the key honesty
downgrade — was "haute confluence"); Pass-2/Pass-6 incoherent + no
independent confirm → "source unique (Claude seule)" with "incohérence
interne" detail. ADR-017-safe analytical vocabulary throughout.

## R59 (before the SSOT mutation)

- `ichor-navigator` (read-only): exactly 2 consumers — cockpit
  `VerdictRow` (renders **only** `confluence.label`+`.tone` chip, NOT
  `.detail`) + deep-dive `VerdictBanner` (`.label`+`.detail`+`.tone`).
  No code switches on literal label strings (safe to re-word). NO
  existing verdict test. ADR-099 §T2.2 pre-sanctions the task.
  `computeNetExposure` (r83) consumes `.bias.tone` only → provably
  unaffected. I re-read the exact confluence block + both consumers
  myself (owning the SSOT change, not delegating understanding).

## ichor-trader proactive review (R28 — every YELLOW applied pre-merge)

**No RED.** Source-independence model economically/statistically SOUND
(P(skew|bias) ≫ P(skew) under shared latent — textbook correlated-
evidence trap; retail genuinely the only exogenous signal; no signal
lost — bias↔skew conflict still surfaces via `!claudeCoherent`).
**Byte-identity CONFIRMED** (confluence block reads biasSign/skewSign/
asymCoherent only; `confiance` computed before & unmutated). ADR-017
CLEAN. `claudeVote` Pass-2-anchor tie-break + `claudeCoherent` boolean
logic verified sound.

- **YELLOW-1 (label clarity in the label-only cockpit chip) — FIXED.**
  Bare "source unique" could read as "data missing". Renamed to
  **"source unique (Claude seule)"** (self-explanatory, ADR-017-clean);
  test assertions synced.
- **YELLOW-2 (missing test pin) — FIXED.** Added a test pinning the
  Pass-2-anchor tie-break where it is directionally observable
  (bias=long + Pass-6 bear + retail bullish → claudeVote anchors bull →
  "signaux alignés"). The anchor's direction was otherwise asserted
  nowhere.

## Verification (3-witness, directly OBSERVED — r88 honored)

1. **Static gate:** `tsc --noEmit` clean + `eslint --max-warnings 0`
   clean (twice, pre- and post-YELLOW).
2. **vitest is PRE-EXISTING-BROKEN in this worktree** —
   `ERR_PACKAGE_PATH_NOT_EXPORTED`: vitest@4.1.5 peer-requires vite
   `^6||^7||^8` but the installed vite lacks the `./module-runner`
   export. **The pre-existing `api.test.ts` fails identically** → a
   repo-wide lockfile/peer skew, NOT an r91 regression and NOT in a
   confluence round's scope (a lockfile mutation to fix repo test-infra
   would be scope creep). Per r88 ("can't-run ≠ proof") the harness
   logic was instead executed **directly** via Node type-stripping
   (`verdict.ts` is a pure module with type-only imports) →
   **ALL 35 assertions PASSED** (byte-identity on the canonical card +
   3-retail-variant invariance + all 7 confluence cases + the YELLOW-2
   Pass-2-anchor + the ADR-017 canary). Temp verifier deleted (doctrine
   #7, never commit scaffolding). The committed `verdict.test.ts` runs
   verbatim once the infra is fixed.
3. **Deploy + direct live observation:** `redeploy-web2.sh` (additive,
   r75 tunnel-stable), `local=200 public=200`, URL stable, legacy
   untouched. One consolidated SSH (internal :3031, zero exposure):
   - **Cockpit `/briefing`**: "signaux alignés" **absent** (no asset
     has independent retail confirming the Claude read with current
     prod data → none falsely "high" — honest); "signaux en conflit" +
     "source unique (Claude seule)" + "confluence partielle" present;
     **OLD "haute confluence" GONE**; **NetExposureLens present**
     (bias-driven — no regression).
   - **SPX500_USD / NAS100_USD** (indices, no retail): "source unique
     (Claude seule)" / "confluence partielle", **never "signaux
     alignés"** — the exact pre-r91 overconfidence bug structurally
     gone, observed live. ADR-017 CLEAN.
   - **EUR_USD**: "signaux en conflit" (real retail opposes the Claude
     read → genuine cross-source divergence surfaced). ADR-017 CLEAN.

## Flagged residuals (NOT fixed — scope discipline)

- **vitest infra pre-existing-broken** (vite/vitest peer skew,
  repo-wide, lockfile-level — fails for the pre-existing tests too).
  Fixing it = a lockfile-mutating infra round of its own, NOT r91.
  Backlog: a Tier-3 doc/infra-hygiene round (`pnpm` vite/vitest
  realignment) — then the committed `verdict.test.ts` runs in CI.
- **`docs/decisions/README.md` `## Index` stale since ADR-076**
  (2026-05-09): ADR-077..102 (26 ADRs incl. 092/099/100/101/102) are
  unindexed; the "update the index" step has been de-facto abandoned
  for 26 ADRs (r89/r90 shipped without touching it). Adding a lone
  ADR-102 row would be inconsistent noise — deliberately NOT done
  (matches precedent). Backlog: a dedicated doc-hygiene round to
  back-fill the index 077→102 in one consistent pass.
- Carried forward: deferred GBP Driver-3 (`IR3TIB01GBM156N`); the
  KeyLevelsPanel joke-market backend data-quality; Dependabot 3 main
  vulns (r49 baseline).

## Process lessons (durable)

- **Pre-existing broken test-infra ≠ a reason to ship unverified, and
  ≠ a reason to scope-creep a lockfile fix into a feature round.** When
  the runner is broken upstream, verify the logic _directly_ (a pure
  module is runnable via Node type-stripping) and flag the infra.
- **A documented convention can be de-facto dead** (the README index,
  abandoned 26 ADRs ago). R59 the _actual_ repo state before "following"
  a doc instruction; a lone consistent-looking entry in a long-stale
  index is misleading noise — flag the whole gap instead.
- **ichor-trader earns its keep on SSOT changes beyond doctrine** — it
  caught a display-clarity gap (YELLOW-1) and an untested tie-break
  (YELLOW-2), not just trading-invariant issues.

## Next

**Default sans pivot:** ADR-099 **Tier 2 continuation** — remaining
ichor-trader Tier-2 items / optional AAII equity-sentiment follow-up →
**Tier 3 autonomy hardening**: ADR-097 `fred_liveness_check.py` missing;
cron 365d/yr holiday-gate; COT-EUR silent-skip; GBP Driver-3
enrichment; **+ the two r91-flagged hygiene items (vitest/vite infra
realign so the verdict harness runs in CI ; README index back-fill
077→102)** → Tier 4 premium UI. R59 first; the next `continue` executes
this default unless Eliot pivots. **Session = 3 rounds post-/clear
(r89/r90/r91)** — approaching the checkpoint zone but not yet deep
(>~10); pickup v26 stays the current resume anchor, kept up to date this
round. No /clear needed yet.
