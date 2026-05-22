# SESSION_LOG 2026-05-18 — r107 EXECUTION

**ADR-099 §D-3 Tier 4 hygiene — app-wide Tailwind v4 `[var(--*)]`
token-resolution fix.** Branch `claude/friendly-fermi-2fff71`. The r106
dedicated-task flag executed. Voie D + ADR-017 held; web2-only additive
deploy; ZERO backend / ZERO migration (alembic still 0050); NO new ADR
(doctrine #9 — dated ADR-099 §Implementation(r107) append).

## Root cause (confirmed, not assumed)

`tailwindcss 4.2.4`, CSS-first (`@import "tailwindcss"` +
`@tailwindcss/postcss`, no JS config). Authoritative: official v4 upgrade
guide via context7 `/tailwindlabs/tailwindcss.com` — _"In v3, CSS
variables could be used as arbitrary values without the `var()`
function … v4 changes the syntax to use parentheses … `bg-[--brand-color]`
should be updated to `bg-(--brand-color)`"_. The codebase was authored
v3-style ; v4 dropped the implicit `var()` wrap, so `prefix-[--color-*]`
emits NO rule → elements fell back to the cascade (mostly inherited
`body` slate-100, transparent bg, absent border). Pre-existing,
codebase-wide, latent (subtle on the dark theme). Surfaced by the r106
heat-strip witness, NOT introduced by r106.

## BEFORE witness (deployed, empirical)

`https://latino-superintendent-restoration-dealtime.trycloudflare.com/briefing/EUR_USD`:

- `text-[--color-text-muted]` "Marché américain ouvert" → computed
  `oklch(0.9425 0.0111 243.66)` = slate-100 inherit, NOT muted. BROKEN.
- `text-[--color-text-secondary]` "GBP/USD" → slate-100. BROKEN.
- `bg-[--color-bg-surface]/40` NY pill → `rgba(0,0,0,0)`. BROKEN.
- `text-[var(--color-text-secondary)]` (the pre-existing _working_ form)
  → `oklch(0.7446 0.0213 257.49)` = exact token. **In-build proof the
  `[var(--*)]` form works on this exact build.**
- Live DOM: 497 broken `text-[--color-`, 34 working `text-[var(--color-`,
  192 broken `bg-[--color-`.

## What shipped

- **Codemod** `prefix-[--color-X]` → `prefix-[var(--color-X)]` —
  `perl -i -pe 's/-\[(--color-[a-z0-9-]+)\]/-[var($1)]/g'` over 21 `.tsx`
  files (`app/briefing/`, `components/briefing/`). 494 occurrences, 10
  prefixes (`text-` 283 · `bg-` 97 · `border-` 84 · `border-l-` 10 ·
  `divide-` 9 · `ring-` 4 · `via-`/`to-`/`from-` 2 · `shadow-` 1), 44
  distinct `--color-*` tokens. PRE 494 broken/0 working → POST **0/494/0
  double-wrap**. `/NN` opacity modifiers preserved outside the bracket
  (now resolve via `color-mix`). `--color-`-anchored regex → zero
  collateral on JS / non-color tokens / already-`[var()]` / star-glob
  prose.
- **Decision `[var(--*)]` over v4 paren `(--*)`** — byte-identical
  compiled CSS ; `[var(--x)]` is the form empirically proven in THIS
  build (the witnessed element), converges the codebase to ONE form,
  zero new syntax. Config-shim rejected (v4 removed auto-var by design,
  no restore flag) ; base-CSS rejected (defeats the token system).
- **`BriefingHeader.tsx:88`** — dropped `/50` on the `·` separator (the
  one element the restore made too-faint ; ui-designer Important #1).
- **3 prose corrections** — `globals.css` opacity-modifier comment (now
  TRUE + r107 pointer) + tree-shake example `[--…]`→`[var(--…)]` ;
  `CorrelationsStrip.tsx` r106 note past-tensed + the codemod-touched
  glyph comment de-falsified. Exhaustive scan → no other stale prose.
- **`docs/decisions/ADR-099-…md`** — dated `## Implementation (r107,
2026-05-18)` appended (NO new ADR, doctrine #9).

## Reviews (3 mandatory, parallel, consolidated 1-pass — all applied)

- **ichor-trader R28: 0 RED / 0 YELLOW-blocker, GREEN.** ADR-017 intact,
  Voie D/ADR-023 N/A, doctrine #9/anti-doublon/#3 verified, zero
  collateral. Positive finding: the codemod _corrects_ a latent
  trading-surface degradation (`VerdictBanner` bull/bear/warn/conviction
  were broken no-ops inheriting slate-100 → now emerald/red correct). One
  non-blocking YELLOW = deferred-flag the pre-existing border-α §1.4.11.
- **ui-designer: PROCEED.** Coherent 3-tier hierarchy restored,
  consistently applied, no value de-emphasised, no bg-as-text misuse,
  layered depth coherent. 1 Important applied (BriefingHeader:88) ;
  remainder = pre-existing deferred items.
- **accessibility-reviewer (MANDATORY): PASS, 0 MUST-FIX / 0 SHOULD-FIX.**
  Full 1.4.3 matrix. Worst REAL combo `text-muted` on `bg-elevated/40`
  hover = **5.01:1** (≥4.5:1). Key insight: `/40` pills composite toward
  the darker `bg-base` → RAISE effective contrast ; the opaque-bg
  theoretical floor (4.69:1) is not realized (0 opaque `bg-elevated` in
  scope). 1.4.11 border-α = ADVISORY/pre-existing/not-load-bearing.
  Zero invisible flips. 1.4.1 no regression.

## Honest non-atomic scope (lesson #11, anti-scope-creep)

r107 = the token-resolution fix + the single restore-introduced faintness
(BriefingHeader:88) ONLY. Deferred, flagged not silently fixed:
(i) WCAG §1.4.11 border-α <3:1 — the pre-existing `globals.css` §5
recalibration, now visually live but not load-bearing in changed
surfaces ; (ii) SentimentPanel↔ScenariosPanel empty-state tier
inconsistency ; (iii) NarrativeBlocks `/10` warn-chip faint pill
(WCAG-OK). Each its own future increment.

## AFTER witness — GREEN (deployed, real live data, 3 routes)

Same stable URL (tunnel not restarted). Deploy: local=200 public=200.

- **`/briefing/EUR_USD`** — SAME element as BEFORE, "Marché américain
  ouvert": `text-[--color-text-muted]`→`text-[var(--color-text-muted)]`,
  `oklch(0.9425…)` → **`oklch(0.6099 0.0243 256.77)` = muted exact** ;
  secondary → **`oklch(0.7446 0.0213 257.49)` exact** ; NY pill bg
  `rgba(0,0,0,0)` → **`oklab(0.1831 −0.00356 −0.03069 / 0.4)`**. DOM
  broken 497→**0**, working text-var 34→**531**.
- **`/briefing`** cockpit (different route): muted `0.6099`, secondary
  `0.7446`, **`text-[var(--color-bull)]` `oklch(0.7729 0.1535 163.22)`
  emerald exact** (trading-surface semantic restored) ; 0 broken.
- **`/briefing/XAU_USD`** (2nd asset): muted/secondary exact, bg-surface
  `oklab …/0.4`, **0 broken / 759 working**.
- **Console**: cold first-load (just-restarted service) = pre-existing
  `404 favicon.ico` + a transient `link-preload-not-used` CSS warning ;
  warm reload = **0 errors / 0 warnings**. The warning empirically
  confirmed a cold-server-restart artifact (a class-string codemod
  cannot affect preload timing ; the CSS content-hash change is the
  EXPECTED recompiled-Tailwind output) — verified, not asserted.
- Full-page screenshots: `r107-after-briefing-{EUR_USD,index,XAU_USD}`
  confirm the restored premium 3-tier hierarchy gestalt.

## Verification numbers

- Codemod: PRE 494/0 → POST 0/494/0 ; residual broken web2-wide = **0**.
- Build gate (post-prettier shape, doctrine #14): `tsc` 0 · `eslint
--max-warnings 0` 0 · vitest **7 files / 95 tests** (zero regression vs
  r106) · `next build` OK.
- AFTER: 3 routes, every probed token resolves to its exact OKLCH value,
  0 broken in DOM, 0 console errors/warnings on settled load.

## NEW lessons

- A v3→v4 framework migration can leave a SILENT, codebase-wide class
  regression that passes every build gate (tsc/eslint/vitest/next build
  ALL green) and is only caught by a deployed computed-style witness —
  the contract is what the build APPLIES, not what the class string
  says (the r104 tree-shake lesson, one form-syntax layer up).
- When two equivalent fix forms exist, prefer the one already
  empirically proven in THIS exact build over the one the docs
  recommend — convergence to a single in-build-proven form is lower
  risk than adopting docs-idiomatic-but-unproven syntax.
- A new colour/encoding round is the highest-yield probe for latent
  token/class-form defects subtle dark-on-dark text had hidden for
  rounds.

Voie D + ADR-017 held; additive web2-only deploy; zero backend / zero
migration; alembic 0050; no new ADR (doctrine #9).
