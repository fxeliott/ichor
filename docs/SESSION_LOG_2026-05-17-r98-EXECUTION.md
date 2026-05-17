# SESSION_LOG 2026-05-17 — r98 EXECUTION (ADR-105 — market-closed gate for session-card generation)

**Round type:** ADR-099 §Tier-3 autonomy hardening — the r97
SESSION_LOG / pickup v26 binding default ("Tier 3 continues, R59 first,
pick highest value/effort: cron 365 d/yr holiday-gate (HIGH
blast-radius)"). doctrine #10 re-eval: (b) holiday-gate = highest
remaining Tier-3 product value (a closed-market card served as if it
were a live pre-session read is a real correctness/honesty defect) ;
(c) GBP Driver-3 = chicken-egg multi-round (defer) ; the §Cross-endpoint
test = lower value. No superior emergent gap. No pivot — executed (b).

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(pure calendar gate, Voie D). ADR-017 N/A (no signal — pure
`zoneinfo`/`date` math ; `test_invariants_ichor` 41/41 green confirms
no BUY/SELL leak). One coherent atomic increment ; `run_briefing`
symmetric gate explicitly deferred to r99 (not silently skipped).

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work in
`friendly-fermi-2fff71`. Verified: HEAD `8098513` (r97), 62 ahead, 0
uncommitted, pushed, PR #138 OPEN. Live == prompt failsafe.

## R59 reshaped the design (doctrine #3 — HIGH-blast collapsed to LOW)

2 parallel read-only R59 sub-agents (ichor-navigator card-gen
cron/`market_session` code-map + infra-auditor blast-radius/mechanism/
fail-safe). They converged decisively:

- The "HIGH blast-radius (2026-05-04 5-services-killed class)" framing
  is true ONLY for systemd mechanisms (b `ExecCondition=`, c
  `ExecStartPre=` → FAILED-state notifier storm, d cron-wrapper) —
  all rewrite the shared `@.service` template via `register-cron-*.sh`.
  **Mechanism (a) pure-Python guard at the batch entrypoint touches
  ZERO systemd/register-cron → blast-radius collapses to a normal
  additive API redeploy.** PRUDENCE is satisfied _by choosing (a)_,
  not by ceremony around a dangerous mechanism.
- Pressure-test killed the only (a) concern: the early-exit precedes
  every `HttpRunnerClient` POST ⇒ a no-op timer day consumes **zero
  claude-runner quota** (only a sub-second timer wake + one flag read).
- The signal SSOT (`compute_session_status`, r78) is "now"-only and
  its `.state` enum has no `ny_mid`/`ny_close` ⇒ the gate must decide
  on the `market_closed_fx`/`market_closed_us_equity` booleans at
  cron-fire time, NOT on `.state` (R59 nuance — would have been a bug
  if guessed from memory).

## ADR-before-code — NEW thin ADR-105 (doctrine #9)

This IS a real architectural decision (unlike r97 pure hygiene): the
gate mechanism, the FAIL-OPEN invariant, the per-asset weekend-vs-US-
holiday semantics, the flag-OFF ship, the deliberate rejection of the
2026-05-04 blast-class mechanisms. No existing ADR is this spec
(ADR-099 §T1.3 was the _signal_ r78 ; the _gate_ is new). Authored
[ADR-105](docs/decisions/ADR-105-market-closed-gate-session-card-generation.md)
Accepted (ADR-099 §D-4 standing autonomy mandate ; precedent
ADR-101/102/103/104 same-round Accepted).

## What shipped (5 modified + 1 new ADR ; one coherent increment)

- **`services/market_session.py`** — NEW pure SSOT extension:
  `_US_EQUITY_ASSETS = frozenset({"SPX500_USD","NAS100_USD"})` +
  `market_closed_for_asset(asset, status) -> bool`. Lives in the
  market-state SSOT (the docstring already carried the FX-vs-US-equity
  asset-class distinction) — anti-accumulation #4 (NOT a parallel gate
  module). Pure ; never raises on a well-formed `SessionStatus`.
- **`cli/run_session_cards_batch.py`** — gate block in `_run_batch`
  after the `_VALID_SESSIONS` check, before the batch header
  (filters `assets`; the existing loop/push/return consume the
  filtered tuple — minimal blast). Feature-flag
  `session_cards_market_closed_gate_enabled` (mirrors the proven
  `run_bundesbank_bund.py:42,79-87` fail-pattern: absent row ⇒
  `is_enabled`→False ⇒ inert). FAIL-OPEN: the whole gate wrapped in
  `try/except` ⇒ any error proceeds. **YELLOW-1 fix:** the full-skip
  `return 0` is STRUCTURALLY gated on a positive
  `market_closed_fx or market_closed_us_equity` ; an empty keep-set on
  a NON-closed market logs `*_anomaly_failed_open` + generates the
  FULL original set (fail-open made structural, not emergent).
