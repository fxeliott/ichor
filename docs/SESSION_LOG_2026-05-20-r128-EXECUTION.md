# Round 128 — Execution log

> **Date** : 2026-05-20 (4th round of the day, after r125→r126→r127)
> **Worktree** : `D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`
> **Branch** : `claude/friendly-fermi-2fff71`
> **Round type** : Tier 4 production deploy + Playwright DUAL witness (Mission Axis-7 ACTIVATION)
> **HEAD pre-r128** : `cbbbbaa` (r127 close, 93 ahead `origin/main` `1909ca0`)
> **HEAD post-r128** : `<commit-hash>` (1 commit doc-only, 94 ahead `origin/main`)
> **Production state shift** : alembic 0050 → **0051 LIVE** + 5 rows in `tempo_thresholds` + r127 wire LIVE on CF tunnel

## §A — Atom summary

r128 **activates** the r126+r127 stack on Hetzner production. The dormant-but-safe code-only landed artifacts from r126 (backend) + r127 (frontend wire) are now LIVE :

- Migration 0051 applied → table `tempo_thresholds` exists with 6 CHECK constraints
- Backend code rsync'd → /v1/tempo-thresholds endpoint returns 200 with Cache-Control header
- Cron timer LIVE → next fire Sun 2026-05-24 04:01:11 CEST
- Feature flag flipped → `tempo_recalibration_collector_enabled = true`
- Manual first run → 5 assets recalibrated and inserted (n=8-16 each, 90d window)
- Frontend deployed → r127 wire on the CF tunnel
- Playwright DUAL witness GREEN → EUR + XAU briefings rendering "tendance" label sourced from API-fed thresholds

**Production deploy chain** (~17 min including 3 SSH-timeout retries) :

1. scp migration 0051 → /opt/ichor/api/src/migrations/versions/
2. ssh alembic upgrade head (0050 → 0051)
3. file-by-file scp of 7 r126+r127 source files (pivot from tar-over-ssh after 3 timeouts)
4. ssh systemctl restart ichor-api + /healthz=200 + /v1/tempo-thresholds=200
5. scp + bash register-cron-tempo-recalibration.sh → timer LIVE
6. psql feature flag flip (`key`, NOT `name` — caught via R59 \d feature_flags)
7. systemctl start ichor-tempo-recalibration.service → 5 rows inserted
8. Cache-Control header verified : `public, max-age=300, stale-while-revalidate=900`
9. redeploy-web2.sh (1 SSH timeout retry) → local=200 public=200
10. Playwright EUR + XAU witness → both render "tendance" label LIVE

**Empirical drift from r125 60d to r128 90d** :
| Asset | r125 (60d) | r128 (90d) | Drift bp |
|-------|-----------|-----------|----------|
| EUR_USD | 59.1/54.2/47.2/31.7 | 59.14/54.96/48.38/35.12 (n=16) | +0-3 |
| GBP_USD | 95.8/71.2/64.5/41.6 | 95.78/71.23/66.00/48.09 (n=16) | +0-6 |
| XAU_USD | 307.4/273.7/177.2/140.0 | 307.42/273.72/199.33/155.55 (n=16) | +0-22 |
| SPX500_USD | 126.0/112.3/102.7/77.2 | 126.01/112.34/102.70/77.22 (n=8) | ~0 |
| NAS100_USD | 180.7/166.4/138.7/114.1 | 180.71/166.45/138.75/114.06 (n=12) | ~0 |

Format: breakout(p90) / active(p75) / trending(p50) / range_bound(p25)

## §B — Playwright DUAL witness (MEASURED on public CF tunnel)

**EUR_USD** (`/briefing/EUR_USD?cb=r128-witness-2`) :

- Heading "Aujourd'hui · mercredi 20 mai" ✓
- Ouverture 00:00 Paris → Maintenant 18:08 ; 1.16048 → 1.16250 (+0.17%)
- **Range jour 54 bp + Londres 55 bp + Tempo "tendance" (3.1× vs typique 30 jours)**
- 54 bp falls between API-fed trending=48.38 and active=54.96 → "trending" ✓
- 0 console errors on this nav

**XAU_USD** (`/briefing/XAU_USD?cb=r128-witness-xau`) :

