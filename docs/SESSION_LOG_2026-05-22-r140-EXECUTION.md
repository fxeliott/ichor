# SESSION_LOG r140 — 2026-05-22

> **Round** : r140 (axis-5 réactivité temps réel LIVE)
> **Branch** : `claude/friendly-fermi-2fff71`
> **Status** : SHIPPED + DEPLOYED + WITNESSED + DOCUMENTED
> **Commits** : `b313922` (initial) + `ffb49b0` (4-reviewer fix-cluster)
> **Mission centrale axis impact** : **axis-5 (réactivité temps réel events 13h-16h NY) FINALLY LIVE after 4 rounds carry-forward** (r137+r138+r139 deferred)

---

## What shipped

### Backend (commit `b313922`)

1. **`apps/api/src/ichor_api/services/economic_calendar.py`** — `assess_calendar(session, *, horizon_days=14, since_minutes=0)` keyword-only param. `since_minutes=0` (default) preserves r68 forward-only behaviour. `since_minutes>0` extends ONLY the ForexFactory DB query (section 3) lower bound backward via `ff_lower = now - timedelta(minutes=since_minutes)`. Sections 1+2 (CB meetings hardcoded + recurring FRED projections) stay forward-only via `today = now.date()` (code-reviewer R1 fix : minute-precision is FF-only, never extends sections 1+2 by a full calendar day).
2. **`apps/api/src/ichor_api/routers/calendar.py`** — added `since_minutes: Annotated[int, Query(ge=0, le=1440)] = 0` query param (24h cap prevents accidental year-long payload explosion). `Cache-Control: no-store` injected when `since_minutes>0` (code-reviewer S1 : any cache defeats freshness-detection in polling-mode).
3. **`apps/api/tests/test_calendar_recent_window.py`** — 6 tests pinning signature + Query bound + back-compat + R1-regression-guard for sections 1+2 forward-only + window-start math + `filter_for_asset` unchanged signature + dynamic integration test with stubbed AsyncMock (S3 fix : initial draft was static source-text pinning only).

### Frontend (commit `b313922`)