- **`tests/test_market_session.py`** — +9 tests appended to the
  sibling module (anti-accumulation): 4 pure (weekend-all /
  us-holiday-only-equities / normal-none / `_US_EQUITY_ASSETS`
  membership-pin) + 5 async `_run_batch` (flag-OFF inert /
  weekend-skip-all / us-holiday-skip-only-equities / **FAILS-OPEN when
  is_enabled raises** / **YELLOW-1 anomaly: empty keep-set on OPEN
  market ⇒ fail-open generates all**).
- **NEW `docs/decisions/ADR-105-…md`** — thin child ; mechanism
  ranking ; FAIL-OPEN invariant ; per-asset semantics ; ship FLAG-OFF
  ; rejects the 2026-05-04 blast-class ; **YELLOW-2 honesty** added to
  §Negative (push-silence on a full skip ; CA-holidays not modelled —
  USD_CAD FX trades through, thinner liquidity ; NYSE half-days not
  modelled = under-suppression = the fail-safe direction ; the
  structural early-return).
- **`docs/decisions/README.md`** — `## Index` += ADR-105 row.
- **`docs/decisions/ADR-099-…md`** — dated `[r78/r79 + r98 DONE]`
  annotation on the §Coverage "Holiday/weekend = NOT handled" line
  (immutable-append, mirrors §T3.1/§T3.2 ; honestly partitions the
  FRONTEND signal half [r78/r79] vs the BACKEND gate half [r98] ;
  names `run_briefing` as the r99 residual).

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy on the full diff. **0 RED / 2 YELLOW / GREEN
-on-rest. Mergeable. Both YELLOW APPLIED pre-merge + regression-pinned.**

- **A FAIL-OPEN GREEN + YELLOW-1 APPLIED** — no path silently
  suppresses a real session _today_ ; but the early-return safety was
  _emergent_, not asserted. Fix applied: the full-skip `return 0` is
  structurally gated on a positive closed-state ; an empty keep-set on
  an OPEN market (a future SSOT regression) logs loud + generates all.
  Pinned by `test_gate_anomaly_empty_keepset_on_open_market_fails_open`.
- **A YELLOW-2 (doc) APPLIED** — push-silence on a full skip stated in
  ADR-105 §Negative (no false `OnFailure` storm — `SuccessExitStatus=0
1` by design ; no watchdog misled — verified none exists).
- **B per-asset trading correctness GREEN** — XAU correctly NOT
  US-equity (gold trades globally through US holidays) ; FX 24/5
  correct ; CA-holidays + NYSE-half-days scope cuts documented honestly
  (under-suppression = fail-safe).
- **C ADR-017 / Voie D / scope GREEN** — pure calendar, zero LLM,
  early-exit precedes every claude-runner call ; one atomic increment ;
  `run_briefing` honestly deferred.
