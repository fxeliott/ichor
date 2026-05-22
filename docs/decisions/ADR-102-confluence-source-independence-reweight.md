# ADR-102: Confluence re-weighted by source independence (fix the overconfidence trap)

**Status**: **Accepted** (round-91, 2026-05-17) — implements the already-**Accepted**
[ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §Tier 2.2 ("Confluence
re-weighted by source independence (fix overconfidence trap)", motivated at ADR-099 §"Confluence
= unweighted 2–3 vote tally → correlated-evidence overconfidence"). Thin per-feature ADR under
Eliot's standing full-autonomy delegation + the per-round default-Option contract (doctrine #10).
Implementation shipped same round (`apps/web2/lib/verdict.ts` `deriveVerdict` confluence block +
`apps/web2/__tests__/verdict.test.ts`, the first automated verdict regression harness).

**Date**: 2026-05-17

**Supersedes**: none

**Extends**: [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §T2.2 (the
enumerated task), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (no BUY/SELL —
the re-worded confluence strings stay environmental/analytical).

**Related**: r70/r71 deriveVerdict synthesis architecture (governed under ADR-099, no
standalone ADR) ; ADR-099 §T2.1 net-exposure (r83 `computeNetExposure`, unaffected — it
consumes `.bias.tone`, never `.confluence`).

## Context

`deriveVerdict` (the deterministic pre-session synthesis SSOT, `apps/web2/lib/verdict.ts`,
consumed by the cockpit `VerdictRow` and the deep-dive `VerdictBanner`) classifies a
`confluence` VerdictPart by an **unweighted vote** of up to 3 signals:
`biasSign` (Pass-2 `bias_direction`), `skewSign` (Pass-6 scenario distribution skew),
and `contrarian` (MyFXBook retail positioning). The old rule:
`allBull/allBear = directional.length >= 2 && all same` → label "signaux alignés", detail
"…pointent dans le même sens — **haute confluence**".

**The flaw (ADR-099 §T2.2 "overconfidence trap"):** `biasSign` and `skewSign` are BOTH
produced by the SAME Claude 4-pass analysis of the SAME card — the Pass-6 scenario
distribution is conditioned on the same regime/thesis that drives the Pass-2
`bias_direction`. Their agreement is **internal consistency** (expected), NOT **independent
corroboration**. So two correlated signals alone (no retail input, e.g. EVERY index —
SPX500/NAS100 have `myfxPair === null` so no retail source) triggered "≥2 aligned → haute
confluence". That over-states confidence: it is one analytical read echoed twice, presented
to the trader as strong multi-signal confluence. This is the same calibrated-honesty failure
class as the r84 pocket-skill badge and r89 themed-source fixes.

The MyFXBook retail `contrarian` tilt is the only signal **structurally independent** of the
Claude analysis (external market-positioning data, not LLM-derived) — and it is **absent for
indices** by construction.

## Decision

Re-weight `confluence` by **source independence**. Collapse the two Claude-derived signals
into ONE _Claude-analysis vote_; reserve high confluence for genuine cross-source
corroboration by the independent retail source.

- **`claudeVote`** = directional read of the Claude analysis: if `biasSign` and `skewSign`
  are both directional and agree → that direction (internally coherent); if they disagree →
  `biasSign` (the primary Pass-2 read anchors) with `claudeCoherent = false`; if only one is
  directional → that one; else neutral. **`biasSign`/`skewSign`/`asymCoherent` are READ as
  copies, never mutated** (they also feed the `confiance` field — which MUST stay
  byte-identical).
- **`indepVote`** = the retail `contrarian` tilt mapped to bull/bear/neutral.
  **`indepAvailable = myfxPair !== null`** (false for indices → no independent source).
- Classification:
  - `claudeVote` neutral → **"confluence partielle"** (neutral) — no directional read.
  - independent source present, directional, AND agrees with `claudeVote` → **"signaux
    alignés"** (bull/bear) — genuine cross-source corroboration = the only true high
    confluence.
  - independent source present, directional, AND opposes `claudeVote` → **"signaux en
    conflit"** (warn) — genuine cross-source divergence, prudence.
  - `claudeVote` directional but `!claudeCoherent` (Pass-2 vs Pass-6 disagree) + no
    confirming independent source → **"source unique"** (neutral) — internal incoherence,
    low confidence.
  - `claudeVote` directional, Pass-2/Pass-6 coherent, but NO independent confirmation
    (retail neutral, or index) → **"source unique"** (neutral) — _the key honesty
    downgrade_: was "haute confluence", now correctly "confluence non-indépendante :
    Pass-2 et Pass-6 partagent la même origine analytique, pas une corroboration croisée".

Only the `confluence` VerdictPart changes. Every other `VerdictSummary` field (`bias`,
`conviction`, `regimeLabel`, `caractere`, `confiance`, `watch`) is computed before the
confluence block and is **byte-identical by construction**. ADR-017: the new strings are
analytical/environmental ("lecture Claude", "source indépendante", "prudence
interprétative", "corroboration croisée") — no BUY/SELL/imperative/sizing.

## Acceptance criteria

1. `deriveVerdict` confluence re-weight implemented in `verdict.ts`; `biasSign`/`skewSign`/
   `asymCoherent` untouched (build the weighting from copies).
2. **First automated verdict regression harness** `apps/web2/__tests__/verdict.test.ts`
   (vitest): (a) every non-`confluence` `VerdictSummary` field byte-identical across a
   battery of representative cards (automates the r71 manual invariant); (b) the new
   confluence cases (cross-source confirm → "signaux alignés"; cross-source oppose →
   "signaux en conflit"; Claude-only-aligned → "source unique" NOT "signaux alignés", the
   downgrade; index always "source unique"/partial, never high); (c) a web2-local ADR-017
   canary: `confluence.detail` matches none of `/\b(BUY|SELL|LONG NOW|SHORT NOW|TP\d|SL\d|
ENTRY \d)\b/i`.
3. `tsc --noEmit` + `eslint --max-warnings 0` clean.
4. Empirical: deployed via `redeploy-web2.sh`; cockpit `VerdictRow` chip + deep-dive
   `VerdictBanner` render the re-weighted confluence consistently with real prod data;
   `computeNetExposure`/NetExposureLens visibly unchanged (uses `.bias.tone`).

## Reversibility

Single-file change to `verdict.ts` (one block) + one new test file + this ADR. No backend,
no migration, no FRED. `git revert <commit>` fully reverses it; `redeploy-web2.sh rollback`
reverses the deploy < 30 s. `verdict.ts` is the SSOT but the change is confined to the
`confluence` branch — both presentations consume the same function, so they cannot diverge.

## Consequences

### Positive

- **Calibrated honesty restored**: "haute confluence" now means genuine independent
  cross-source corroboration; correlated Claude-only agreement is honestly labelled. Indices
  (no retail source) can no longer show spurious "haute confluence". Directly serves "calibre
  la prise de risque" / "ne pas surévaluer".
- **First automated verdict regression harness** — the r71 byte-identical invariant was a
  manual R59 check; it is now mechanised (hardening, not just this round).
- ADR-099 §T2.2 closed; net-exposure (T2.1) provably unaffected.

### Negative

- Many cards that previously read "signaux alignés / haute confluence" (esp. all indices,
  and FX pairs with neutral retail) will now read "source unique". This is the intended
  correction, not a regression — but it is a visible change to the cockpit/deep-dive for the
  trader, who must understand "source unique" = lower-confidence single-origin read.

### Neutral

- Label vocabulary changes ("source unique" is new); no consumer switches on literal label
  strings (verified r91 navigator) — purely display.

## Sources

- ADR-099 §T2.2 (the enumerated task + "correlated-evidence overconfidence" motivation).
- r91 navigator consumer/test/ADR map (2 consumers, no existing verdict test, ADR-099
  governance, ADR-102 next free number).
