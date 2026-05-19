# SESSION LOG — 2026-05-19 — r120 EXECUTION

> ADR-099 §D-3 **Tier 4 (E): hourly-volatility seasonality on the PRIMARY
> `/briefing/[asset]` page**, via a doctrine-#9 EXTRACT-to-shared
> `<HourlyVolReport>` (the r71/r105/r109 anti-accumulation pattern — NOT
> copy-paste) + a thin shared `getHourlyVol` fetch wrapper. The standalone
> `/hourly-volatility/[asset]` page refactored byte-identical. Reuses the
> r116 `<BarSeries>` SSOT. NO new ADR, NO new primitive, NO new coord-math,
> ZERO backend/migration. doctrine-#9 coord-math ledger UNCHANGED.

## Resume / ground-truth concordance (r116-lesson permanent discipline)

- `git -C friendly-fermi-2fff71` at r120-START: HEAD `47faf27` == `origin/claude/friendly-fermi-2fff71` (byte-equal, pushed) ; `origin/main` `1909ca0` ; **85 ahead** ; tree clean ; alembic 0050. Matches the r119-close state exactly — the live wins and validates the resume.
- `git log -6` confirms r119 on top of r118 + the r114/r115/r116a spawn-task ancestors. **No concurrent drift, branch STABLE.**
- **RE-GREP ADR-099 `^## Implementation (r1…` headers** at round-start AND immediately before the append (the r116 permanent lesson): unique r104→r119, NO `r120` heading, append point EOF clean (ADR was 2698 lines).

## R59 inspect-first — the menu-default is itself R59-subject (meta-r110→r119)

The r119-close menu offered (B′) more consumers / (E) hourly-vol on the primary briefing / (D‴) ε-removal / T4.2. A read-only `researcher` R59 + the orchestrator's own file:line verification:

- **(E) RANK #1 — the prompt's own (E) gating-hypothesis was R59-DISPROVED.** The "web2-SSR-API-base seed fallback" r118/r119 surfaced is **`/yield-curve`-SPECIFIC, NOT a universal SSR gate**: `apiGet` (`lib/api.ts:9` base `process.env.ICHOR_API_URL ?? localhost:8001`, `:35` default `cache:"no-store"`, returns `null` on failure) is the SAME path for both routes ; `/yield-curve` has a hardcoded `FALLBACK` const (silently renders the seed on `null`), whereas `/briefing/[asset]` has **NO `FALLBACK`** and degrades honestly — and r112/r113 deployed-witnessed 90 REAL live bars on `/briefing/EUR_USD`, proving that same `apiGet` SSR path reaches live data in prod. So a new hourly-vol fetch on the briefing page is honestly live, NOT seed-gated. (E)'s SHIPPED≠FUNCTIONAL fear = **falsified by the live code** (meta-r110 — the prompt's gating-hypothesis is itself R59-subject ; disproving it is a recorded part of the verified increment). (B′) = strictly lower value (a subset of (E)'s mechanism). (D‴) = YAGNI/DEFER (smallest tenor `0.25` → `Math.log` finite, no `log(0)` input ever — recorded as a one-line backlog note, NOT shipped).
- R59 self-verified the load-bearing facts on the LIVE code (the sub-agent map is a hypothesis): `apiGet` mechanism, the briefing `Promise.all` structure (12 entries, NO FALLBACK), `HeatmapBars`/`Percentile75Bars`/`SessionAverages` are PAGE-LOCAL (not exported) in the standalone page ⇒ the doctrine-#9-correct architecture is EXTRACT-to-shared, not copy-paste.

## What r120 implemented

