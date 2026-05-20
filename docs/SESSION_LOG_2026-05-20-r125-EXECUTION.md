# SESSION LOG — 2026-05-20 — r125 EXECUTION

> ADR-099 §Impl(r125) Tier 4 per-asset tempo threshold recalibration on
> `<TodaySessionPulse>` (lib/sessionPulse.ts) : empirical SQL-derived
> per-asset `TEMPO_THRESHOLDS_BY_ASSET` const replaces the r123
> EUR_USD-calibrated global ratio thresholds. Closes the r123 backlog
> top item (per-asset recalibration deferred to r124+) + the r123 trader
> R28 YELLOW-2 honest disclosure "labels lean conservative on higher-vol
> assets". **r124 ROADMAP-driven execution discipline validated** : the
> canonical `docs/ROADMAP.md` §3 binding "immediate next" reference drove
> the r125 default selection per lesson #21.

## Resume / ground-truth concordance

- `git -C friendly-fermi-2fff71` at r125-START : HEAD `1e8e919` (r124 close) == origin/branch byte-equal ; origin/main `1909ca0` ; 90 ahead ; tree clean ; alembic 0050.
- §Impl headers : r104→r124 unique, NO r125 yet — append-point clean. Verified at round-start AND immediately before append per r116-lesson permanent discipline.

## R59 — UNE SSH consolidée empirical calibration (the load-bearing input)

Per the r124 canonical `docs/ROADMAP.md` §4 r125 top-default row, r125 = per-asset tempo recalibration via offline R53 SSH `psql` on Hetzner. **R59 BACKEND** : `polygon_intraday` table (verified via `models/polygon_intraday.py:22`) + columns `asset/bar_ts/open/high/low/close`.

**SSH query (one consolidated, throttle-aware)** :

```sql
WITH daily AS (
  SELECT
    asset,
    bar_ts::date AS day,
    MAX(high) AS day_high,
    MIN(low) AS day_low,
    (array_agg(open ORDER BY bar_ts ASC))[1] AS day_open
  FROM polygon_intraday
  WHERE bar_ts > now() - interval '60 days'
    AND asset IN ('EUR_USD','GBP_USD','XAU_USD','SPX500_USD','NAS100_USD')
  GROUP BY asset, day
)
SELECT asset, COUNT(*),
  percentile_cont(0.10/0.25/0.50/0.75/0.90/0.95) WITHIN GROUP (ORDER BY (day_high - day_low) / day_open * 10000)
FROM daily WHERE day_open > 0
GROUP BY asset ORDER BY asset;
```

**Empirical 60-day distribution (MEASURED, 2026-05-20)** :

| asset      | n_days | p10  | p25   | p50   | p75   | p90   | p95   |
| ---------- | ------ | ---- | ----- | ----- | ----- | ----- | ----- |
| EUR_USD    | 16     | 15.4 | 31.7  | 47.2  | 54.2  | 59.1  | 68.9  |
| GBP_USD    | 16     | 17.0 | 41.6  | 64.5  | 71.2  | 95.8  | 110.9 |
| XAU_USD    | 16     | 0.0  | 140.0 | 177.2 | 273.7 | 307.4 | 344.3 |
| SPX500_USD | 8      | 31.6 | 77.2  | 102.7 | 112.3 | 126.0 | 139.5 |
| NAS100_USD | 12     | 82.6 | 114.1 | 138.7 | 166.4 | 180.7 | 186.8 |

The cross-asset daily-range distribution differs by **4× (EUR median ~47 bp vs XAU median ~177 bp)** — confirms the r123 trader R28 YELLOW-2 honest disclosure. r125 fixes via per-asset ABSOLUTE bp thresholds.

## What r125 implemented

