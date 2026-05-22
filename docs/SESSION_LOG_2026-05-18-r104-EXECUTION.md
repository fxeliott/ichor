# SESSION_LOG 2026-05-18 — r104 EXECUTION (ADR-099 Tier 4, increment 1 — OKLCH 3-layer design-token migration ; witness-driven, zero-regression)

**Round type:** ADR-099 §D-3 Tier 4 (premium UI), the r103-close binding
default (no pivot, doctrine #10). Honest non-atomic split: r104 = the
**OKLCH 3-layer token foundation only**; SSR SVG microchart primitives =
r105, T4.2 = r106, T4.3 = r107.

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API.** Frontend
web2-only, additive Hetzner deploy, **ZERO backend / ZERO migration**.
ADR-017 N/A by construction (CSS custom properties) + empirically clean on
the live render. Voie D held.

## R59 reshaped the scope (doctrine #3 — caught before any code)

Two parallel R59 sub-agents (ichor-navigator web2 code-map + researcher
7-SESSION_LOG digest) + direct read of `apps/web2/app/globals.css` +
context7 Tailwind v4 + a one-consolidated read-only SSH dumping the real
prod OpenAPI/endpoint shapes. Findings that **reshaped the plan**:

- `globals.css:51-52` (pre-r104) carried a verbatim self-flagged deferral
  _"Full OKLCH palette migration deferred — needs a dedicated session with
  visual diff review per route, not a code-only flip."_ r104 **is** that
  session.
- `tabular-nums` (`.font-mono,code,[data-numeric]` `tnum/zero`), dark-default
  (single dark surface system), and motion tokens (`--duration-*`/`--ease-*`)
  were **already shipped** pre-r104. Part of the T4.1 wording, NOT
  re-implemented, **NOT claimed as r104 work** (lesson #11). The genuine
  T4.1 increment-1 gap = the OKLCH 3-layer restructure only.

## What r104 implemented

`apps/web2/app/globals.css` palette → 3-layer OKLCH:

- **Layer 1 — primitives** (`:root --p-<family>-<step>`): raw semantic-free
  OKLCH ramp; suffix = **ordinal Tailwind-style step (50…950), DECOUPLED
  from literal lightness** (ui-designer r104 — re-tune changes value only,
  never the name; no rename cascade).
- **Layer 2 — semantic** (plain `@theme`): the existing `--color-*` names
  **byte-identical**, value `hex → var(--p-*)`. Borders/overlay = direct
  `oklch(L C H / α)` (lossless alpha-of-primitive).
- **Layer 3 — compat aliases** (plain `@theme`): unchanged var-refs.

Method = each former hex/rgba → its **exact CSS Color 4 OKLCH equivalent**
(computed, not guessed; venv Python). Round-trip sRGB→OKLCH→sRGB at the
shipped 4-dp precision = **ΔsRGB=0, ΔA=0 on all 22 colours / 28 semantic
tokens** (name-agnostic parser, re-run on every shape change). spacing /
radius / shadow / motion / z + ALL base CSS (regime tints / selection /
scrollbar / focus / reduced-motion) **byte-identical** (scope discipline).

## ADR-before-code (doctrine #9 — no new ADR)

ADR-099 §D-3 Tier 4 **is** the spec. Appended dated `## Implementation
(r104, 2026-05-18)` + inline `[r104 …]` annotation on the T4.1 bullet
(immutable-append, §T3.1/§T3.2/ADR-104§Impl(r96)/ADR-105§Impl(r99,r100)
precedent). Tailwind v4 `oklch()`-in-`@theme` + var-referencing confirmed
canonical via context7 (`/tailwindlabs/tailwindcss.com`).

## Review trio (mandated, UI round) — 0 RED / 0 MUST-FIX, ALL findings applied pre-merge

- **ichor-trader R28**: ADR-017 GREEN, framework axes N/A-confirmed,
  over-claim GREEN (under-claimed). **2 doc-only YELLOW (cross-file drift
  MY change introduced)** — both applied: (1) de-pinned the stale
  `globals.css:51-52` self-citation in §Impl → past-tense, non-line-pinned;
  (2) `ROADMAP_2026-05-06.md:518` `[ ]` → `[x] [r104 DONE]` (r78/r92/r93
  precedent; dead `globals.css:50-52` cite removed). (`:520` left open =
  honest, r104 ≠ color-mix-for-states; `SESSION_LOG_2026-05-07:177` NOT
  edited — immutable per-day record, no stale cite, editing it would
  violate no-rewrite-history.)
- **ui-designer**: "sound, ship it". 6 findings applied: #1 (highest-
  leverage) primitive ordinal-step rename + value-decoupling comment; #2
  severity-incoherent / #3 glow-shadow SSOT-dedup orphan / #6 r105
  `--p-chart-*` → deferred-residual list (globals.css header §1–§6 +
  ADR-099 §Impl, kept consistent); #4 depth-variant-asymmetry-is-intentional
  / #5 overlay-border relative-color future-cleanup → one-line comments.
- **accessibility-reviewer** WCAG 2.2 AA: **crux claim rigorously
  confirmed** — exact OKLCH equivalence (ΔsRGB=0) preserves every contrast
  ratio identically by definition (WCAG luminance is a pure function of
  sRGB; OKLCH never an input). Spot-checks text-muted 5.33:1 / primary
  17.08:1 / focus-ring 10.50:1 PASS. **ADVISORY-1 applied**: the
  pre-existing border-α comment ("≈3.0:1/4.5:1") is numerically false (real
  composited 1.84:1 / 2.87:1 / 4.98:1) — r104 carries the values
  byte-identical (ΔsRGB=0, NOT an r104 regression) and **corrected the
  comment** to the true ratios + flagged the α recalibration as a deferred
  residual (lesson #11 — never re-affirm a false WCAG claim). ADV-2
  (no forced-colors) / ADV-3 → backlog notes.

Re-verified the full consolidated shape: regression ΔsRGB=0 28/28 GREEN +
build gate GREEN (tsc / eslint --max-warnings 0 / vitest 5·68 / `next build`).

## Deploy-witness investigation (the substance of the round — honest, lesson #1/#2/#11/#12/#13, process>outcome)

Deployed via vetted additive `redeploy-web2.sh` (server-side build, restart
`ichor-web2` only → LIVE URL stable r75, legacy 3030 untouched). Real-prod
Playwright witness on the **deployed** `/briefing` (Tier-0 public-by-design
= the actual artifact, stronger than a local re-render):

1. **The witness caught what 4 green gates hid.** Green build + HTTP 200 +
   Python ΔsRGB=0 + browser `getComputedStyle` chain-resolution ALL passed,
   yet a **canvas sRGB readback + `:root` enumeration** found **4 semantic
   tokens absent from the compiled `:root`**: `--color-ichor-deep`,
   `--color-bull-deep`, `--color-bear-deep`, `--color-accent-cobalt-deep`.
   _This is exactly why we witness — "marche exactement ≠ ça marche"._
2. **H1 = "`@theme inline` tree-shakes them"** → fixed (Layer 2/3 →
   plain `@theme`), re-deployed, re-witnessed → **same 4 still absent →
   H1 FALSIFIED** (did not act on the first hypothesis; verified it).
3. **H2 = "r104 regression"** → **decisive control** (doctrine #3, never
   act on a guess): backed up r104 `globals.css`, restored the pre-r104
   committed version (`git show HEAD:…`), built it, grepped the compiled
   CSS → the **identical 4 tokens absent in the pre-r104 build too**, while
   consumed var-refs (`--color-bg-deep`, `--color-accent-cobalt-bright`)
   present in both → **H2 FALSIFIED**; restored r104.
   _(First grep used the wrong `.next` path — even known-present controls
   showed "absent" → lesson #13 verification-script artifact, re-probed
   correctly at `.next/static/css/_.css`. Also: a cp1252 console crash on
the `Δ` glyph in the Python proof = same class of artifact, not a data
   defect.)\*
4. **VERIFIED root cause:** Tailwind v4's production build tree-shakes
   theme tokens with **zero references** — identical pre/post-r104 and in
   both `@theme` modes; the discriminant is **consumer-count**, not the
   migration. The 4 have **0 web2 consumers** (grep-proven). **NOT an
   r104 regression** — pre-existing, by-design, **zero functional impact**
   (nothing reads an unemitted var that nothing consumes; the first
   `[--color-bull-deep]` consumer auto-triggers emission).
5. **Disposition: ACCEPT.** `@theme static` (force-emit all) would ship
   dead CSS for 0-consumer tokens = the accumulation this project forbids
   (ui-designer: depth-variants on-demand by design). Plain `@theme` kept
   = exact pre-r104 structural fidelity (the H1 "fix" coincidentally
   landed on the correct pre-r104 structure). The false globals.css
   comment + ADR-099 §Impl were **corrected to the verified truth** (the
   investigation recorded honestly in ADR-099 §"Deploy-witness
   investigation", not papered over).

Net: r104 is **emission-neutral AND contrast-neutral** vs pre-r104 — the
exact same 24 consumed tokens emitted, now in OKLCH at ΔsRGB=0.

## Final state — proven by 5 independent witnesses (real deployed prod)

Final redeploy from the corrected committed source (deployed == committed,
ONE consolidated SSH, idempotent). Final witness, **correct success
criterion** (24/24 consumed exact; 4 zero-consumer absent = expected):

1. Python file-level: ΔsRGB=0, 28/28 semantic, 23/23 primitives.
2. Browser `getComputedStyle`: `--color-* → var(--p-*) → oklch()` chain
   resolves on deployed prod; body/H1 render the exact computed OKLCH.
3. **Canvas sRGB readback on real prod: ΔsRGB=0 for all 24 consumed
   opaque tokens** (browser-rasterized deployed OKLCH == pre-r104 hex
   byte); 0 unexpected-absent; the 4 zero-consumer absent as documented.
4. Visual screenshots both priority routes (`/briefing` cockpit +
   `/briefing/EUR_USD` detail, 60 sections incl. Volume SVG bull/bear) —
   styled, coherent, premium, pixel-faithful, no layout/fallback break.
5. Pre-r104 build comparison (the H2 control) — proves zero-regression.

Console: only error = pre-existing `404 favicon.ico` (unrelated to r104,
out of scope, non-blocking — lesson #13 triaged).

## Files changed (3 — exactly r104 scope)

- `apps/web2/app/globals.css` — 3-layer OKLCH migration + corrected
  comments (border-α true ratios, verified tree-shake explanation).
- `docs/decisions/ADR-099-…md` — inline `[r104]` + `## Implementation
(r104, 2026-05-18)` (incl. honest Deploy-witness investigation) +
  de-pin + Layer2/3 plain-`@theme` + deferred-residual list.
- `docs/ROADMAP_2026-05-06.md:518` — `[x] [r104 DONE]`.

## Lessons

- **NEW (r104):** a token system's _contract_ is **what the build emits**,
  not what the source defines — Tailwind v4 tree-shakes 0-reference theme
  tokens by design. The correct witness criterion is "all _consumed_
  tokens render exact", not "all _source_ tokens in `:root`". Using the
  wrong criterion produced a false "STILL-RED" before the pre-r104 control
  settled it.
- Reinforced #1/#2 (forecast≠preuve / shipped≠functional): 4 green gates
  passed; only the real-prod canvas witness caught the anomaly.
- Reinforced #13 (verification-script artifact ≠ data defect): triaged
  twice — the cp1252 `Δ` crash and the wrong-`.next`-path grep.
- Reinforced #3 (never act on a guess): 2 hypotheses formed, **both
  empirically falsified** via re-deploy + a decisive pre-r104 build
  control before the true cause was stated.
- Honest scope: 3 deploys this round (v1 initial / v2 H1-fix / v3
  final-from-corrected-source) — each warranted, ONE consolidated SSH
  each, not hammering; the investigation was the round's substance.

## Default sans pivot → r105

**ADR-099 Tier 4 increment 2 = SSR SVG microchart primitives** (sparkline /
probability ladder / correlation heat strip / regime timeline) — zero
charting dep, RSC-clean, add NEW `--p-chart-*` sequential/diverging ramps
(NOT overload the semantic accents). R59-first against the real
`build_data_pool`/card shapes. Then T4.2 (r106) uncertainty-always /
motion-as-function, T4.3 (r107) responsive.
