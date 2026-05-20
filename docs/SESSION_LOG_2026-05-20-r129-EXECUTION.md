# Round 129 — Execution log

> **Date** : 2026-05-20 (5th round of the day after r125→r126→r127→r128 ; r129 spanned a session-resume hook ~4.2h gap between deploy and commit)
> **Worktree** : `D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`
> **Branch** : `claude/friendly-fermi-2fff71`
> **Round type** : Tier 4 NEW visible UI element (ADR-104 data-honesty staleness banner) — closes r127 trader NIT, surfaces calibration provenance to user
> **HEAD pre-r129** : `651f478` (r128 close, 94 ahead `origin/main` `1909ca0`)
> **HEAD post-r129** : `<commit-hash>` (1 commit, ~120 LOC + 5 new vitest cases, 95 ahead `origin/main`)
> **Production state** : alembic 0051 + 5 rows in `tempo_thresholds` (UNCHANGED from r128) + r127 wire LIVE + **r129 banner LIVE in panel footer** (deployed pre-resume at 18:43 CEST, committed post-resume after R59 git-state verification)

## §A — Atom summary

r129 surfaces the calibration provenance on the user surface — the panel footer of `<TodaySessionPulse>` now reads alongside the ADR-017 disclaimer :

> **"Calibration des seuils · aujourd'hui · n=16 · fenêtre 90 j"**

The r127 wire shipped the API-fed override mechanism BUT dropped `computed_at` + `sample_size` + `window_days` in the `getTempoThresholds()` flatten (the trader r127 NIT explicitly flagged this — calibration freshness invisible to Eliot). r128 ACTIVATED the cron + populated 5 rows but staleness still invisible. r129 closes the loop : Eliot can SEE how stale the thresholds are + how many samples backed them without leaving the briefing page.

**Mission centrale Axis-7 auto-improvement loop now has its 5th stage** :

> measure (cron) → store (table) → consume (label) → **SEE (banner)** → recalibrate

## §B — Files changed

