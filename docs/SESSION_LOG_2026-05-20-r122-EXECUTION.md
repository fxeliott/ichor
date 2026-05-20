# SESSION LOG — 2026-05-20 — r122 EXECUTION

> ADR-099 §D-3 **Tier 4 `/yield-curve` static-generation bypass** :
> `export const dynamic = "force-dynamic"` + `export const revalidate = 60`
> (page-level) + fetch-level `revalidate: 300 → 60` (mirror
> `/hourly-volatility/[asset]` house pattern). Closes the 5+ round
> recurring `/yield-curve` seed-stuck flag (r118/r119/r120/r121 SESSION_LOGs).
> ZERO change to the FALLBACK const itself (graceful-degradation safety
> net preserved per v40/v41 discipline). NO new ADR, NO new primitive,
> NO coord-math change, doctrine-#9 coord-math ledger UNCHANGED, ZERO
> backend/migration (alembic still 0050). **FOUR-LAYER meta-r110
> disproof recorded** — including the falsification of the orchestrator's
> OWN R59 sub-agent's "ISR cache TTL is the bug" hypothesis by the
> deployed witness (lesson #1 forecast≠proof applied at the META level :
> even the orchestrator's R59 conclusions are HYPOTHESES that the witness
> verifies or falsifies).

## Resume / ground-truth concordance (r116-lesson permanent discipline)

- `git -C friendly-fermi-2fff71` at r122-START: HEAD `05295e8` == `origin/claude/friendly-fermi-2fff71` (byte-equal, pushed) ; `origin/main` `1909ca0` ; **87 ahead** ; tree clean ; alembic 0050. Matches the r121-close state exactly.
- `git log -8` confirms r121 on top of r120/r119/r118/r117/r116b/r116a/r115/r114. No concurrent drift.
- **RE-GREP ADR-099 `^## Implementation (r1...` headers** : unique r104→r121, NO r122 yet, append point clean.
- PENDING grep = 2 hits at lines 2708 (r120) + 2738 (r121), BOTH = the v41-documented faux-positif (narrative descriptive "reconcile PENDING placeholders to MEASURED — _done HERE_"), NOT real placeholders. 0 real PENDING.

## R59 inspect-first — the menu-default is itself R59-subject (meta-r110→r122)

The r121-close menu offered (typography-reconcile, Eliot-preference-dependent → DEFER without signal), (B′) more-consumers (backend-first), and T4.2 muted-text recalibration. Eliot invoked `/maximum-mode + /ultrathink-this + sub-agents` for r122. Two parallel `researcher` R59 sub-agents + one SSH-consolidated API liveness probe + one Playwright deployed-state extraction surfaced a HIGHER-PRIORITY candidate not in the explicit menu : the **yield-curve seed-stuck data-honesty defect**.

### THE FOUR R59 LAYERS (meta-r110 four-fold)

1. **v40/v41 paste-prompt** said "the web2-SSR-seed condition is `/yield-curve`-SPECIFIC (a hardcoded `FALLBACK` const), R59-DISPROVED at r120 + r121 as a universal SSR gate. Do NOT re-flag." — **CORRECT** (r122 does NOT remove the FALLBACK ; the FALLBACK stays as a graceful-degradation safety net for genuine API-down scenarios).

2. **The r118/r119/r120/r121 SESSION_LOGs** framed the issue as "the page silently renders seed" — **R59-REFRAMED by the 1st sub-agent** : the page ALREADY does `isLive(live) ? live : FALLBACK` (`page.tsx:42-44`, prefers live, falls back ONLY on real `null`) ; the page LOGIC is correct.

3. **The orchestrator's pre-write hypothesis** ("yield-curve-live-wire might be backend-dependent / Tier 0.2 / named-tunnel-gated") was **R59-DISPROVED** by the live-code evidence : SSH-consolidated `curl http://127.0.0.1:8000/v1/yield-curve` from Hetzner returned 200 + 8/10 tenors LIVE (`observation_date: 2026-05-18T00:00:00Z`, shape="normal", slope_2y_10y=+0.54). The API IS live.