1. **NEW `apps/web2/components/hourly-vol/HourlyVolReport.tsx`** — RSC-safe (NO `"use client"`, lesson #5), the 3 sub-sections moved VERBATIM from the standalone page + an exported `<HourlyVolReport report={HourlyVolOut|null} headingLevel?: 2|3 = 2 />` owning the `isLive` gate. The deterministic `git show "HEAD:.../hourly-volatility/[asset]/page.tsx" | diff` PROVED the bodies byte-identical to the pre-r120 page-local defs EXCEPT exactly the concordant-3-reviewer `headingLevel` threading (signature `level` ×3 + `const H = \`h${level}\``×3 +`<h2>`→`<H>`/`</h2>`→`</H>` ×3 ; zero body-logic drift — the r71/r105 regression-safety claim PROVEN not asserted, the ichor-trader YELLOW-1 CLOSED).
2. **`apps/web2/lib/api.ts`** — NEW thin `getHourlyVol(asset)` mirroring `getIntradayBars` : the SINGLE source of the `/v1/hourly-volatility/{asset}?window_days=30` URL + `{revalidate:300}` opts (anti-accumulation — both consumers share it ; `encodeURIComponent` like the house helper, byte-identical for asset codes).
3. **`apps/web2/app/hourly-volatility/[asset]/page.tsx`** — REFACTORED to `getHourlyVol(slug)` + `<HourlyVolReport report={report} />` (no `headingLevel` → default 2 → `<h2>` byte-identical attrs), the 3 page-local defs deleted, file-header comment rewritten (no stale drift) → **byte-identical rendered DOM** (the r71/r105 zero-behaviour-change discipline, proven by the deployed standalone witness vs the r117 shape).
4. **`apps/web2/app/briefing/[asset]/page.tsx`** — `getHourlyVol(normalisedAsset)` added to the existing `Promise.all` (12→13, destructure `hourlyVol`) + a NEW additive `<section aria-labelledby="hourly-vol-heading">` (mirrors the Volume-section house pattern verbatim) between Volume and Corrélations, rendering `<HourlyVolReport report={hourlyVol} headingLevel={3} />` (the applied a11y/ui fix) + the ui Nit-3 descriptor trim.
5. **ADR-099 `## Implementation (r120, 2026-05-19)`** — dated §Impl appended AFTER r119 (RE-GREP'd), NO new ADR ; Reviews/Verification written as placeholders then RECONCILED to MEASURED (the round's own discipline / ichor-trader YELLOW-2/4 / NO-MERGE-gate — 0 PENDING in the merge commit).

## Reviews (consolidated 1-pass — all 3 dispatched, doctrine #14/#17)

- **ichor-trader R28 — YELLOW, NO-MERGE-until-reconciled, 0 RED code defects.** ADR-017 OK (the `order` greps were `border-` Tailwind substrings ; the footer disclaimer still covers the page). doctrine-#9 extract-not-copy-paste GREEN (genuine shared component, standalone CONSUMES it, ledger UNCHANGED correct). R59 (E)-gate-disproof SOUND/non-ego. Cross-file drift clean. YELLOW-1 (verbatim claim unverified by the sub-agent) → **CLOSED by the orchestrator's deterministic `git show HEAD: | diff`**. YELLOW-2 (FAIL-SAFE asymmetry) = inherited-verbatim pre-r120 behaviour, NOT a regression, doc-noted (anti-scope-creep). YELLOW-3 (heading-order) → APPLIED. YELLOW-4 / NO-MERGE-gate = reconcile PENDING→MEASURED before the merge commit → DONE.
- **ui-designer — MERGE-with-changes, 0 Critical, 2 Important, 3 Nit.** Section-wrapper PASS (byte-for-byte house pattern, coherent placement). Important-1 (heading-rank flatten) → APPLIED (`headingLevel` prop). Important-2 (double-titling) → RESOLVES via Important-1. Nit-2 (spacing) = N/A correct behaviour. Nit-3 (descriptor longest) → APPLIED (trimmed). Nit-1 (card chrome `rounded-xl`/`shadow-sm` vs the glass `rounded-2xl`/`backdrop-blur-xl` of VolumePanel/ScenariosPanel) = an **acceptable verbatim-move tradeoff → r121+ backlog** (restyling would break the standalone byte-identical discipline + is a separate cross-page design-reconciliation — flag-not-fix-with-reason, NOT a pre-existing-defect re-scope). Byte-identical standalone PASS.
- **accessibility-reviewer — PASS, 0 MUST-FIX, 2 SHOULD-FIX.** Duplicate-id CLEAN. 1.4.1 colour-only PASS (3 colour-independent channels preserved by the verbatim move). SHOULD-FIX-1 (heading-rank flatten, r120-introduced) → APPLIED (the `headingLevel` prop — the reviewer-endorsed fix, default 2 byte-identical / briefing 3). SHOULD-FIX-2 (`--color-text-muted` ≈3.4–4.0:1) = pre-existing §T4.2 backlog (r120 propagates, did NOT introduce) — flag-not-fix #11, NOT re-scoped. Pre-existing 1.1.1 BarSeries aria-label+`<title>` dup (r116-origin) — flag-not-fix #11.

**Consolidated apply (1-pass, doctrine #14): triple-concordant `headingLevel?:2|3` prop APPLIED (default 2 → standalone byte-identical DOM ; briefing passes 3) + ui Nit-3 descriptor trim APPLIED ; YELLOW-1 CLOSED by deterministic git-diff proof ; YELLOW-2 + ui Nit-1 = flag-not-fix-with-reason (r121+ backlog) ; a11y §T4.2 + r116 = pre-existing flag-not-fix #11, NOT re-scoped ; gate RE-RUN post-apply.**

## Verification (MEASURED, not forecast)

- **Build gate** (re-run post-review-apply, doctrine #14): `tsc` **0** · `eslint --max-warnings 0` (4 changed files) **0** · vitest **7 files / 147 pass** (UNCHANGED baseline — r120 adds no test ; verbatim extraction proven by the deterministic git-diff + the deployed witness per the r71/r105 precedent, no forced jsdom dep) · `next build` **✓ Compiled successfully**, `/briefing/[asset]` ƒ 17.5 kB, `/hourly-volatility/[asset]` ƒ 1.23 kB (−190 lines moved to the shared component).
- **YELLOW-1 verbatim-extraction PROOF (deterministic):** `git show "HEAD:apps/web2/app/hourly-volatility/[asset]/page.tsx" | diff` vs the new component — ONLY the extraction wrapper/import/gate + the concordant `headingLevel` threading ; every body computation byte-identical.
- **Deploy**: `redeploy-web2.sh` additive — Hetzner Linux build clean, `local=200 public=200`, `DEPLOY OK`, LIVE URL **stable**, tunnel not restarted, legacy 3030 untouched, ONE run no-throttle.
- **Deployed DUAL real-prod witness (Playwright):** (1) **standalone `/hourly-volatility/EUR_USD` byte-identical vs r117** — `h1 → h2×3` (all H2, default headingLevel=2), median BarSeries `aria "…pic 13:00, creux 02:00"` 24 rects 2-stroked fills `[cobalt,bear,bull]` + p75 24 rects 0-stroked `[text-secondary]`, `offline=null` (live) = EXACTLY the r117 shape ⇒ r71/r105 zero-behaviour-change PROVEN on the deployed surface. (2) **briefing `/briefing/EUR_USD` — the NEW hourly-vol section LIVE** : section `H2 "Volatilité horaire"` + trimmed descriptor → **`H3 #heatmap-heading` / `H3 #p75-heading` / `H3 #session-avg-heading`** (the concordant `headingLevel={3}` fix LIVE-CONFIRMED, no h2-under-h2 flatten) ; 2 BarSeries LIVE (`offline=null`, same R53 EUR profile `pic 13:00 / creux 02:00` as the standalone) ⇒ **the R59 (E)-gate-disproof EMPIRICALLY CONFIRMED — the briefing fetch reaches live data, NOT seed-gated** (SHIPPED≠FUNCTIONAL satisfied) ; the 5 `role="img"` (r112 price + r113 amplitude Sparklines + VolumePanel + the 2 NEW hourly-vol) are genuinely distinct ⇒ the r113/r117 NOT-a-duplicate discipline satisfied empirically.
- **HONEST SCOPE (lesson #1/#11/r106-a, causation≠proof):** the briefing console = **9 errors / 2 warnings = the PRE-EXISTING r111-flagged `/briefing/*` vendor-chunk defect** (`TypeError: e[o] is not a function` in chunks `5318`/`5889`/`7985` + `webpack-*.js`, asset-agnostic — **ZERO r120 code in any of the 9 stack traces**). r120 NEITHER caused NOR fixed it (the r120 section renders PERFECTLY alongside, proving pre-existence per the r111/r112/r113 discipline) ; the r111-spawn-task remains the owner (flag-not-fix #11, NOT re-scoped, NOT re-claimed — neither a 0/0 nor a regression). The standalone surface rendered cleanly.

## Doctrine / lessons applied

- **meta-r110 (extended r119)**: the resume-prompt's OWN (E) gating-hypothesis ("the web2-SSR-seed condition may gate any new SSR-fetch surface") was R59-subject and **DISPROVED by the live code** (it is `/yield-curve`-specific, the briefing uses the proven-live path) — the disproof recorded as a verified part of the round, then EMPIRICALLY CONFIRMED by the deployed briefing witness (live data).
- **doctrine #9 anti-accumulation EXTRACT-to-shared (the r71/r105/r109 precedent)**: a 2nd consumer of page-local logic MUST extract, never copy-paste — one brain (the shared component + the single `getHourlyVol` fetch source), two views (standalone + briefing). The coord-math ledger is UNCHANGED (r120 reuses the r116 `<BarSeries>` SSOT, adds no scalar/coord-math).
- **r71/r105 zero-behaviour-change extraction discipline**: the standalone page proven byte-identical (deterministic git-diff + the deployed witness) ; the ONLY post-extraction delta = the concordant-3-reviewer `headingLevel` threading, default 2 keeping the standalone byte-identical.
- **lesson #1/#11/r106-a (causation≠proof, honest scope)**: the pre-existing r111 `/briefing/*` console defect flagged-not-fixed, NOT re-claimed (neither 0/0 nor regression — r120 renders perfectly alongside it).
- **doctrine #14**: gate re-run on the committed post-review-apply shape ; ADR Reviews/Verification reconciled to MEASURED with 0 PENDING in the merge commit (the ichor-trader NO-MERGE-gate).
- Voie D + ADR-017 N/A held ; additive web2-only ; zero backend / zero migration (alembic 0050) ; NO new ADR (doctrine #9 dated §Impl) ; ONE consolidated SSH (deploy script internal, no throttle).

## Backlog noted (NOT r120 scope — recorded honestly)

- **ui Nit-1 / r121+ chrome reconciliation**: `<HourlyVolReport>`'s 3 cards use the flat standalone style (`rounded-xl` opaque `bg-surface` `shadow-sm`) vs the glass house style (`rounded-2xl bg-surface/40 backdrop-blur-xl`) of the sibling `VolumePanel`/`ScenariosPanel` on the briefing page. A deliberate verbatim-move tradeoff ; a future increment may reconcile the card chrome to the glass house style (would need a shared chrome wrapper to keep BOTH consumers consistent — itself a doctrine-#9 extract).
- **§T4.2 muted-text contrast** (`--color-text-muted` ≈3.4–4.0:1) — pre-existing app-wide backlog, NOT r120-introduced (flag-not-fix #11).
- **r116-origin BarSeries `aria-label`+`<title>` SR double-announce** — pre-existing component-level backlog (flag-not-fix #11).
- **the pre-existing r111 `/briefing/*` vendor-chunk `TypeError`** — the r111-spawn-task domain, NOT r120's.
- **(D‴) yield-curve ε removal** — YAGNI (no `log(0)` input ever exists ; r119 deliberately kept ε as a defensible boundary guard) ; recorded, NOT shipped.

## Files

- `apps/web2/components/hourly-vol/HourlyVolReport.tsx` (NEW — verbatim-moved bodies + headingLevel threading + isLive gate wrapper)
- `apps/web2/lib/api.ts` (+ thin `getHourlyVol` — single fetch source)
- `apps/web2/app/hourly-volatility/[asset]/page.tsx` (refactored byte-identical, 287→~80 lines)
- `apps/web2/app/briefing/[asset]/page.tsx` (Promise.all 12→13 + additive section + headingLevel={3} + trimmed descriptor)
- `docs/decisions/ADR-099-north-star-architecture-and-staged-roadmap.md` (§Impl(r120) + Reviews/Verification reconciled to MEASURED, NO new ADR)
- `docs/SESSION_LOG_2026-05-19-r120-EXECUTION.md` (this)

## Next (r121) — R59-subject default (the menu-default is itself R59-subject, meta-r110→r120)

- **(B′) more `<Sparkline>`/`<BarSeries>` consumers** on another proven-live DISTINCT series (R59 projected-AND-populated ; `XvsYIdenticalPoints=false` at data+rendered — the r113/r117 discipline).
- **the r121+ chrome reconciliation** (ui Nit-1) — reconcile `<HourlyVolReport>`'s flat card chrome to the glass house style WITHOUT breaking the standalone byte-identical discipline (a shared glass-card-chrome wrapper extracted so BOTH the standalone and briefing consumers stay consistent — itself a doctrine-#9 extract ; R59 the exact glass token set from `VolumePanel`/`ScenariosPanel` first).
- regime-timeline still DEFERRED (needs a NEW backend regime-TIME-series projection, the #1 Pydantic-projection class, backend-first). T4.2 (uncertainty-band / calibration-overlay / degraded+empty / no-truncated-axis ; `prefers-reduced-motion` ALREADY globally clean — do NOT re-attempt) → T4.3 (responsive/mobile).

**Default sans pivot (« continue » = this, doctrine #10): r121 = ADR-099 Tier 4 further additive coverage — R59-first (the default is R59-subject), decide (B′)/(chrome-reconcile)/T4.2 on real value + data projected-AND-populated + honest feasibility, no forced migration.**