1. **`lib/api.ts`** — `getTempoThresholds()` return shape **breaking change** : `Record<string, T> | null` → `{ thresholds, metadata } | null` envelope. New `TempoMetadata` + `TempoThresholdsBundle` interfaces. Sole consumer (briefing page) updated same commit ; lib is `apps/web2`-internal, NOT a public-API break.
2. **`lib/sessionPulse.ts`** — added `TempoMetadata` structural mirror (drift-guard test pins byte-identical field declarations) + `thresholdsMetadata?: Record<asset, TempoMetadata>` optional 6th param to `derivePulse(...)` + `tempo_metadata: TempoMetadata | null` field on `SessionPulse`. Backward-compat preserved.
3. **`app/briefing/[asset]/page.tsx`** — destructured `tempoBundle?.thresholds` + `tempoBundle?.metadata` as 5th + 6th args to `derivePulse(...)`.
4. **`components/briefing/TodaySessionPulse.tsx`** — `formatCalibrationAge(iso): string | null` helper (FR phrasing : `"à l'instant"` / `"aujourd'hui"` / `"hier"` / `"il y a N jours"` / `"il y a 30+ jours"` cap). Banner in **panel footer** alongside ADR-017 disclaimer (provenance-with-provenance per ui-designer concordant). Renders only when `formatCalibrationAge` non-null AND `tempo_metadata` present (doctrine #11 honest silent absence — never replaces missing with fabricated freshness). `calibrationAge` extracted to const once per render (code-reviewer N-1).
5. **`__tests__/sessionPulse.test.ts`** — +5 tests : threaded / omitted / asset-absent / unparseable-ISO / TempoMetadata drift-guard.

## §C — Review pass (4 parallel reviewers, classe-trigger NEW visible UI)

**Reviewers fired in parallel** : ichor-trader R28 + ui-designer + accessibility-reviewer + code-reviewer.

**Consensus post-apply** : 0 RED / 0 Critical / 0 PENDING.

### Concordance applied

1. **CONCORDANT (ui-designer + a11y)** — `text-[10px]` → `text-[11px]` size bump (contrast risk + zoom safety)
2. **CONCORDANT (a11y SC 1.3.1 + code-reviewer Y-1 + Y-2)** — aria-label override-on-`<p>` ignored per ARIA 1.2 spec + semantic-drift "16 jours échantillonnés" wrong + grammar awkward on `"à l'instant"` → DROPPED aria-label entirely (visible text self-explanatory)
3. **STRONG single-reviewer (ui-designer)** — placement Tempo-tile → panel-footer (provenance-with-provenance) — ALSO fixes mobile-wrap by side-effect. Applied per doctrine "STRONG single-reviewer semantic call applies when domain-single-discipline" (UI taxonomy is single-discipline).

### Individual fixes APPLIED

- ui-designer #1 prose-mono → sans (banner is mixed prose+numeric, leading "Calibration des seuils" is prose)
- trader Y-1 JSDoc "fenêtre 90j" literal drift → reworded
- trader Y-2 SSR `Date.now()` ISR 5-min quantization → JSDoc "live-ish ±5 min" honest framing
- code-reviewer N-1 `formatCalibrationAge` 3× call → extract-to-const once per render

### Deferred to r130+ (feature creep, doctrine #2)

- ui-designer stale-amber tint at `days >= 7` (would need conditional tone escalation)
- ui-designer degraded-sample tone at `sample_size < window_days * 0.5`
- code-reviewer N-3 30-day cap blind-spot (same conditional-tone family)
- ui-designer #6 r125-hardcoded fallback surfacing (declined per doctrine #11 honest silent absence)

## §D — Verification (MEASURED, lesson #1)

- **tsc** : `npx tsc --noEmit` → **0 errors**
- **eslint** : `--max-warnings 0` on 5 r129 files → **0 errors**
- **vitest sessionPulse** : 35 passed (was 34 pre-final-N-1 test + 1 unparseable-ISO regression = 35)
- **vitest full** : 8 files / 181 passed (was 177 r127 + 4 r129 new = 181, 0 regression)
- **next build** : ✓ Compiled successfully ; `/briefing/[asset]` shown as `ƒ Dynamic` (per-request render, no SSG bake-in risk for `Date.now()`)
- **redeploy-web2.sh** : `local=200 public=200`, `DEPLOY OK`, CF tunnel stable
- **Playwright TRIPLE witness GREEN** :
  - **EUR_USD** (`?cb=r129-witness-eur`) — banner LIVE in panel footer ; range 54 bp + tempo "tendance" 3.1× ; 0 console errors
  - **GBP_USD** (bonus from AssetSwitcher auto-redirect on first nav) — same banner format LIVE
  - **XAU_USD** (`?cb=r129-witness-xau-resume`) — banner LIVE in panel footer ; range 221 bp + tempo "Tendance" 3.0× ; snapshot confirms position AFTER intraday chart in footer block

## §E — Doctrines applied + lessons codified

**Applied** :

- doctrine #1 (R59 inspect-first reality wins) — verified git state + production state post-session-resume before commit
- doctrine #2 (strict scope) — deferred stale-amber + degraded-sample + r125-hardcoded surfacing to r130+
- doctrine #4 (concordant 2+ YELLOW → APPLY ; single-reviewer YELLOW → flag-not-fix UNLESS domain-single-discipline)
- doctrine #6 (single-step, no amend)
- doctrine #9 (anti-accumulation + dated §Impl append, NO new ADR — this extends r96 ADR-104)
- doctrine #11 (calibrated honesty — silent absence of metadata, not fabricated freshness)
- doctrine #14 (build-gate on COMMITTED shape, MEASURED Reviews/Verification, 0 PENDING in merge commit)
- doctrine #17 (4 parallel reviewers per classe-trigger NEW visible UI)
- lesson #22 (worktree-mismatch protocol)

**Codified new** :

- **Lesson #25 (r129)** : when 4 parallel reviewers fire on a NEW visible UI element (trader + ui-designer + a11y + code-reviewer), concordance often emerges on size + accessibility (apply concordant YELLOWs) ; STRONG single-reviewer ui-designer placement calls apply when domain is single-discipline (UI semantic taxonomy is single-discipline) even WITHOUT concordance, vs flag-not-fix for pure-preference.
- **Lesson #26 (r129)** : when a session is compacted mid-round (after deploy but before commit), the UNCOMMITTED local state matches the deployed production state — the post-resume close just needs R59 git-status verification + commit to capture reality, NOT a re-deploy.

## §F — Mission centrale Axis-7 status post-r129

✅ **PRECONDITION (r126)** — backend cron infrastructure
✅ **CONSUMER WIRE (r127)** — frontend lookup chain with 3-layer fallback
✅ **ACTIVE-ON-PROD (r128)** — LIVE deploy + 5 rows + DUAL Playwright witness
✅ **SEE-AND-TRUST (r129)** — calibration provenance visible on user surface

**Mission centrale Axis-7 auto-improvement loop is now FULLY OBSERVABLE on the user surface.** The 5-stage chain : measure → store → consume → SEE → recalibrate.

⏳ **r130 candidate** : threshold drift detector (auto-alert when this-week thresholds deviate by N% from N-weeks-ago) ; OR add stale-amber + degraded-sample tone escalation deferred from r129 ui-designer review ; OR start the next Mission centrale axis (Axis-4 Polymarket × DXY synthesis panel).

## §G — r130 candidate list (per ROADMAP §3 promotion)

1. **Threshold drift detector cron** — weekly cron comparing this-week vs last-week, structlog alert on >N% drift. New cron + `auto_improvement_log` `loop_kind` CHECK constraint ALTER. Effort M.
2. **Stale-amber + degraded-sample tone escalation** on banner — `days >= 7` → amber tint ; `sample_size < window_days * 0.5` → tone shift. Closes r129 ui-designer deferred missing-states. Effort S.
3. **Tempo cross-asset matrix on `/today`** — surface all 5 priority assets' tempo + thresholds at once. Effort M.
4. **AUD_USD revival** — alternative China money supply LIVE series (MYAGM1CNM189N still dead). Effort M-L.
5. **Polymarket × DXY synthesis panel** — Mission Axis-4 deepening from r123 audit. Effort M.

R59-AUDIT first to confirm honest scope on chosen path.
