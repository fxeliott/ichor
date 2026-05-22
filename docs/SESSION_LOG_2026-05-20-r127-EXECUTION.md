# Round 127 — Execution log

> **Date** : 2026-05-20 (same operating day continuation r125 → r126 → r127)
> **Worktree** : `D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`
> **Branch** : `claude/friendly-fermi-2fff71`
> **Round type** : Tier 4 frontend WIRE (no NEW visible UI component — the existing `<TodaySessionPulse>` panel's visual contract from r123 is preserved verbatim, only the threshold source changes)
> **HEAD pre-r127** : `d460b97` (r126 close, 92 ahead `origin/main` `1909ca0`)
> **HEAD post-r127** : `<commit-hash>` (1 commit, +254 / -9 LOC, 93 ahead `origin/main`)

---

## §A — Atom summary

r127 ships the **frontend consumer wire** for the r126 backend `/v1/tempo-thresholds` endpoint — closing the r126 split-atom (backend code + frontend wire BOTH landed code-only on this branch). Per **doctrine #11 calibrated honesty** : "the wire ships" is precisely shipped ; "the wire is LIVE on production" is honestly NOT-YET because the Hetzner deploy chain crosses **ADR-099 §D-4 boundary of autonomy** (Eliot territory : PR merge → rsync → alembic upgrade → cron register → feature flag flip + Playwright witness).

**What ships this round** :

1. **`apps/web2/lib/sessionPulse.ts`** — exported `TempoThresholds` interface + added 5th param `thresholdsOverride?` to `derivePulse(...)` + `tempoLabelByAsset` reads override-first via 3-layer lookup chain (override → r125 hardcoded → DEFAULT).
2. **`apps/web2/lib/api.ts`** — new `TempoThresholdsForAsset` interface (structural mirror, drift-guard test) + `getTempoThresholds()` async fetcher (300s ISR, transform list→map, null on error/empty, `console.info` distinguishes cold-state from API-down per Y-3).
3. **`apps/web2/app/briefing/[asset]/page.tsx`** — `getTempoThresholds()` added to existing Promise.all + `tempoThresholdsLive ?? undefined` passed to `derivePulse(...)`.
4. **`apps/web2/__tests__/sessionPulse.test.ts`** — +6 new tests covering all 4 layers of the fallback chain + XAU live-transparency + TempoThresholds drift-guard regex with `import.meta.url`-resolved paths (MF-1 fix).
5. **ADR-099 §Impl(r127) append** + this SESSION_LOG + ROADMAP §1 sync + §3 promotion to r128.

**What is DEFERRED to r128** (Eliot-gated per ADR-099 §D-4) :

- GitHub PR merge `claude/friendly-fermi-2fff71` (93 ahead) → `main`
- Hetzner rsync sync of the new files
- `alembic upgrade head` (0050 → 0051)
- `register-cron-tempo-recalibration.sh` (creates `ichor-tempo-recalibration.timer`)
- Feature flag flip : `tempo_recalibration_collector_enabled = true`
- Smoke verify via `psql` + `systemctl list-timers` + `journalctl`
- Playwright DUAL witness on the CF tunnel (EUR + XAU briefing → verify thresholds come from API rather than hardcoded)

**What stays infrastructure-level** : both r126 backend + r127 frontend wire are landed code-only on this branch. On production today, the briefing page consumes the r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET` (the API call returns 404 since the endpoint isn't registered in deployed `main` lineage → fetcher returns null → fallback chain holds). The data-honesty invariant is preserved : the worst case is "label is exactly what it was at r125 ship", never "label is missing".

---

## §B — R59-AUDIT findings (pre-implementation)

Lecture en parallèle de :

- **`lib/api.ts`** : `apiGet<T>` pattern + existing `getHourlyVol` / `getSessionStatus` / `getCorrelations` as fetcher prior art ; 300s ISR via `{ revalidate: 300 }` matches backend Cache-Control max-age.
- **`app/briefing/[asset]/page.tsx`** : existing 14-item Promise.all + `derivePulse(intraday, hourlyVol, sessionStatusSsr, normalisedAsset)` r125 call site → r127 = 15-item Promise.all + 5th arg.
- **`lib/sessionPulse.ts`** : r125 state — `TempoThresholds` interface private + `tempoLabelByAsset(range_bp, asset)` + `derivePulse(..., asset = "")`.
- **`__tests__/sessionPulse.test.ts`** : vitest `environment:"node"` pure-logic pattern + ADR-017 canary regex test pattern.
- **Hetzner state** : `/opt/ichor/api/src/migrations/versions/` head = `0050_session_card_degraded_inputs.py` (r126 `0051_tempo_thresholds.py` NOT yet rsync'd) + `alembic current` reports `0050 (head)` + no `.git` repo on `/opt/ichor/api/` (rsync-deployed externally).

**doctrine-#9 anti-accumulation verified** : zero pre-existing `getTempoThresholds*` or `lib/data/*` files. The fetcher lands in `lib/api.ts` per project convention (NOT a new `lib/data/` directory — would create accumulation against an existing single-file convention).

---

## §C — Review pass (classe-trigger : frontend WIRE with NO new visible component → trader + code-reviewer, NO ui-designer / a11y)

**ichor-trader R28** : GREEN / MERGE 0 RED / 0 Critical / 0 MUST-FIX. ADR-017 boundary clean (descriptive percentile baselines, never predictive). Voie D held (zero `import anthropic`). 2 single-reviewer YELLOWs dissolved on inspection (DISTINCT ON race + Mission Axis-7 framing) + 2 NIT applied (r128+ banner hook comment + transparent-on-stable wording).

**code-reviewer** : MUST-FIX × 1 (drift-guard test cwd fragility) + 5 YELLOW + 3 NIT. **MF-1 + Y-1 + Y-3 + N-1 APPLIED same-commit + re-gate**. Y-2 (`Record<string, T>` → `Partial<Record<AssetCode, T>>`) + Y-5 (backward-compat edge) flag-not-fix-with-reason : single-reviewer + cross-module refactor + project-convention consistent. Y-4 LIVE wording calibrated via **doctrine #11 calibrated honesty** ("API-fed (≤5min CDN lag)" replaces any "LIVE" claim).

**Concordance** : 0 concordant YELLOW (no overlap between trader + code-reviewer YELLOW lists). Single-reviewer YELLOWs : applied if cheap + load-bearing (MF-1 + Y-1 + Y-3 + N-1), flag-not-fix-with-reason if cross-module scope creep (Y-2 + Y-5) or wording calibration (Y-4 via doctrine #11).

---

## §D — Verification (MEASURED, lesson #1)

- **tsc --noEmit** : exit 0 (zero errors).
- **eslint --max-warnings 0** on 4 changed files : exit 0.
- **vitest run** : 8 files / **177 tests pass** (was 171 r125-baseline + 6 r127 = 177 ; r126 web2 NULL).
- **vitest run **tests**/sessionPulse.test.ts** : 30 tests / 536ms (was 24 + 6 r127 = 30).
- **next build** : ✓ Compiled successfully (route table unchanged — briefing/[asset] = ƒ Dynamic).
- **Hetzner state verified pre-commit** : `alembic current` reports `0050 (head)` → r126 migration NOT yet on prod fs ; the wire targets a 404 today → fallback chain holds.
- **Hetzner deploy** : DEFERRED per ADR-099 §D-4 boundary. r128 candidate or Eliot-manual step.

---

## §E — Doctrines applied + lessons codified

**Applied** :

- doctrine #1 (R59 inspect-first → reality wins) — verified Hetzner has no git + alembic still 0050, scoped deploy as Eliot-gated step rather than autonomous SSH.
- doctrine #2 (strict scope) — `Record<string, T>` tightening to `AssetCode` union deferred to r128+ (Y-2 flag-not-fix).
- doctrine #4 (concordance) — 0 concordant YELLOW ; single-reviewer YELLOWs applied if cheap + load-bearing.
- doctrine #6 (single-step prettier 2e-passe).
- doctrine #9 (anti-accumulation : fetcher lands in `lib/api.ts` per existing convention, NOT new `lib/data/` directory).
- doctrine-#9 coord-math ledger UNCHANGED (wire change, NOT visual SSOT).
- **doctrine #11 calibrated honesty** — "API-fed (≤5min CDN lag)" replaces "LIVE" wording (the wire is weekly cron + ISR, not streaming).
- doctrine #14 (build-gate on COMMITTED shape).
- doctrine #17 (parallel reviewers classe-trigger — backend = 3, frontend NEW component = 3, frontend WIRE = 2).
- lesson #21 (canonical ROADMAP drives round default).
- lesson #22 (worktree-mismatch protocol, applied since r126).

**Codified new** :

- **lesson #23 (r127)** : Hetzner deploy chain is ADR-099 §D-4 Eliot territory when the code path is "rsync-deployed-from-external + no-git-on-server". Even if SSH is authorized via prompt-cadre autonomy, the production deploy mechanic itself is not fully autonomous — the rsync source + the deploy-blue-green.sh trigger live outside `/opt/ichor/` on the server. Default = ship code-only landed artifact + flag the Hetzner activation as the next round candidate. The wire's dormant-but-safe state (404 → fallback chain) makes this split safe.

---

## §F — r128 candidate (per ROADMAP §3 promotion)

**r128 binding default** = **Hetzner production deploy of the r126+r127 stack + Playwright DUAL witness** :

1. GitHub PR merge `claude/friendly-fermi-2fff71` (93 ahead) → `main`.
2. Hetzner rsync sync of new files (8 r126 backend files + 4 r127 wire files).
3. `cd /opt/ichor/api/src && source /etc/ichor/api.env && /opt/ichor/api/.venv/bin/alembic upgrade head` (0050 → 0051).
4. Smoke verify schema : `sudo -u ichor psql -d ichor -c "\d tempo_thresholds"` → expect 6 CHECK constraints + compound desc index.
5. `bash /opt/ichor/scripts/hetzner/register-cron-tempo-recalibration.sh` → creates `ichor-tempo-recalibration.timer` (Sun 04:00 Paris).
6. Feature flag flip : `psql -d ichor -c "INSERT INTO feature_flags(name, enabled, rollout_pct) VALUES ('tempo_recalibration_collector_enabled', true, 100) ON CONFLICT (name) DO UPDATE SET enabled=true, rollout_pct=100;"`.
7. Manual first run (don't wait Sunday) : `systemctl start ichor-tempo-recalibration.service` + verify via `journalctl -u ichor-tempo-recalibration.service` + `psql -d ichor -c "SELECT asset, breakout_bp, active_bp, trending_bp, range_bound_bp, sample_size, window_days, computed_at FROM tempo_thresholds ORDER BY computed_at DESC LIMIT 10"` (expect 5 assets each n=12-16).
8. Reload `ichor-api.service` via systemctl OR blue-green deploy-blue-green.sh (depending on Eliot's deploy preference).
9. `bash scripts/hetzner/redeploy-web2.sh` to push the frontend wire.
10. **Playwright DUAL witness** on the CF tunnel : `/briefing/EUR_USD` + `/briefing/XAU_USD` — verify the network log shows `/v1/tempo-thresholds` 200 + the tempo label uses the API-fed thresholds (not the r125 hardcoded values, which would be byte-identical for stable calibration but the DevTools network shows the API hit).

**r128 alternative** (if Eliot prefers split-deploy) : backend deploy only (steps 1-7) + r129 = frontend deploy + witness.
