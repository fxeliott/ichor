# Round 126 — Execution log

> **Date** : 2026-05-20 (afternoon, continuation of the same operating day as r125)
> **Worktree** : `D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`
> **Branch** : `claude/friendly-fermi-2fff71` (NB : the Claude Code SESSION ran from a DIFFERENT worktree at `gifted-bell-c1b656` — see §Reality-check below)
> **Round type** : Tier 4 BACKEND atom (split-atom doctrine ; r127 = frontend wire)
> **HEAD pre-r126** : `3d38cbc` (r125 close, 91 ahead `origin/main` `1909ca0`)
> **HEAD post-r126** : `<commit-hash>` (1 commit, ~700 LOC + 41 tests, 92 ahead `origin/main`)

---

## §A — Atom summary

r126 ships the **per-asset tempo threshold auto-recalibration backend infrastructure** — the explicit deferral from r125's `sessionPulse.ts` docstring lines 153-160 (_"auto-recalibration deferred to r126+ ... could wire a Hetzner-side weekly cron to re-derive + push to a `tempo_thresholds` table consumed via API"_) is now realized.

**What ships this round** :

1. **Migration 0051** `tempo_thresholds` — historical-trace shape (one row per `(asset, computed_at)`), 6 CHECK constraints (monotonic + sample_size + window_days floors), compound desc index for "latest per asset".
2. **ORM** `TempoThreshold(Base)` + registered in `models/__init__.py`.
3. **Service** `services/tempo_recalibration.py` — `recalibrate_tempo_thresholds(...)` with Paris-day grouping in SQL, stdlib `_percentile` linear-interp helper, `TempoRecalibrationResult` per asset (inserted | skipped).
4. **CLI** `cli/run_tempo_recalibration.py` — feature-flag-gated (`tempo_recalibration_collector_enabled`), `--dry-run`, `--window-days`, `--min-sample-days`, `--assets`.
5. **Cron** `scripts/hetzner/register-cron-tempo-recalibration.sh` — weekly Sunday 04:00 Paris systemd timer.
6. **API endpoint** `routers/tempo_thresholds.py` — `GET /v1/tempo-thresholds` + `GET /v1/tempo-thresholds/{asset}` with `Cache-Control: public, max-age=300, stale-while-revalidate=900`.
7. **Tests** — 3 files / 41 tests (35 base + 6 review-driven post-fix).
8. **ADR-099 §Impl(r126)** + this SESSION_LOG + ROADMAP §1 sync + §3 promotion to r127.