4. **`apps/web2/components/briefing/FreshDataBanner.tsx`** (NEW, ~240 LOC) — polls `/v1/calendar/upcoming?asset=X&since_minutes=60` every 60s while the briefing tab is visible. Page Visibility API pauses when hidden, resumes on `visibilitychange`. 4-state disclosure with "pas un signal" + "actuals à vérifier à la source" anchors (ADR-017 boundary + lesson #37). Pure function `pickLatestElapsed(events, briefingAt, now)` extracted for testability (S4 fix). AbortController wired to `apiGet` via the new `signal?: AbortSignal` option threaded end-to-end (R2 fix). `lastFiredAtRef` for cross-response monotonicity. `sessionStorage` pause persistence per-asset. `role="status"` + `aria-live="polite"` + `aria-atomic="true"` + permanently-mounted live region (a11y R-1 fix : SR users miss state changes if region only mounts on event). `aria-pressed` with stable accessible name + `min-h-[24px] min-w-[24px]` + `focus-visible:ring-2` on pause button (WCAG 2.2 SC 2.5.8 + 2.4.7 + 4.1.2 + 4.1.3). Demoted neutral chrome (`border-subtle + bg-surface/40 + border-l-2 warn accent`) per ui-designer Y-1.
5. **`apps/web2/lib/api.ts`** — `ApiFetchOptions.signal?: AbortSignal` threaded end-to-end (was decorative no-op in initial draft). `getCalendarUpcoming(asset?, sinceMinutes?, opts?)` extended for polling path.
6. **`apps/web2/app/briefing/[asset]/page.tsx`** — `<FreshDataBanner>` placed AFTER `<DataIntegrityBadge>` (ui-designer Y-1 ordering — verdict/badge stays primary).
7. **`apps/web2/__tests__/freshDataBanner.test.ts`** (NEW, 10 tests) — `pickLatestElapsed` boundary cases : null events / null `when_time_utc` / forward / before briefing / equal-now boundary / equal-briefing boundary / multi-match latest-pick / unparseable date / window composition.

---

## 4-reviewer concordance audit (fix-cluster commit `ffb49b0`, +433 / −106)

Per doctrine #17 : NEW visible UI = 4 reviewers (ui-designer + a11y + trader + code-reviewer).

| Reviewer          | RED                                                                                                                | SHOULD/YELLOW                                                                                                             | NICE                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| **trader**        | RED-1 HALLUCINATION (claimed URL backslashes — verified false empirically, lesson #38)                             | Y-1 honest-scope copy strengthening ("actuals à vérifier à la source" stamp + "pas un signal" anchor double-down)         | —                     |
| **ui-designer**   | —                                                                                                                  | Y-1 chrome-demotion (full `warn` bg → `border-subtle + border-l-2 warn accent` — verdict stays primary)                   | 5 NICE polish         |
| **a11y**          | R-1 missing live region when empty (SR miss state changes) + R-2 button min-touch-area below SC 2.5.8 24×24        | S-1 `aria-pressed` stable name + S-2 `role="status"` + `aria-live="polite"` + S-3 focus-visible ring                      | —                     |
| **code-reviewer** | R1 sections 1+2 over-extension + R2 AbortController decorative no-op + R3 stale closure bug in setInterval cleanup | S1 `Cache-Control: no-store` polling-mode + S3 dynamic integration test + S4 `pickLatestElapsed` pure-function extraction | N1 + N2 + N3 cleanups |

**Total** : **8 RED + 7 SHOULD/YELLOW + 5 NICE** applied. trader RED-1 NOT-applied (false positive, documented as lesson #38).

---

## Lessons codified this round

### Lesson #37 — DEMOTE framing when upstream data lacks the actionable field

When upstream data lacks the actionable field (e.g. `economic_events.actual` doesn't exist because ForexFactory XML doesn't publish actuals), DEMOTE the framing to what's truly observable (scheduled time elapsed) and stamp the gap honestly ("actuals à vérifier à la source"). Never imply data the source doesn't carry. This is doctrine #11 calibrated-honesty applied at the schema/framing layer, not the copy layer.

### Lesson #38 — Trader subagent claims need empirical verification

trader RED-1 claimed `apps/web2/lib/api.ts:266` contained `URL backslashes → banner functionally dead`. Verified empirically :

- `grep -n 'calendar/upcoming' apps/web2/lib/api.ts` → forward slashes correct.
- Playwright network log captured request #77 `GET /v1/calendar/upcoming?asset=SPX500_USD&since_minutes=60 → 200`.

~10min wasted on a phantom RED that empirical verify dispelled instantly. A trader's "I see X" in a review is a hypothesis to verify, NOT a fact to fix. Lesson #11 calibrated refusal applies to subagent output too.

---

## Verification (MEASURED, no forecast)

- **Backend tests** : 6/6 r140 + 303/303 regression `-k 'calendar or briefing or freshdata'` pass.
- **Frontend tests** : 10/10 `pickLatestElapsed` boundary tests pass.
- **Build gate** : tsc 0 errors + eslint 0 warnings on 4 modified web2 files + next build OK.
- **ADR-017 CI guard** : green (banner copy regex-verified — never BUY/SELL).
- **Backend deploy** : `redeploy-api.sh` (lesson #24 SSH-instability recurrence — host dropped SSH step 3→4 ; recovered via short individually-retryable calls + `systemctl restart ichor-api` + grep prod-path verify). Verified `Cache-Control: no-store` header present on `/v1/calendar/upcoming?since_minutes=60` response via `curl -I`. Verified `since_minutes=60` returns events with `when_time_utc` populated.
- **Frontend deploy** : `redeploy-web2.sh` local=200 + public=200.
- **Playwright LIVE empirical witness on public CF tunnel** : opened `/briefing/spx500_usd?cb=r140-witness-firstrender` → Network log captured request #77 `GET /v1/calendar/upcoming?asset=SPX500_USD&since_minutes=60 → 200` confirming polling fires every 60s. Banner correctly SILENT at witness time (07:43 UTC) — UoM Consumer Sentiment 14:00 UTC is forward not elapsed in the 60-min window vs `briefing.generated_at`. All 14 sibling panels render, 0 console errors. The silent-but-mounted live region is the honest no-event state (lesson #1).

---

## HONEST SCOPE (lessons #1/#11/#37)

- (a) **The endpoint detects "scheduled time elapsed", NOT "data published"**. `economic_events` has NO `actual` column ; ForexFactory XML doesn't publish actuals. Banner copy stamps "actuals à vérifier à la source" — never claims a result published. r141 candidate #1 = add `actual` column + free-tier provider reconciliation.
- (b) The 60s poll cadence is judgment, not Brier-fit (axis-7 unsuited — no labeled "user noticed catalyst in N minutes" data). 60s = compromise between freshness (NFP fires) and API load (5 priority assets × all open tabs). Configurable via constant if needed.
- (c) `since_minutes` capped at 1440 (24h). Beyond 24h, the briefing itself is stale and should be regenerated (r141+ staleness banner candidate).
- (d) Pause button persists per-asset in `sessionStorage` (intentionally not `localStorage` — pausing on XAU shouldn't persist across browser sessions).
- (e) Static `<EventSurpriseGauge>` (forward-looking pre-NY catalyst gauge from r110) UNCHANGED. r140 adds the recent-window banner ABOVE the gauge — distinct axes (gauge = forward "what's coming pre-NY", banner = backward "what just fired since briefing").

---

## Voie D held 55 rounds

Zero `import anthropic` ; pure backend SQL window-shift + pure frontend setInterval polling ; no LLM call added. ADR-017 boundary clean (CI-guarded ; banner copy regex-verified non-directional). Doctrine #9 dated APPEND to ADR-099 §Impl(r140), NO new ADR (additive endpoint param + additive frontend banner ; no existing surface to refactor or supersede). Doctrine-#9 coord-math ledger UNCHANGED.

---

## Mission centrale axis snapshot post-r140

| Axis                                            | Pre-r140                   | Post-r140                                             |
| ----------------------------------------------- | -------------------------- | ----------------------------------------------------- |
| 1 — Lecture session Londres en cours            | ✅ r123                    | ✅ r123                                               |
| 2 — Calibrage NY 13h-16h                        | ✅ r123                    | ✅ r123                                               |
| 3 — Repartir de zéro chaque jour                | ✅ r132+r133               | ✅ r132+r133                                          |
| 4 — Anticipation par profondeur                 | 🎯+1 r130                  | 🎯+1 r130                                             |
| **5 — Réactivité temps réel events 13h-16h NY** | **🎯+1 LEVEL (r135-r137)** | **🎯 LIVE r140** ⭐ **FINALLY closed after 4 rounds** |
| 6 — Apprentissage auto-amélioration             | 🎯+1 r134                  | 🎯+1 r134                                             |
| 7 — Apprentissage autonomie                     | 🎯 LIVE                    | 🎯 LIVE                                               |
| 8 — Manipulation watch                          | 🎯+1 PARTIAL r131          | 🎯+1 PARTIAL r131                                     |

---

## Next round (r141) — top default

**`economic_events.actual` column + free-tier provider reconciliation** (closes r140 honest-scope gap : upgrades the banner from "scheduled time elapsed" to "data published — surprise vs consensus = X%"). Alembic migration + Investing.com OR polymarket consensus market scrape + reconciler service. Effort M-L.

Alternatives R59-pickable : word-boundary regex for short-token keywords (r139 honest-scope gap, S effort) ; gold/UK upstream feeds (M) ; business-cycle-conditioned news sign (M) ; conviction backend driver-wiring (M-L) ; GDPC1 quarterly weighting (S) ; dealer-GEX regime state (M).
