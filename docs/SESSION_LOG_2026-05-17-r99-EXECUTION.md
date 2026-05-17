# SESSION_LOG 2026-05-17 — r99 EXECUTION (ADR-105 §Implementation(r99) — briefing market-closed gate)

**Round type:** ADR-099 §Tier-3 autonomy hardening — the r98
SESSION_LOG / pickup v26 binding default ("the `run_briefing`
symmetric market-closed gate, r99 — the natural continuation").
doctrine #10 re-eval: leaving session-cards gated (r98) but the
briefing path un-gated is the "half-built capability" anti-pattern
(doctrine #1) — completing it IS "ce qui peut manquer". (c) GBP
Driver-3 = chicken-egg multi-round (defer) ; §Cross-endpoint test =
lower value ; Tier 4 = after Tier 3 complete (ADR-099 ordering). No
superior emergent gap. No pivot.

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(pure calendar gate, Voie D). ADR-017 N/A (no signal — `test_invariants_
ichor` 41/41 green). One coherent atomic increment ; 5 files modified,
0 new.

**Context discipline:** session = r97+r98+r99 post-/clear, deep ;
Eliot continued without `/clear` after the r98 re-flag. Stayed
context-frugal: ONE R59 sub-agent (not 2 — the mechanism was already
decided & proven r98 ; only `run_briefing.py`'s shape was unknown ;
anti-FOMO / position-sizing).

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work in
`friendly-fermi-2fff71`. Verified: HEAD `c1eb9b8` (r98), 63 ahead, 0
uncommitted, pushed. Live == prompt failsafe.

## R59 reshaped the design (doctrine #3 — caught a would-be bug)

ONE focused read-only R59 sub-agent (ichor-navigator) mapped the real
`run_briefing.py` (file:line, not guessed). It **overturned the
binding-default hypothesis** ("r99 reuses `market_closed_for_asset`
byte-identically"):

- **Market-wide, NOT per-asset.** `run_briefing.main:428` produces ONE
  fused market-wide artefact per `briefing_type` (single `Briefing`
  row + single `_assemble_context` + single claude-runner POST — no
  per-asset loop, contrast `run_session_cards_batch.py`). The r98
  per-asset filter does not map ; `market_closed_for_asset` is
  correctly NOT reused (a coarser surface needs a coarser decision —
  NOT a doctrine-#4 violation: `compute_session_status` IS reused
  byte-identical, and the briefing decision is extracted to a NEW pure
  SSOT, not inlined). The binding-default note is superseded by this
  R59 finding — documented, not silently deviated.
- **`weekly` / `crisis` are EXEMPT (R59-critical — a would-be bug).**
  The `weekly` briefing fires **Sunday 18:00 Paris**, which
  `market_session.py:154` correctly classifies `market_closed_fx=True`
  (weekend). A naïve weekend-skip would suppress the very Sunday-evening
  week-ahead prep the weekly briefing exists to produce. `crisis` is
  event-driven — a weekend shock is precisely when it matters most.
  Both are intentionally market-closed-time artefacts → exempt. The
  gate applies ONLY to the 4 daily intraday windows. **This exemption
  would have been a bug if the design had been guessed from memory.**

## ADR-before-code — ADR-105 §Implementation(r99), NO new ADR (doctrine #9)

ADR-105 §5 explicitly reserved the `run_briefing` symmetric gate as the
r99 follow-up — ADR-105 IS the spec. Per doctrine #9 (precedent
ADR-104 §Implementation r96) a dated `## Implementation (r99,
2026-05-17)` section was appended to immutable ADR-105 (the market-wide
shape, the weekly/crisis exemption rationale, the US-holiday-KEEP
decision, the distinct flag, the insert point). No redundant ADR.

## What shipped (5 modified, 0 new ; one coherent increment)

- **`services/market_session.py`** — NEW pure SSOT
  `should_skip_briefing(briefing_type, status) -> bool` +
  `_DAILY_BRIEFING_TYPES = frozenset({"pre_londres","pre_ny","ny_mid",
"ny_close"})`. True iff `briefing_type ∈ _DAILY_BRIEFING_TYPES and
status.market_closed_fx`. weekly/crisis/unknown ⇒ never skip (the
  exemption is encoded IN the SSOT so a future drift fails a test —
  anti-accumulation #4). Placed next to `market_closed_for_asset` (the
  gate-decision SSOT home).
- **`cli/run_briefing.py`** — gate block in `async def main` between
  `sm = get_sessionmaker()` and the pending-`Briefing`-row insert (so a
  gated closed day writes NO wasted `pending` row). Flag
  `briefing_market_closed_gate_enabled` (DISTINCT from the
  session-cards flag — independent enablement ; mirrors the
  `run_bundesbank_bund.py` is_enabled pattern: absent row ⇒ False ⇒
  inert ; ships OFF). FAIL-OPEN: whole gate in `try/except` ⇒ any error
  proceeds. Structurally simpler than r98 (a boolean skip, no
  per-asset keep-set ⇒ the r98 YELLOW-1 empty-set anomaly class does
  not arise).
- **`tests/test_market_session.py`** — +9 tests appended to the
  sibling SSOT module (anti-accumulation): 7 pure (incl. the
  **R59-critical `weekly`-EXEMPT-on-Sunday-18:00-weekend** pin +
  crisis-exempt + daily-skipped-weekend + daily-NOT-skipped-US-holiday
  - unknown-never-skipped + `_DAILY_BRIEFING_TYPES` membership pin) +
    2 async (`run_briefing.main` skip-fires-before-`_assemble_context` ;
    fail-open-when-is_enabled-raises). 25/25 test_market_session pass.
- **`docs/decisions/ADR-105-…md`** — appended `## Implementation
(r99, 2026-05-17)` dated note (incl. the ichor-trader R28 YELLOW-1
  interim-honesty-floor commitment + YELLOW-2 aligned wording).
- **`docs/decisions/ADR-099-…md`** — §Coverage annotation extended to
  `[r78/r79 + r98 + r99 DONE]`, softened per YELLOW-2 ("no _weekend_
  residual ; US-holiday fused-briefing asset-prune + interim
  `holiday_name` caveat explicitly-deferred — NOT 'fully done'").

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy. **0 RED / 2 YELLOW / GREEN-on-rest. Both
YELLOW applied pre-merge (doc-only, same commit).**

- **A FAIL-OPEN GREEN** — exactly one `return 0` skip path, reachable
  only on a positive `should_skip_briefing` True for a flag-ON daily
  type ; every exception path proceeds ; gate runs before the
  pending-row insert (no half-state) ; the EXEMPT `weekly` is never
  gated so the `After=ichor-briefing@weekly` post-mortem chain is never
  starved. Pinned by the fail-open async test.
- **B weekly/crisis exemption GREEN** — both correct & safety-critical;
  no market scenario makes either exemption produce a stale-as-live
  artefact (both are by-construction forward-looking prep, not a live
  pre-session read).
- **C US-holiday KEEP GREEN + YELLOW-1 APPLIED** — KEEP is the correct
  trading-desk call (under-suppression = fail-safe ; 4/6 trade ;
  market-wide artefact). **YELLOW-1 applied**: the r98-skip-SPX/NAS vs
  r99-keep asymmetry is defensible but the briefing would carry SPX/NAS
  sections on a US holiday with no in-artefact caveat → committed the
  interim honesty floor in ADR-105 (surface `status.holiday_name` in
  `_assemble_context` as the next clean increment ; `should_skip_briefing`
  already computes `status` ; `_assemble_context` does not yet consume
  it — flagged, not silent).
- **D scope/Voie D/ADR-017 GREEN + YELLOW-2 APPLIED** — pure calendar,
  no LLM/SDK/BUY-SELL ; one atomic increment ; **YELLOW-2 applied**:
  softened ADR-099 + ADR-105 "no residual / end-to-end" → "no
  _weekend_ residual ; US-holiday prune + caveat explicitly-deferred"
  so the §Coverage one-liner cannot be quoted as "holiday-gate fully
  done" (lesson #11 calibrated-honesty).

## Verification (3-witness for an additive, deliberately-INERT Hetzner ship)

Honest "marche exactement" for a flag-OFF ship = deployed + provably
inert + the gate logic exhaustively unit-proven. The live weekend-skip
is NOT pixel-witnessable (flag OFF by design = Eliot's enable gesture,
ADR-099 §D-4) — stated, not over-claimed (r96/r98 honesty pattern).

1. **Witness A — static gate (GREEN):** doctrine-#4 venv → worktree ;
   ruff check + `format --check` clean ; **pytest 25/25**
   `test_market_session.py` (7 orig + 9 r98 + 9 r99 incl. the
   R59-critical weekly-EXEMPT + the 2 async briefing-gate wiring) +
   **regression 50/50** (`test_invariants_ichor` 41 ADR-081 +
   `test_cftc_tff` 9 — zero doctrinal regression ; `should_skip_briefing`
   is pure-additive, the gate is additive-before-pending-insert).
2. **Deploy (additive, ADR-099 §D-4 autonomous):** vetted
   `scripts/hetzner/redeploy-api.sh` — Steps 1-3 OK (path hard-check +
   timestamped `.bak` + tar-over-ssh of the `ichor_api` package, both
   changed files inside ; ZERO migration, ZERO systemd/register-cron).
   Step-4 hit the known sshd-throttle (the documented r98 pattern: code
   synced, service un-restarted ⇒ prod = OLD code, NOT regressed = safe
   with an inert additive change). Recovered with **ONE consolidated
   throttle-aware recovery SSH** (doctrine #7, never hammered).
3. **Witness B+C — LIVE on prod (consolidated SSH):** `HEALTHZ=200`
   (ichor-api restarted clean, no rollback) ; `CODE_OK
['ny_close','ny_mid','pre_londres','pre_ny']
briefing_market_closed_gate_enabled` (the r99 code —
   `should_skip_briefing`, `_DAILY_BRIEFING_TYPES` [exactly the 4 daily,
   weekly/crisis correctly absent], `_BRIEFING_MARKET_CLOSED_GATE_FLAG`
   — is LIVE & importable on the prod venv) ; **`IS_ENABLED= False`**
   via the REAL `is_enabled` code path (api.env-sourced as `ichor`) ⇒
   the flag row is absent ⇒ the gate's `if gate_on:` is never entered
   ⇒ **fully inert ⇒ ZERO behaviour change on prod**. Applied the r98
   lesson #13: used the real code path from the start (no schema-guess
   SQL) — no verification-script artifact this round.

## Flagged residuals (NOT fixed — scope discipline)

- **US-holiday in-briefing `holiday_name` caveat** (ichor-trader r99
  YELLOW-1) — the next clean increment: `_assemble_context` should
  consume `status.holiday_name` so the fused briefing's SPX/NAS
  sections are not read as a live US-equity session on a US holiday.
  The `should_skip_briefing` path already computes `status`. Flagged in
  ADR-105 §Implementation(r99), not silent.
- **US-holiday fused-briefing asset-prune** — explicitly deferred
  (mid-flow `assets` mutation, marginal purity, ~10 US-holidays/yr vs
  ~104 weekends/yr ; YAGNI). A clean future increment.
- Live weekend-skip not pixel-witnessed (flag OFF by design — Eliot's
  RUNBOOK-019-class enable gesture for `briefing_market_closed_gate_enabled`).
- Carried: GBP Driver-3 (`IR3TIB01GBM156N`) ; Pass-6 occasional
  ADR-017-token retry ; Dependabot 3 main vulns (r49) ; KeyLevelsPanel
  $5 polymarket joke market ; MEMORY.md >cap consolidation ; the
  §Cross-endpoint page-wiring integration test. Then Tier 4 premium UI.

## Process lessons (durable)

- **R59 caught a would-be bug the prompt's binding default missed
  (doctrine #3 reinforced).** The default said "reuse
  `market_closed_for_asset` byte-identically" ; R59 proved briefing is
  market-wide (not per-asset) AND that a naïve weekend rule would
  suppress the deliberately-weekend-scheduled `weekly`/`crisis`
  briefings. R59 primes over the prompt's hypothesis — it reshapes the
  design, it does not just confirm it.
- **Context-frugal sub-agent calibration on a deep no-/clear session.**
  ONE R59 sub-agent (not the r98 two) because the mechanism was already
  decided & proven r98 — only the unknown (`run_briefing.py` shape)
  needed mapping (anti-FOMO / position-sizing ; protect context when
  Eliot continues past a /clear re-flag).
- **Apply the prior round's verification lesson immediately.** r98
  lesson #13 (a schema-guess SQL = a verification-script artifact) was
  applied pre-emptively in r99 — the recovery SSH used the real
  `is_enabled` code path from the start, no artifact this round.
- **ichor-trader catches doc-precision over-claims even at 0 RED.**
  "no residual / end-to-end" was internally reconciled but quotable
  out of context ; softened to "no _weekend_ residual" + the interim
  honesty-floor commitment (lesson #11 — precision, not rounding up).

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening
continues** — R59 first, pick highest value/effort: the US-holiday
in-briefing `holiday_name` caveat in `_assemble_context` (the r99
YELLOW-1 follow-up — small, well-scoped, closes the last data-honesty
soft-spot of the holiday-gate) ; OR GBP Driver-3 (`IR3TIB01GBM156N`
ingestion + R53 prod-DB liveness — chicken-egg multi-round) ; OR the
§Cross-endpoint page-wiring integration test (r96/r97 YELLOW). Then
Tier 4 premium UI. The next `continue` executes this default unless
Eliot pivots.

**Session depth: r97 + r98 + r99 in one post-/clear session, all
substantial (r98 + r99 each = R59 sub-agent(s) + ichor-trader + a
Hetzner deploy).** Well past the anti-context-rot threshold.
**`/clear` STRONGLY RECOMMENDED now** — pickup v26 + SESSION_LOG
r95/r96/r97/r98/r99 are the zero-loss anchor (current through r99) ;
the next `continue` resumes cleanly. Per the standing brief "ne grind
pas jusqu'à la dégradation".