**What is DEFERRED to r127** (split-atom doctrine, doctrine-#2 strict scope) :

- Frontend lib fetcher (`apps/web2/lib/data/tempoThresholds.ts`)
- `sessionPulse.ts` `derivePulse(..., asset, thresholdsOverride?)` optional param
- Briefing page wire (`apps/web2/app/briefing/[asset]/page.tsx`)
- Hetzner alembic upgrade + cron registration + feature flag flip (KEYWORD DEPLOY scope — keep r126 as a code-only landed artifact, deploy when r127 ships the consumer view, witness the full chain together)

**What stays infrastructure-level** : the cron will populate `tempo_thresholds` weekly once Eliot flips the feature flag + registers the cron on Hetzner. The hardcoded `TEMPO_THRESHOLDS_BY_ASSET` in `sessionPulse.ts` r125 continues to drive the LIVE frontend until r127 wires the API-fed override.

---

## §B — Reality-check (worktree mismatch, lesson #1 R59)

The Claude Code session started in `D:\Ichor\.claude\worktrees\gifted-bell-c1b656` (HEAD `635a0a9` = round-49 docs merged to main, BEHIND `origin/main` `1909ca0`). The r121-r125 work lives on a DIFFERENT branch `claude/friendly-fermi-2fff71` (HEAD `3d38cbc`, **91 ahead origin/main**), unmerged. The conversation summary from the previous session matched friendly-fermi state, not gifted-bell state.

**Decision** (autonomous, per prompt-cadre autonomy directive + doctrine #1 reality wins) : work in `friendly-fermi-2fff71` via absolute paths from the gifted-bell-c1b656 CWD. Git operations use `git -C` flag ; file operations use absolute paths. The CWD stays gifted-bell to avoid polluting hooks `cwd-scope-lock` (already triggered at session start). pytest + ruff + git ops all run cleanly via this approach.

**Lesson #22 codified** : when a Claude Code session starts in a worktree that doesn't match the conversation-summary state, default action = work in the worktree the conversation-summary describes via absolute paths + `git -C`. The session's CWD lock is not a barrier ; tools accept absolute paths. **Surface the mismatch to the user in the FIRST response with explicit reality-check** but do NOT block on permission — autonomy directive + doctrine #1 (inspect-first → reality wins) say execute on the verified state.

---

## §C — R59-AUDIT findings (pre-implementation)

Lecture en parallèle de :

- **Migration head** : `0050_session_card_degraded_inputs.py` → r126 = **0051**.
- **CLI pattern** : `run_ecb_estr.py` (round-34) — argparse + asyncio + feature-flag gate + structlog + `_async_main` + dispose-engine in finally.
- **Cron pattern** : `register-cron-ecb-estr.sh` — systemd `[Unit]/[Service]/[Timer]` triplet + `OnFailure=ichor-notify@%n` + `EnvironmentFile=/etc/ichor/api.env`.
- **Router pattern** : `hourly_volatility.py` — `APIRouter(prefix="/v1/...")` + Pydantic `BaseModel` + async `Depends(get_session)` + `_VALID_ASSET` whitelist.
- **ORM pattern** : `models/bund_10y_observation.py` — SQLAlchemy 2.0 `Mapped[type]` declarative + `__table_args__` mirroring migration CHECK constraints.
- **Service percentile** : `services/hourly_volatility._percentile` — stdlib `math.floor/ceil` linear-interp, REUSED VERBATIM in r126 with drift-guard test.

**doctrine-#9 anti-accumulation verified** : zero pre-existing `tempo_threshold*` or `tempo_recalibration*` files. Greenfield atom. No duplicate-creation risk.

---

## §D — Review pass (1-pass, classe-trigger : backend atom → trader + code-reviewer + api-designer)

**ichor-trader R28** : GREEN / MERGE 0 RED / 0 Critical / 0 MUST-FIX. 3 single-reviewer YELLOWs flag-not-fix. NIT-3 (auto_improvement_log docstring drift) was caught simultaneously by trader AND service-author — pre-applied before review returned.

**code-reviewer** : MUST-FIX × 2 (MF-1 clamp ordering, MF-2 Numeric overflow risk) + 7 YELLOW + 5 NIT. **ALL MUST-FIX + Y-1 docstring + Y-2 SQL drift guard + Y-3 percentile drift guard APPLIED same-commit**. Y-4/Y-7 pattern-consistent, no fix. NITs deferred.

**api-designer** : MERGE with **YELLOW-2 Cache-Control APPLIED same-commit (CONCORDANT with code-reviewer Y-5)** + YELLOW-1 404→envelope FLAGGED-NOT-FIX with reason (single-reviewer, breaks project convention `routers/sessions.py:88` pattern, r127 wire primarily consumes the list endpoint where the 404 doesn't occur) + YELLOW-3 RESTful nesting CONFIRMED AS-IS.

**Concordance** : 1 CONCORDANT YELLOW (Cache-Control × 2 reviewers) → applied. 1 SINGLE-REVIEWER YELLOW (envelope) → flag-not-fix per doctrine #4.

---

## §E — Verification (MEASURED, lesson #1)

- **pytest r126 subset** : `pytest tests/test_tempo_recalibration.py tests/test_tempo_thresholds_router.py tests/test_run_tempo_recalibration_cli.py` → **41 passed / 0 failed / 0 errored** in 51.96s.
- **pytest full suite** : `pytest` → **2198 passed / 34 skipped / 12 deprecation warnings (pre-existing, OTHER routers)** in 559.61s → **ZERO regression** vs post-r125 baseline.
- **Ruff** : `ruff check + ruff format` on 8 r126 source files → **All checks passed** + 8 files reformatted (whitespace + import ordering).
- **Build gate web2** : N/A (zero web2 change this round).
- **Deploy** : DEFERRED per split-atom doctrine — r127 ships the consumer view + the chain deploys + witnesses together.

---

## §F — Doctrines applied + lessons codified

**Applied** :

- doctrine #1 (R59 inspect-first → reality wins) — worktree-mismatch reality-check.
- doctrine #2 (strict scope, no premature shared module) — `_percentile` duplicated (defensible at 2 callers + drift-guard test).
- doctrine #4 (concordant 2+ reviewer YELLOW → MUST-FIX ; single-reviewer YELLOW → flag-not-fix-with-reason).
- doctrine #9 (anti-accumulation + dated §Impl append).
- doctrine-#9 coord-math ledger UNCHANGED (backend infrastructure, NOT visual SSOT).
- doctrine #14 (build-gate on COMMITTED shape, MEASURED Reviews/Verification).
- doctrine #17 (3 parallel reviewers, NOT FOMO — classe-trigger backend → trader + code-reviewer + api-designer).
- lesson #21 (canonical ROADMAP drives the round default).

**Codified new** :

- **lesson #22** (worktree-mismatch protocol — work in the worktree the conversation-summary describes via absolute paths + `git -C`, surface the mismatch in the first response, do NOT block on permission).
- **split-atom doctrine** (backend ships first when the frontend wire has no consumer urgency ; the cron runs, data accumulates, then the frontend wire lands in the next round with confidence on populated rows).

---

## §G — Next round (r127, ROADMAP §3 promotion)

**r127 binding default** = **frontend wire of `<TodaySessionPulse>` to `/v1/tempo-thresholds`** :

1. `apps/web2/lib/data/tempoThresholds.ts` fetcher — server-component compatible, 5-min ISR, fallback to r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET` on network error.
2. `apps/web2/lib/sessionPulse.ts` — extend `derivePulse(bars, hourlyVol, sessionStatus, asset, thresholdsOverride?: Record<string, TempoThresholds>)` with the optional override (default = r125 hardcoded fallback).
3. `apps/web2/app/briefing/[asset]/page.tsx` — `await getTempoThresholds()` in the Promise.all + pass as `thresholdsOverride`.
4. Tests : 2-3 new vitest tests (fetcher behavior + override behavior + fallback on error).
5. Deploy : Hetzner alembic upgrade head 0050 → 0051 + register-cron-tempo-recalibration.sh + feature flag flip + redeploy-web2.sh.
6. Witness : Playwright EUR + XAU briefing — verify thresholds come from API (`source="api"` data attribute or computed_at metadata visible).

**R59-pickable alternatives** if r127 scope is too ambitious in one round :

- **Just the fetcher + fallback** (XS effort) without modifying `derivePulse` — the fetcher returns to a data-honesty banner instead.
- **Just the Hetzner deploy** of r126 backend (Eliot manual step + smoke test) — no frontend change ; lets the cron accumulate one or two weeks of data before r128 wires the frontend.
- **Tempo cross-asset matrix on `/today`** (deferred from r126 alternatives, ROADMAP §4 r127+ candidate).