4. **THE LEVEL-4 R59 LAYER (the meta-level lesson #1 reconciliation)** : the orchestrator's OWN R59 sub-agent's conclusion ("the bug is `revalidate: 300` (5-min ISR cache) intersecting with transient API null returns") was itself a HYPOTHESIS that the deployed witness FALSIFIED. After applying `revalidate: 300 → 60`, building, deploying via `redeploy-web2.sh`, and Playwright-witnessing the public `/yield-curve` surface (08:34:00 UTC + cache-buster 08:37:02 UTC), the page CONTINUED to render the FALLBACK seed (▼ OFFLINE · SEED · SHAPE: INVERTED_SHORT verbatim, tenor values 4.86%/4.78%/.../4.38% = FALLBACK const, slope -44bps inverted). The hypothesis was empirically falsified. A deeper SSH diagnostic discovered the actual mechanism : **Next.js Static Site Generation bakes the build-time apiGet null result into the static HTML output** (`/opt/ichor/apps/web2-deploy/apps/web2/.next/server/app/yield-curve.html` exists with FALLBACK content). At build time, the systemd `Environment=ICHOR_API_URL=http://127.0.0.1:8000` line does NOT propagate (the build runs as user `ichor` in a non-systemd context), so apiGet's default `process.env.ICHOR_API_URL ?? "http://localhost:8001"` resolves to localhost:8001 (unreachable on Hetzner build context) → fetch fails → apiGet returns null → FALLBACK is RENDERED into the static HTML output. Every subsequent request serves the same baked-in stale FALLBACK regardless of ISR `revalidate` TTL. The actual fix = `export const dynamic = "force-dynamic"` to bypass SSG and render at request-time where systemd Environment correctly provides ICHOR_API_URL. The lesson #1 forecast≠proof discipline applied AT THE META LEVEL : even the orchestrator's R59 sub-agent's conclusion is a HYPOTHESIS that the witness verifies or falsifies — the test/the deployed pixel is ground truth.

## What r122 implemented

1. **`apps/web2/app/yield-curve/page.tsx`** — added 2 page-level directives :

   ```ts
   export const dynamic = "force-dynamic"; // bypass SSG bake-in (the load-bearing fix)
   export const revalidate = 60; // page-level ISR TTL (60s)
   ```

   plus a 13-line comment block above them documenting the LEVEL-4 R59 narrative + the SSG bake-in mechanism + the `/hourly-volatility/[asset]:32-33` house pattern alignment. Inside the page body, the fetch-level `{ revalidate: 60 }` (was 300) is preserved as a defensible secondary alignment with sibling deep-dive house pattern (the `/hourly-volatility/[asset]` precedent uses 300s, but the page-level is what matters here). The `FALLBACK` const at `page.tsx:18-39` is UNCHANGED. The `isLive`/`apiGet` contract (`lib/api.ts:21-49`) is UNCHANGED. ZERO test file modification.

2. **ADR-099 `## Implementation (r122, 2026-05-20)`** — dated §Impl appended after r121, NO new ADR (doctrine #9). FOUR-LAYER R59 narrative + the falsified-forecast reconciliation + the empirical 2-attempt witness.

## Reviews (single-pass ichor-trader R28 dispatched pre-Attempt-1)

- **ichor-trader R28 — GREEN, MERGE-ready, 0 RED / 0 Critical, 2 YELLOW doc-only.** ADR-017 boundary CLEAN. Mechanism diagnosis VERIFIED. Sibling-300s flag-not-touched VERIFIED. Cache-pattern claim INDEPENDENTLY VERIFIED. Cross-file-drift CLEAN. TRIPLE→FOUR-LAYER meta-r110 disproof SOUND. Data-honesty narrative ACCURATE. **YELLOW-1 (placeholders → MEASURED)** : DONE post-witness in the ADR. **YELLOW-2 ("post-deploy state EXPECTED LIVE" → "post-deploy state MEASURED LIVE")** : DONE post-witness — the §Impl(r122) records the empirical 2-attempt witness.
- **NO ui-designer / NO accessibility-reviewer** dispatched per classe-trigger rules : no NEW component, no nouvel encodage couleur, no changement-pixel-délibéré. Pure render-mode + cache-config tuning.

## Verification (MEASURED, no forecast — the empirical 2-attempt witness)

### Attempt 1 (post-`revalidate: 300 → 60` only, NO `force-dynamic`)

- Build : tsc 0 / eslint 0 / vitest 7f/147p UNCHANGED / next build OK, `/yield-curve` **`○ Static`** with `5m revalidate, 1y expire` columns
- Deploy : `redeploy-web2.sh` → local=200 public=200, DEPLOY OK, LIVE URL stable, ONE consolidated SSH
- Deployed witness (Playwright 08:34:00 UTC + cache-buster 08:37:02 UTC) : page STILL renders FALLBACK seed (`▼ OFFLINE · SEED · SHAPE: INVERTED_SHORT`, tenors 4.86%/4.78%/.../4.38% verbatim FALLBACK, slope -44bps inverted, note "2Y-10Y inverted → growth premium compressed, USD haven flows expected"). **HYPOTHESIS FALSIFIED.**
- Diagnostic SSH : `/opt/ichor/.../yield-curve.html` exists with FALLBACK baked in. journalctl shows ZERO `[api]` warnings post-restart (no runtime SSR fetch happens because page is static-served). systemd env IS correctly applied to running process. `sudo -u ichor curl 127.0.0.1:8000` returns 200 + LIVE data. **Root cause = Next.js SSG bake-in at build time, NOT ISR cache pollution.**

### Attempt 2 (post-`force-dynamic + revalidate=60` page-level + fetch-level `revalidate:60`)

- Build : tsc 0 / eslint 0 / vitest 7f/147p UNCHANGED / next build OK, `/yield-curve` **`ƒ (Dynamic)`** 241 B 165 kB (the render-mode flip empirically measured in the build output)
- Deploy : `redeploy-web2.sh` → local=200 public=200, DEPLOY OK, LIVE URL stable, ONE consolidated SSH
- Deployed witness (Playwright 08:44:01 UTC, cache-buster `?cb=r122-final`) :
  - Header pill : **`▲ LIVE · SHAPE: NORMAL`** (was `▼ OFFLINE · SEED · SHAPE: INVERTED_SHORT`)
  - Tenors : `1Y 3.81% / 2Y 4.07% / 3Y 4.14% / 5Y 4.27% / 7Y 4.43% / 10Y 4.61% / 20Y 5.14% / 30Y 5.14%` — **BYTE-IDENTICAL** to SSH-verified API response (FRED 2026-05-18 observations)
  - 3M + 6M filtered out (API `yield_pct: null` on those, page.tsx:47 filter at `p.yield_pct !== null`)
  - Slope : **`10Y - 2Y +54 bps normal`** (was -44bps inverted) ; `30Y - 5Y +87 bps term premium` ; `REAL 10Y +213 bps TIPS 2.13%`
  - FRED source-stamps : `DGS1 · DGS2 · DGS3 · DGS5 · DGS7 · DGS10 · DGS20 · D...`
  - **DATA-HONESTY DEFECT FIXED ON DEPLOYED SURFACE** — the page now propagates the REAL normal-curve macro context instead of the misleading FALLBACK inverted-bear seed.

### The empirical witness DIFFERENTIATES the two attempts and PROVES `force-dynamic` was the load-bearing fix

The Attempt-1 SEED-stuck FALSIFIED the R59 sub-agent's "ISR cache TTL" hypothesis. The Attempt-2 LIVE-confirmed the SSG-bake-in fix. The `revalidate: 60` change ALONE was insufficient ; `dynamic = "force-dynamic"` was the load-bearing addition. The lesson #1 forecast≠proof discipline applied at the META level (forecast = sub-agent's R59 conclusion ; proof = deployed pixel-witness). The orchestrator + the sub-agent + the trader-review were ALL on a hypothesis until the witness arrived. **The deployed-pixel-witness is ground-truth.**

## Doctrine / lessons applied

- **meta-r110 FOUR-FOLD (r122)** : (1) v40/v41 prompt FALLBACK discipline respected ; (2) r118-r121 framing "silently picks seed" reframed by 1st sub-agent ; (3) orchestrator's "backend-dependent" hypothesis disproved by SSH ; (4) **THE 1st R59 sub-agent's "ISR cache TTL is the bug" hypothesis FALSIFIED by deployed witness** — the actual mechanism is SSG bake-in, the actual fix is `force-dynamic`. THE META-LEVEL LESSON : even the orchestrator's OWN R59 conclusions are HYPOTHESES that the deployed pixel-witness verifies or falsifies.
- **lesson #1 forecast≠proof discipline applied at THREE meta levels in r122 alone** (prompt framing + orchestrator pre-investigation + R59 sub-agent hypothesis — all 3 reconciled to the deployed witness).
- **doctrine #14** : gate re-run on the committed post-LEVEL-4-apply shape ; ADR Reviews/Verification reconciled to MEASURED with 0 PENDING in the merge commit (the ichor-trader NO-MERGE-gate honored).
- **doctrine #5 cross-file-drift hygiene** : sibling 300s pages (`/hourly-volatility/[asset]` + `/confluence/history`) were verified to already have `force-dynamic` set, so the SSG-bake-in defect doesn't affect them — `/yield-curve` was the ONLY page missing the directive among the 300s-revalidate set. r122 closes that gap.
- **doctrine #7** : ONE consolidated SSH per deploy run + ONE for the diagnostic + ONE for the API-liveness probe — throttle-aware.
- **doctrine #11 honest scope** : the `revalidate: 60` change was kept (defensible house-pattern alignment) but explicitly framed as a SECONDARY change, NOT the root-cause fix. r123+ could revisit whether the fetch-level `revalidate: 60` is even needed on a `force-dynamic` page — flag-not-fix this round.
- Voie D + ADR-017 N/A held ; additive web2-only ; zero backend / zero migration (alembic 0050) ; NO new ADR (doctrine #9 dated §Impl) ; ONE consolidated SSH per call.

## Backlog noted (NOT r122 scope — recorded honestly)

- **r123+ candidate** : revisit whether the fetch-level `revalidate: 60` on `/yield-curve/page.tsx:53` is needed at all (a force-dynamic page with default `no-store` fetch would be equivalent — the fetch-level TTL only matters if multiple components in the same render share the cached value, which isn't the case here). Flag-not-fix.
- **r123+ candidate (typography-reconcile, ui Important-1 from r121 DEFERRED-with-rationale)** : `<HourlyVolReport>` glass chrome `<header border-b> + serif h3 title` adoption. Eliot-preference-dependent trade-off. DEFER until Eliot signals preference.
- **r123+ candidate (B′) more consumers** : likely backend-first (no remaining R59-proven projected-AND-populated DISTINCT live series at this layer).
- **r123+ candidate T4.2 muted-text recalibration** : repo-wide a11y hygiene per the r121 a11y review's empirical Δ +0.25 to +0.81 finding (r121 IMPROVED §T4.2 on glass without recalibrating the token itself ; the muted-text recalibration would be a separate increment).
- **Pre-existing r111 spawn-task `/briefing/*` vendor-chunk `TypeError e[o]`** : not r122's domain ; flag-not-fix #11.

## Files

- `apps/web2/app/yield-curve/page.tsx` (added `export const dynamic = "force-dynamic"` + `export const revalidate = 60` at module scope + 13-line comment block ; fetch-level `revalidate: 300 → 60` ; FALLBACK + isLive + apiGet contract UNCHANGED)
- `docs/decisions/ADR-099-north-star-architecture-and-staged-roadmap.md` (§Impl(r122) appended after §Impl(r121) with FOUR-LAYER R59 narrative + 2-attempt empirical witness MEASURED ; Reviews + Verification reconciled to MEASURED with 0 PENDING)
- `docs/SESSION_LOG_2026-05-20-r122-EXECUTION.md` (this)

## Next (r123) — R59-subject default (the menu-default is itself R59-subject, meta-r110→r122)

- **(typography-reconcile, ui Important-1 from r121, DEFERRED-with-rationale)** : Eliot-preference-dependent trade-off. R59-needed at r123 : is Eliot's preference for sub-component-identity (current r121 shape, trader-preferred) or for full-sibling-identity (ui-designer-preferred)? If unclear → DO NOT FORCE.
- **(revalidate cleanup r123 candidate)** : revisit whether `revalidate: 60` at the fetch-level OR page-level OR both makes sense on a `force-dynamic` page — most likely simplify to just `dynamic = "force-dynamic"` and remove the revalidate options entirely (since force-dynamic + no revalidate = fresh every request).
- **(B′)** more `<Sparkline>`/`<BarSeries>` consumers on another proven-live DISTINCT series : remaining proven-live FE surface exhausted at this layer (per r120/r121 R59) ; would need NEW backend projection.
- **T4.2 muted-text recalibration** : repo-wide a11y hygiene, well-bounded scope.
- regime-timeline still DEFERRED (needs NEW backend regime-TIME-series projection, the #1 Pydantic-projection class, backend-first).

**Default sans pivot (« continue » = this, doctrine #10) : r123 = ADR-099 Tier 4 further additive coverage — R59-first (the default is R59-subject), decide between cleanup / typography-reconcile / B′ / T4.2 on real value + data projected-AND-populated + honest feasibility + Eliot signal (typography-reconcile) ; no forced migration.**