1. **`apps/web2/lib/sessionPulse.ts`** :
   - NEW `TempoThresholds` interface (the typed shape)
   - NEW `DEFAULT_TEMPO_THRESHOLDS: TempoThresholds` literal (EUR_USD's values, FX-major-conservative fallback)
   - NEW `TEMPO_THRESHOLDS_BY_ASSET: Record<string, TempoThresholds>` with 5 priority assets' empirical thresholds (mapping breakout=p90 / active=p75 / trending=p50 / range_bound=p25)
   - NEW `tempoLabelByAsset(range_bp, asset): TempoLabel` pure function — looks up per-asset thresholds with DEFAULT fallback for unknown assets
   - REMOVED the old `tempoLabel(ratio)` function (no longer the label driver)
   - `derivePulse` signature extends with `asset: string = ""` (default empty = fallback ; backward-compat preserved)
   - `derivePulse` return uses `tempoLabelByAsset(range_bp, asset)` instead of `tempoLabel(tempo_ratio)`
   - The `tempo_ratio` + `expected_range_bp_30d` STILL computed + returned in SessionPulse — they drive the meter visualization + the "X× vs p75 30 j" display in the panel ; only the LABEL is per-asset-grounded now (decoupling pinned by the YELLOW-2 test)
2. **`apps/web2/__tests__/sessionPulse.test.ts`** :
   - REPLACED the 4 ratio-based tempo tests (would fail under r125)
   - ADDED 13 NEW tempo tests : EUR (3 : breakout, trending, compressed) + GBP (1 : range-bound) + XAU (2 : trending, breakout) + SPX (1 : trending) + NAS (1 : active) + unknown-asset fallback (1) + empty-asset fallback (1) + null-hourlyVol-with-asset (1) + YELLOW-1 boundary-equality at EUR p90=59.1 (1) + YELLOW-2 decoupling ratio-vs-label (1)
   - REMOVED unused `hourlyVol` helper + `HourlyVolOut`/`HourlyVolEntry` imports
3. **`apps/web2/app/briefing/[asset]/page.tsx`** : one-line wiring to pass `normalisedAsset` as 4th arg to `derivePulse`.
4. **`apps/web2/components/briefing/TodaySessionPulse.tsx`** : UNCHANGED (consumes `pulse.tempo_label` etc. — no API change visible).
5. **`docs/decisions/ADR-099-...md`** : `## Implementation (r125, 2026-05-20)` appended with the empirical data + per-asset thresholds + honest scope flags + MEASURED Reviews/Verification.

## Reviews — ichor-trader R28 single review (per-classe-trigger scope)

- **ichor-trader R28 — GREEN, MERGE-READY, 0 RED / 0 Critical / 0 MUST-FIX, 2 YELLOW + 1 NIT all applied.**
- ADR-017 vocabulary canary CLEAN ; doctrine #9 SSOT CLEAN ; doctrine-#9 coord-math ledger UNCHANGED ; empirical data VERBATIM MATCH across 20 numbers ; backward-compat VERIFIED ; honest scope flags PRESENT in the const docstring ; cross-file-drift hygiene VERIFIED ; calibration direction CORRECT (XAU 200 bp pre-r125 false-positive breakout → post-r125 trending).
- **YELLOW-1 APPLIED same-commit** : boundary-equality test at EUR_USD p90=59.1 → breakout (pins `>=` inclusive semantic).
- **YELLOW-2 APPLIED same-commit** : decoupling test demonstrating `tempo_ratio` non-null AND label is range_bp + asset driven (NOT ratio-driven) — XAU 200 bp + low p75=10 baseline (ratio ≥ 5×) STILL gets "trending" label (not "breakout") because range_bp = 200 ∈ XAU's [177.2, 273.7].
- **NIT framing APPLIED** : r125 honestly framed as "Axis-4 enabler + Axis-7 auto-recalibration precondition" rather than "Axis-4 leap" (per the trader R28 net-honest framing).
- **NO ui-designer / NO accessibility-reviewer** per classe-trigger (numeric thresholds change, no NEW visible component, no nouvel encodage couleur, no changement-pixel-délibéré — the label STRINGS + tile + meter + colors are visually unchanged).

## Verification (MEASURED, no forecast — empirical deployed witness)

### Build gate (post-1-pass-apply on committed shape, doctrine #14)

- `tsc --noEmit` **0**
- `eslint --max-warnings 0` (3 files) **0**
- vitest **8 files / 171 pass** (was 8f/162 pre-r125 — net +9 tempo tests : 11 r125 per-asset + YELLOW-1 boundary + YELLOW-2 decoupling = 13 added, 4 r123 ratio-based replaced)
- `next build` ✓ Compiled successfully

### Deploy

- `bash scripts/hetzner/redeploy-web2.sh` additive
- `local /briefing http=200` Step 4
- `RESULT: local=200 public=200`, `DEPLOY OK` Step 5
- LIVE URL stable `https://latino-superintendent-restoration-dealtime.trycloudflare.com`
- Tunnel NOT restarted, ONE consolidated SSH chain

### Deployed real-prod DUAL witness (Playwright)

**(1) `/briefing/EUR_USD?cb=r125-witness-v2`** (after 1 transient 502 retry post-restart) :

- H2 = "Aujourd'hui · mercredi 20 mai" ✓
- 4 stat tiles populated LIVE :
  - Ouverture 00:00 Paris 1.16048
  - Maintenant 14:26 1.15982 (**-0.06%**)
  - Range jour **27 bp** (1.16140 / 1.15830, Londres 19 bp)
  - **Tempo = Compressé** (2.1× vs p75 30 j displayed in meter)
- **r125 EMPIRICAL VALIDATION** : EUR @ 27 bp + asset="EUR_USD" → range_bp 27 < EUR_USD's range_bound threshold 31.7 → **"compressed"** label. Pre-r125 same data would have shown "active" via tempo_ratio 2.1× ≥ 1.0 global EUR-baseline. The per-asset threshold correctly identifies this as a quiet day for EUR.
- Chart aria-label = "Lecture intraday EUR/USD — ouverture 00:00 Paris à 1.16048, prix actuel 1.15982 (-0.06%), range jour 27 points de base, Londres 19 points de base, tempo compressé (2.1× vs typique 30 jours)."

**(2) `/briefing/XAU_USD?cb=r125-witness`** :

- H2 = "Aujourd'hui · mercredi 20 mai" ✓
- 4 stat tiles populated LIVE :
  - Ouverture 00:01 Paris 4480.95
  - Maintenant 14:26 4496.33 (**+0.34%**)
  - Range jour **124 bp** (4508.68 / 4453.00, Londres 66 bp)
  - **Tempo = Compressé** (2.3× vs p75 30 j displayed in meter)
- **r125 EMPIRICAL PROOF** : XAU @ 124 bp + asset="XAU_USD" → range_bp 124 < XAU's range_bound threshold 140.0 → **"compressed"** label. Pre-r125 same data would have shown "breakout" via tempo_ratio 2.3× ≥ 1.5 EUR-baseline. **This is the EXACT case the trader R28 r123 YELLOW-2 highlighted** : XAU high tempo_ratio = false-positive breakout under EUR-calibrated global thresholds. Post-r125, XAU's own 60-day distribution correctly says 124 bp is below the asset's own quiet-day boundary (p25 = 140).
- Chart aria-label = "Lecture intraday XAU/USD — ouverture 00:01 Paris à 4480.95, prix actuel 4496.33 (+0.34%), range jour 124 points de base, Londres 66 points de base, tempo compressé (2.3× vs typique 30 jours)."

### HONEST SCOPE (lesson #1/#11/r106-a, causation≠proof)

- **r125 EMPIRICAL DEMONSTRATION across both assets** : both EUR (27 bp) AND XAU (124 bp) showed identical "Compressé" labels post-r125, BUT for different reasons — EUR's 27 bp is below EUR's own p25 (31.7), XAU's 124 bp is below XAU's own p25 (140.0). The label STRING is the same ("Compressé") but the underlying empirical justification is asset-specific. This is the calibration the r125 atom enables.
- 1 console error on EUR / 10 console errors on XAU — both within the pre-existing r111-spawn-task vendor-chunk variability domain (r120: 9err, r121: 0, r122: 0, r123: 1, r124: N/A, r125: 1+10). ZERO r125 code in any stack trace. The XAU console-error count is on the higher end of the chunk-skew distribution but consistent with the pre-existing defect class. **flag-not-fix #11 NOT re-scoped NOT re-claimed**.
- A transient 502 Bad Gateway hit the first EUR navigation (~10s after deploy Step 5) — cloudflare quick-tunnel re-stabilization lag post-service-restart. Resolved on retry 22s later. Documented in the witness scope.

## Doctrine / lessons applied

- **lesson #21 (r124) ROADMAP-driven execution** : r125 = the canonical `docs/ROADMAP.md` §4 r125 top-default row "per-asset tempo recalibration", picked NOT from the paste-prompt menu alone but from the binding ROADMAP §3 reference. The ROADMAP discipline (created r124) is empirically validated by r125.
- **lesson #20 (r123) POINT FONDAMENTAL → R59-AUDIT first** : applied here as "ROADMAP §3 + §4 → SSH empirical calibration → derive thresholds" instead of pattern-matching default thresholds.
- **lesson #11 calibrated-honesty** : the r123 trader R28 YELLOW-2 honest disclosure ("EUR-calibrated, per-asset deferred to r124+") is now RESOLVED with empirical data. The new docstring is itself a calibrated-honesty artifact (flags SPX n=8 small sample, XAU p10=0.0 weekend filter, 60-day short window → r126+ auto-recalibration).
- **doctrine #9 anti-accumulation SSOT** : `TEMPO_THRESHOLDS_BY_ASSET` is the single source. `DEFAULT_TEMPO_THRESHOLDS` literal declared ONCE, referenced TWICE — pattern verified.
- **doctrine #14 gate on committed shape** : re-gated post YELLOW-1/2 test additions ; 171 tests pass.
- **r122 lesson #19 SSG bake-in** : N/A — `/briefing/[asset]` is `ƒ Dynamic` per r122 carry-through, the per-asset threshold lookup happens at SSR render-time per request.
- Voie D + ADR-017 N/A held cross-round (39 → 40 rounds).

## Backlog noted (NOT r125 scope — flagged per honest-scope discipline)

- **r126+ auto-recalibration cron** : currently thresholds are HARDCODED from the 2026-05-20 60-day SSH snapshot. Wire a Hetzner-side weekly cron to re-derive + push to a `tempo_thresholds` table consumed via API ("Mission centrale Axis-7 auto-amélioration" partial extension). Per ROADMAP §5.
- **r126+ extend window to 90/180 days** : 60-day window is short, SPX500 had n=8 only. Extend for more stable percentiles.
- **r126+ tempo cross-asset matrix on `/today`** : surface 5 assets' tempo at once (ROADMAP §4 r127+).
- **r127+ Polymarket × DXY synthesis panel** (ROADMAP §4).
- **r128+ real-time event reactivity** (ROADMAP §4, Axis-5).

## Files

- `apps/web2/lib/sessionPulse.ts` (+`TempoThresholds` interface + `DEFAULT_TEMPO_THRESHOLDS` literal + `TEMPO_THRESHOLDS_BY_ASSET` const-record with 5 priority assets + `tempoLabelByAsset` pure function + `derivePulse` asset param + tempo_label derivation switch)
- `apps/web2/__tests__/sessionPulse.test.ts` (+13 new tempo tests : 11 per-asset + boundary + decoupling ; -4 r123 ratio-based ; -hourlyVol helper + imports)
- `apps/web2/app/briefing/[asset]/page.tsx` (+`normalisedAsset` arg to derivePulse, +5-line comment block documenting r125)
- `docs/decisions/ADR-099-north-star-architecture-and-staged-roadmap.md` (+§Impl(r125) with empirical data table + per-asset thresholds + MEASURED Reviews/Verification)
- `docs/SESSION_LOG_2026-05-20-r125-EXECUTION.md` (this)

## Next (r126) — per ROADMAP.md §3+§4 promotion

The r125 atom closes the per-asset tempo recalibration. r126 default options per ROADMAP §4 :

- **r126 top-default candidate** : auto-recalibration cron (the r125 honest-scope flag "thresholds HARDCODED from 60-day snapshot" → wire Hetzner-side weekly auto-recalibration, ROADMAP §5 Axis-7 hook).
- r126 alt : revalidate cleanup (r122 carry), SSG-audit (r122 lesson #19 backlog), Polymarket × DXY synthesis (ROADMAP §4 r127+).

**Default sans pivot per doctrine #10 + lesson #21 (r124 ROADMAP-driven execution)** : the canonical `docs/ROADMAP.md` §3 binding reference will be updated by this close (r125 done → r126 top-default promoted = auto-recalibration cron OR per ROADMAP §4 alt options). The next round opens with §3 as the binding "immediate next".