- Heading "Aujourd'hui · mercredi 20 mai" ✓
- Ouverture 00:01 Paris à 4480.95 → Maintenant 18:09 à 4533.04 (+1.16%)
- **Range jour 221 bp + Londres 191 bp + Tempo "Tendance" (3.0× vs typique 30 jours)**
- 221 bp falls between API-fed trending=199.33 and active=273.72 → "trending" ✓
- 1 console error = React `#418` hydration mismatch (r111-spawn-task chunk-skew variability flag-not-fix #11, pre-existing pattern documented in MEMORY.md since r111)

**Transparent-on-stable-calibration property EMPIRICALLY confirmed** : the r127 vitest test pinning "XAU 200 bp + API-fed thresholds → trending label" is realized LIVE on prod. The API thresholds differ from r125 hardcoded by 1-22 bp depending on percentile, but produce the SAME labels on today's ranges (54 bp + 221 bp). The wire is INVISIBLY swapping the source of truth from compile-time const to runtime DB without behavior change because the dispersion is within-bracket.

## §C — Doctrines applied + lesson codified

**Applied** :

- doctrine #1 (R59 inspect-first reality wins) — verified `feature_flags` schema before INSERT (`key` not `name` caught from paste-prompt v47 drift)
- doctrine #2 (strict scope) — kept r128 to "deploy + witness", no scope creep
- doctrine #6 (single-step ; no amend)
- doctrine #9 (anti-accumulation + dated §Impl append)
- doctrine #11 (calibrated honesty — XAU console error flagged-not-fix with reason)
- doctrine #14 (build-gate on COMMITTED shape ; r126+r127 already gated, r128 = pure activation)
- lesson #22 (worktree-mismatch protocol)
- lesson #23 (Hetzner deploy chain mostly §D-4 but autonomously runnable via redeploy-\*.sh scripts)

**Codified new** :

- **lesson #24 (r128)** : when SSH is unstable mid-tar transfer (3 timeouts observed during r128 deploy), pivot from `redeploy-api.sh` tar-over-SSH to file-by-file `scp` with `ServerAliveInterval=5`. The pattern trades throughput for resilience. Future enhancement : add `--mode=fallback-scp` flag to `redeploy-api.sh` that auto-pivots if the initial tar handshake fails.

## §D — Mission centrale Axis-7 status post-r128

✅ **PRECONDITION (r126)** : per-asset tempo recalibration auto-cron infrastructure
✅ **CONSUMER WIRE (r127)** : frontend lookup chain with 3-layer fallback
✅ **ACTIVE-ON-PROD (r128)** : LIVE deploy + 5 rows + Playwright DUAL witness GREEN

**Mission centrale Axis-7 is FULLY ACTIVE** for the first time. The auto-improvement loop closes : measure (cron percentile fire weekly Sunday) → store (tempo_thresholds historical trail) → consume (briefing tempo label) → recalibrate (next Sunday).

⏳ **r129 candidate** : threshold drift detector (auto-alert when this-week thresholds deviate by N% from N-weeks-ago) ; ADR-104 data-honesty staleness banner on `<TodaySessionPulse>` (surface `computed_at` + `sample_size` + `window_days` metadata that r127 currently drops in the flatten — the banner hook comment in `lib/api.ts:getTempoThresholds` already pinpoints the re-plumbing point).

## §E — r129 candidate (per ROADMAP §3 promotion)

**r129 binding default candidates** :

1. **ADR-104 data-honesty staleness banner** on `<TodaySessionPulse>` — surface `computed_at` (the `tempo_thresholds.computed_at` of the latest recalibration), `sample_size`, `window_days` so Eliot can see "recalibré il y a N jours, n=K, 90j window". Effort S-M (re-plumb the fetcher to preserve the metadata + add a `<small>` line on the Pulse panel). Backend already returns the metadata via the API ; just a flatten-shape change in `lib/api.ts` + a new prop on the panel.
2. **Tempo drift detector** — weekly cron that compares this-week's thresholds against last-week's + alerts on >N% drift. Effort M (new collector cron + `auto_improvement_log` schema extension to add `tempo_drift` loop_kind + structlog alert).
3. **Tempo cross-asset matrix on `/today`** — surface all 5 priority assets' current tempo + thresholds at once on the `/today` page. Effort M.
4. **AUD_USD revival** (Mission centrale gap from r46 close + r49 honest disclosure) — MYAGM1CNM189N still dead per FRED ; find alternative China money supply LIVE series. Effort M-L.
5. **Polymarket × DXY synthesis panel** (Mission centrale Axis-4 gap from r123 audit) — dedicated themed panel surfacing Polymarket-themed positioning vs DXY divergence. Effort M.

R59-AUDIT first to confirm honest scope on chosen path.