- **D ADR-105 + ADR-099 annotation honesty GREEN** — no over-claim ;
  precise FRONTEND-vs-BACKEND partition ; "ships flag-OFF" not claimed
  as live-prod proof (lesson #11 bar met).

## Verification (3-witness for an additive, deliberately-INERT Hetzner ship)

The honest "marche exactement" for a flag-OFF ship is: deployed +
provably inert + the gate logic exhaustively unit-proven. The live
weekend/holiday skip is NOT pixel-witnessable because the flag is OFF
by design (Eliot's enable gesture, ADR-099 §D-4) — stated, not
over-claimed (the r96 DEGRADED-not-live-witnessed honesty pattern).

1. **Witness A — static gate (GREEN):** doctrine-#4 venv →
   `ichor_api`/`ichor_brain` resolve to the WORKTREE ; ruff check +
   `format --check` clean (3 files) ; **pytest 16/16**
   `test_market_session.py` (7 pre-existing + 9 new incl. fail-open +
   the YELLOW-1 anomaly) + **regression 50/50** (`test_invariants_ichor`
   41 [ADR-081 Voie-D/ADR-017] + `test_cftc_tff` 9 — zero doctrinal
   regression). `market_session` change is purely additive (existing 7
   tests unchanged-pass) ; the gate is additive before the loop.
2. **Deploy (additive, ADR-099 §D-4 autonomous):** vetted
   `scripts/hetzner/redeploy-api.sh` — Steps 1-3 OK (path hard-check +
   timestamped `.bak` + tar-over-ssh of the `ichor_api` package, both
   changed files inside it ; ZERO migration, ZERO systemd/register-cron
   change). Step-4 hit the known sshd-throttle (`Connection timed out`
   — the documented r76/r90/r94/r95 pattern: code synced, service
   un-restarted ⇒ prod = OLD code, NOT regressed = safe with an inert
   additive change). Recovered with **ONE consolidated throttle-aware
   recovery SSH** (restart + server-side health-wait + code-present +
   flag check — never hammered/revenge-retried, doctrine #7).
3. **Witness B+C — LIVE on prod (consolidated SSH):**
   `HEALTHZ=200` (ichor-api restarted clean, no rollback) ;
   `CODE_OK ['NAS100_USD','SPX500_USD'] session_cards_market_closed_gate_enabled`
   (the r98 code — `market_closed_for_asset`, `_US_EQUITY_ASSETS`,
   `_MARKET_CLOSED_GATE_FLAG` — is LIVE deployed & importable on the
   prod venv) ; **`IS_ENABLED= False`** via the REAL gate code path
   (`is_enabled(s, "session_cards_market_closed_gate_enabled")` on
   prod, api.env-sourced as `ichor`, mirroring the systemd unit) ⇒ the
   flag row is absent ⇒ the gate's `if gate_on:` is never entered ⇒
   **fully inert ⇒ ZERO behaviour change on prod** (the ship-OFF
   contract, proven schema-agnostically via the exact function the
   gate calls).

**Honest note (calibrated, lesson #13):** my first consolidated SSH
included a `SELECT count(*) FROM feature_flags WHERE name=…` that
errored `column "name" does not exist` — the real column is `key`. A
**verification-script schema guess, NOT a data/deploy defect** — the
definitive inert proof is the `is_enabled`-via-real-code-path witness
(`IS_ENABLED= False`), which is schema-agnostic and tests exactly what
the gate tests. Triaged to ground truth (the `\d feature_flags`
schema), not rationalised.

## Flagged residuals (NOT fixed — scope discipline)

- **`run_briefing` symmetric gate = r99** — explicitly deferred
  (ADR-105 §5, ADR-099 annotation). The SSOT `market_closed_for_asset`
  makes the r99 reuse byte-identical (2nd-use SSOT trigger, doctrine
  #4) — not silently skipped.
- **Live weekend/holiday skip not pixel-witnessed** — flag OFF by
  design (Eliot's RUNBOOK-019-class enable gesture). Proven:
  deployed + inert + 16 unit tests (incl. fail-open + anomaly). The
  flag-ON pixel-witness awaits Eliot inserting the
  `session_cards_market_closed_gate_enabled` row.
- NYSE half-days / CA holidays not modelled (under-suppression =
  fail-safe ; ADR-105 §Negative).
- Carried (r91→r97): vitest CI realign **DONE r97** ; README index
  back-fill **DONE r97/r98** ; GBP Driver-3 (`IR3TIB01GBM156N`) ;
  Pass-6 occasional ADR-017-token retry ; Dependabot 3 main vulns
  (r49) ; KeyLevelsPanel $5 polymarket joke market ; MEMORY.md
  > cap consolidation. Then Tier 4 premium UI.

## Process lessons (durable)

- **R59 collapses a HIGH-blast framing to LOW by finding the right
  mechanism.** The prompt's mandated PRUDENCE was satisfied by
  _choosing the pure-Python guard_, not by adding ceremony to a
  systemd change. Acting on the memory "HIGH blast-radius" framing
  without R59 would have over-engineered a dangerous mechanism.
- **FAIL-OPEN must be STRUCTURAL, not emergent (ichor-trader R28
  YELLOW-1).** "Correct today because the SSOT happens to make the
  early-return unreachable on an open market" is not good enough for a
  SAFETY-CRITICAL block where a missed real session is unrecoverable —
  the invariant must be asserted in code + regression-pinned.
- **A verification-script schema guess is not a data defect (lesson
  #13 reinforced).** The `name` vs `key` column error was triaged to
  the real `\d` schema + resolved via the real code path, not
  rationalised or shipped on.
- **Calibrated honesty on a deliberately-inert ship (lesson #11).**
  "deployed + provably inert + unit-exhaustive" is the honest claim
  for a flag-OFF round — NOT rounded up to "live weekend skip proven".

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening
continues** — R59 first, pick highest value/effort: the `run_briefing`
symmetric market-closed gate (r99 — reuses the `market_closed_for_asset`
SSOT byte-identically, the natural continuation) ; OR GBP Driver-3
(`IR3TIB01GBM156N` ingestion + R53 prod-DB liveness first — chicken-egg
multi-round) ; OR the §Cross-endpoint no-sidecar page-wiring
integration test (the r96/r97 YELLOW follow-up). Then Tier 4 premium
UI. The next `continue` executes this default unless Eliot pivots.

**Session depth:** r97 + r98 in one post-/clear session — r98 is a
larger round (2 R59 sub-agents + ichor-trader + a Hetzner deploy).
Approaching the anti-context-rot threshold ; pickup v26 + SESSION_LOG
r95/r96/r97/r98 are the zero-loss anchor (current through r98). A
`/clear` after this round is reasonable per the standing brief ("ne
grind pas jusqu'à la dégradation").
