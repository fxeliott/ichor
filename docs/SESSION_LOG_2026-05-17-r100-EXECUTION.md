# SESSION_LOG 2026-05-17 — r100 EXECUTION (ADR-105 §Implementation(r100) — in-briefing closed-market caveat)

**Round type:** ADR-099 §Tier-3 autonomy hardening — the r99
SESSION_LOG / pickup v26 binding default ("the US-holiday in-briefing
`holiday_name` caveat in `_assemble_context` — the r99 YELLOW-1
follow-up, small, well-scoped, closes the last data-honesty soft-spot
of the holiday-gate"). doctrine #10 re-eval: (a) is the explicitly
recommended-first default (lowest blast-radius, closes the documented
ichor-trader r99 YELLOW-1) ; (b) GBP Driver-3 = chicken-egg multi-round
(defer) ; (c) §Cross-endpoint test = lower value. No superior emergent
gap. No pivot — executed (a).

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(pure calendar string, Voie D). ADR-017 N/A (no signal — a
string-literal honesty caveat ; `test_invariants_ichor` 41/41 green,
the token-guard excludes STRING tokens by design). One coherent atomic
increment ; 5 files modified, 0 new code files (1 new SESSION_LOG).

**Context discipline:** fresh session post-/clear (the r99 close
strongly recommended /clear ; Eliot did it, resumed via the
maximum-mode pickup). Clean context budget. Sub-agents calibrated to
the protocol, not FOMO: ONE R59 ichor-navigator (the mechanism was
clear, only `run_briefing.py`/`market_session.py` real shapes unknown)

- ONE mandatory ichor-trader R28 pre-merge. Both findings independently
  re-verified by me against the real code (sub-agent map = hypothesis
  until re-verified, doctrine #3).

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work in
`friendly-fermi-2fff71`. Verified live: HEAD `4006836` (r99), branch
`claude/friendly-fermi-2fff71`, 64 ahead origin/main, 0 uncommitted,
`origin/claude/friendly-fermi-2fff71 == HEAD` (pushed). Live == prompt
failsafe (0 discrepancy on the resume baseline — correct-by-construction:
the r99 commit cannot embed its own future hash). Doctrine #4: worktree
venv resolves `ichor_api` + `ichor_brain` to the WORKTREE (verified
`__file__`).

## R59 reshaped the design (doctrine #3 — the §Impl(r99) premise was load-bearing-wrong for the deployed state)

ONE focused read-only R59 sub-agent (ichor-navigator) mapped the real
`run_briefing.py` + `market_session.py` (file:line). I then re-read the
real code myself and **reshaped the design vs the ADR-105
§Implementation(r99) YELLOW-1 premise** ("the `should_skip_briefing`
path already computes `status` ; `_assemble_context` does not yet
consume it" — read naively as "just thread the gate's `status` in"):

- **`_assemble_context` MUST compute its OWN status.** The r99 gate's
  `status` local (`run_briefing.py:458` pre-r100 / `:477` post-format)
  is bound **only** inside `if gate_on:` inside the gate's `try`. On
  the **ships-OFF default** (`briefing_market_closed_gate_enabled` row
  absent ⇒ `gate_on=False` — the **actual production state**) and on
  the fail-open `except` path, `status` is **never bound** ⇒
  referencing it at the `_assemble_context` call site would raise
  `UnboundLocalError`. Threading the gate's local would have been a
  prod-crashing bug. `_assemble_context` recomputes its own
  `compute_session_status()` — verified pure / zero-DB / never-raising
  on well-formed input (`market_session.py:144-226`, no I/O) ⇒ zero
  new DB dependency, safe on every path. R59 reshaped it ; documented,
  not silently deviated.
- **Two assembler paths.** Legacy (the proven deployed default,
  `ICHOR_RICH_CONTEXT` opt-in) builds a `parts` list ; rich
  (`ICHOR_RICH_CONTEXT=1`) early-returns a delegated
  `build_rich_context`. The caveat is an **invariant of
  `_assemble_context` regardless of path** — computed once at the top,
  injected on BOTH (legacy preamble after "Generated at" ; rich
  prepended with an honest `tok_est += len(caveat)//4 + 1`).
- **Exact DB-access patterns** of the legacy path (`.scalars().all()`
  / `.all()` / `.first()`) mapped so the async wiring test's
  empty-result fake is non-fragile ("marche exactement", not a flaky
  test).

## ADR-before-code — ADR-105 §Implementation(r100), NO new ADR (doctrine #9)

ADR-105 §Implementation(r99) explicitly reserved this caveat as the
r99 YELLOW-1 interim honesty-floor next increment — ADR-105 IS the
spec. Per doctrine #9 a dated `## Implementation (r100, 2026-05-17)`
section was appended to immutable ADR-105 (the R59 reshape rationale,
the NEW-SSOT decision, the both-paths coverage, the
weekend+holiday-scope reasoning, the still-deferred asset-prune). NO
redundant ADR. ADR-099 §Coverage annotation extended `[… + r100 DONE]`
for the **caveat** half only, with the **US-holiday fused-briefing
asset-PRUNE** still named as the sole explicitly-deferred residual
(calibrated honesty — NOT rounded up to "holiday-gate fully done").

## What shipped (5 modified, 0 new code ; one coherent increment)

- **`services/market_session.py`** — NEW pure SSOT
  `briefing_market_caveat(briefing_type, status) -> str | None`, placed
  right after `should_skip_briefing` (its sibling — the gate-decision
  SSOT home ; anti-accumulation #4: the caveat decision/wording IS the
  SSOT, NOT inlined in `run_briefing.py`, so a future drift fails a
  test). Reuses `_DAILY_BRIEFING_TYPES` byte-identically (weekly/crisis/
  unknown ⇒ None — same exemption as `should_skip_briefing`). Weekend
  (`market_closed_fx`) ⇒ all-markets banner ; US-equity holiday
  (`market_closed_us_equity and holiday_name`) ⇒ SPX/NAS banner
  surfacing `holiday_name`, FX/XAU stated trading. Weekend-precedence
  matches `compute_session_status` branch order. Pure / never-raises.
- **`cli/run_briefing.py`** — import += `briefing_market_caveat` ;
  `caveat = briefing_market_caveat(briefing_type,
compute_session_status())` computed once at the top of
  `_assemble_context` (own status — R59 reshape) ; injected into the
  legacy `parts` preamble after "Generated at" ; prepended to the rich
  path's delegated md with `tok_est += len(caveat)//4 + 1`.
- **`tests/test_market_session.py`** — +11 tests appended to the
  sibling module (anti-accumulation #4): **8 pure SSOT** (weekend-daily
  banner / us-holiday surfaces `holiday_name` + SPX/NAS / 2nd-holiday
  MLK name-surfaced / normal-weekday-None / weekly-EXEMPT-on-weekend /
  crisis-EXEMPT / unknown-None / all-4-daily-types-one-identical-banner)
  - **3 async wiring** (`_assemble_context` threads the us-holiday
    caveat into the preamble before the first section + holiday_name
    surfaced + token estimate > 0 ; weekend caveat threaded ;
    normal-weekday emits NO caveat + preamble unchanged — zero-regression
    on the common path).
- **`docs/decisions/ADR-105-…md`** — appended `## Implementation
(r100, 2026-05-17)` dated note (immutable-append, doctrine #9).
- **`docs/decisions/ADR-099-…md`** — §Coverage annotation extended
  `[r78/r79 + r98 + r99 + r100 DONE]` ; the asset-PRUNE named as the
  sole residual (calibrated honesty).

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy on the full diff, with an explicit
weekend-scope adjudication ask. **0 RED / 0 YELLOW / GREEN on all 5
axes + all framework axes N/A-confirmed (not assumed). Mergeable as-is,
no pre-merge fixes.**

- **Axis 1 ADR-017 boundary GREEN** — the directive wording ("do not
  describe … as showing live pre-session momentum") is calendar/data-
  honesty CONTEXT, not a signal: no direction/size/entry/order, zero
  `\b(BUY|SELL)\b` hits, string-literal (structurally outside the
  token-guard by the documented prompt-text carve-out). Defensible as
  macro context, same register as the `_section_*` symmetric-language
  doctrine.
- **Axis 2 SCOPE adjudication GREEN (= include the weekend caveat)** —
  the weekend + US-holiday branches answer ONE predicate ("is this
  DAILY fused briefing a closed-market read mistakeable for live?").
  Shipping holiday-only would re-arm the **identical** defect for
  ~104 weekends/yr in the **shipped flag-OFF production state** — a
  half-fixed bug, not a deferred feature. The r99 YELLOW-1 text is the
  floor, not the ceiling. Genuinely atomic (one SSOT, one predicate,
  one call site, two `if`-arms). A desk would reject the narrow-
  literalist alternative as leaving a known landmine armed.
- **Axis 3 trading correctness GREEN** — weekend-precedence (Sat-that-
  is-also-a-holiday ⇒ weekend banner only, no holiday banner) correct ;
  US-holiday banner accurately states SPX/NAS closed + FX/XAU
  (EUR/USD,GBP/USD,XAU/USD) trade, no over/under-suppression ; `weekly`
  Sunday-18:00 correctly NO caveat (deliberate week-ahead artefact —
  a "markets closed" line there would actively mislead). USD_CAD folded
  into FX-trades-normally = consistent with the documented ADR-105
  §Consequences CA-holiday scope cut.
- **Axis 4 over-claim/honesty audit GREEN** — checked every "DONE"
  string for out-of-context quotability ; the ADR-099 "closed
  END-TO-END" is immediately scoped by the bracket that names the
  asset-PRUNE residual ; the R59-reshape note is itself an honesty win
  (corrects the §Impl(r99) load-bearing-wrong premise). No misquote
  possible.
- **Axis 5 / framework canon GREEN** — Tetlock invalidation /
  source-stamping / dollar-smile / VPIN / GEX / FX-peg / conviction-cap
  / macro-trinity all N/A-**confirmed** (pure calendar preamble, no
  session-card invalidation block, no data-pool numeric, no Pass-1
  axis). One optional informational note (a harmless redundant pure
  `compute_session_status()` on the flag-ON path — microsecond
  datetime math, explicitly **no fix**): recorded, not actioned (scope
  discipline ; it is correctness- and perf-neutral by the function's
  purity).

## Verification (3-witness for an always-on ADDITIVE Hetzner ship)

Honest "marche exactement" for r100 = deployed + the SSOT LIVE &
producing the correct banners via the **real prod venv code path the
briefing invokes** (NOT a schema/SQL guess — lesson #13 applied
pre-emptively) + healthz 200 + service active + deployed file carries
the wiring + zero regression. NB r100 is correctly **ungated/active**
(an honesty floor, not a destructive skip — so there is NO "flag-OFF
inert" claim ; the caveat is active on closed-market days, `None` on
normal days = zero behaviour change on the common path, proven
`NORMAL_NONE True`).

1. **Witness A — static gate (GREEN):** doctrine-#4 venv → worktree ;
   `ruff check` clean + `ruff format --check` "3 files already
   formatted" (PostToolUse hook auto-formatted ⇒ no commit-time
   reformat churn) ; **pytest 86/86** (`test_market_session` 25→36
   [+11 r100] + regression 50/50 : `test_invariants_ichor` 41 ADR-081
   [Voie-D + ADR-017] + `test_cftc_tff` 9 — ZERO doctrinal regression ;
   `briefing_market_caveat` is pure-additive, the injection is additive
   in the preamble). Pre-existing FastAPI `regex`-deprecation warnings
   are unrelated noise (not introduced/regressed).
2. **Deploy (additive, ADR-099 §D-4 autonomous):** vetted
   `scripts/hetzner/redeploy-api.sh` (R59-verified before running — not
   deployed blind). Steps 1-3 OK (path hard-check + timestamped `.bak`
   - tar-over-ssh of the `ichor_api` package, both changed `.py`
     inside ; ZERO migration, ZERO systemd/register-cron). Step-4 hit the
     known sshd-throttle (`Connection timed out` — the documented
     r76/r90/r94/r95/r98/r99 pattern: code synced, service un-restarted
     ⇒ prod = OLD code, NOT regressed = safe with an additive change).
     Recovered with **ONE consolidated throttle-aware recovery SSH**
     (single throttle-decay wait, then ONE connection: restart +
     server-side health-poll + real-code-path SSOT verify + deployed-file
     grep — never hammered/revenge-retried, doctrine #7).
3. **Witness B+C — LIVE on prod (consolidated SSH):** `HEALTHZ=200`
   - `systemctl is-active ichor-api` = `active` (clean restart, no
     auto-rollback). The r100 SSOT is LIVE on the prod venv via the
     REAL code path the briefing calls (pure, zero-DB): `WKND_OK True`
     (weekend → "MARKET CLOSED"+"weekend"), `XMAS_OK True` (Christmas →
     surfaces `holiday_name`='Christmas Day' + "US EQUITIES CLOSED"),
     `NORMAL_NONE True` (normal weekday → None ⇒ zero behaviour change on
     the common path), `WEEKLY_EXEMPT True` (R59-critical weekly-on-
     weekend exemption holds on prod). Deployed
     `run_briefing.py`: `grep -c briefing_market_caveat` = **2** (import
   - call site), r100 marker comment = **1** (wiring physically
     present). No schema-guess artifact this round (the r98 lesson #13
     applied pre-emptively — used the real `is_*`/import code path from
     the start).

**Honest scope (calibrated, doctrine #11 / lesson #1 FORECAST≠PREUVE):**
the SSOT is proven LIVE-callable + correct on prod via the exact code
path the briefing invokes, with the deployed-file wiring present and
86/86 unit+wiring tests. An actual closed-market DAILY-briefing
cron-fire physically rendering the caveat in a persisted `Briefing`
row is a **future observed event** — explicitly NOT claimed as done
now (the next real weekend/US-holiday daily-briefing fire will render
it ; I do not substitute that forecast for proof). This is the honest
bar for an always-on additive change — strictly stronger than the
r98/r99 flag-OFF "deployed+inert" bar because the real-code-path
behaviour itself is witnessed, not just inertness.

## Flagged residuals (NOT fixed — scope discipline)

- **US-holiday fused-briefing asset-PRUNE** — the sole remaining
  explicitly-deferred holiday-gate increment (a mid-flow `assets`
  mutation on a critical path ; ~10 US-holidays/yr ; YAGNI per ADR-105
  §Impl(r99)). r100 closed the _caveat_ half of the r99 YELLOW-1, NOT
  the prune — stated precisely in ADR-105 §Impl(r100) + ADR-099
  §Coverage, not rounded up.
- Redundant pure `compute_session_status()` on the flag-ON briefing
  path (ichor-trader Axis-5 informational) — correctness/perf-neutral
  (pure microsecond datetime math), explicitly no-fix.
- Carried: GBP Driver-3 (`IR3TIB01GBM156N` not polled — ingestion +
  R53 prod-DB liveness, chicken-egg multi-round) ; §Cross-endpoint
  no-sidecar page-wiring integration test (r96/r97 YELLOW — hardens an
  already prose+diff+SSOT-guarded contract) ; Pass-6 occasional
  ADR-017-token retry (guard HOLDS — efficiency, not safety) ;
  KeyLevelsPanel $5 polymarket joke market ; Dependabot 3 main vulns
  (r49 baseline) ; MEMORY.md > soft-cap consolidation ; 13 git
  worktrees incl. stale (housekeeping, non-blocking). Then Tier 4
  premium UI.
- Eliot-gated (RUNBOOK-019, unchanged): merge PR #138 ; named CF
  tunnel ; `gh secret set ICHOR_CI_FRED_API_KEY` ; activate the
  holiday-gate DB flags `session_cards_market_closed_gate_enabled`
  (r98) + `briefing_market_closed_gate_enabled` (r99) when ready
  (absent ⇒ gates inert, ship-OFF by design ; **the r100 caveat is
  independent of these flags — it is always active**) ; rotate leaked
  FRED+CF creds ; revoke PAT ; OPTIONAL `/healthz` CF bypass.

## Process lessons (durable)

- **R59 caught a prod-crashing would-be bug the §Impl(r99) note's
  naive reading implied (doctrine #3 reinforced).** "The path already
  computes `status`" is true only inside the flag-ON gate scope ; on
  the shipped flag-OFF state reusing that local raises
  `UnboundLocalError`. R59 primes over the ADR's own forward-looking
  note — it reshapes the design, it does not just confirm it. ichor-
  trader independently re-verified the binding against
  `run_briefing.py:473-497`.
- **An always-on additive ship has a STRONGER honest-proof bar than a
  flag-OFF ship, and it is reachable.** Because r100 is ungated, the
  real-code-path SSOT witness on prod (weekend/holiday/normal/weekly-
  exempt all correct via the exact function the briefing calls) is the
  honest "marche exactement" — strictly stronger than r98/r99's
  "deployed+inert". The only thing NOT claimed is the future cron-fire
  render (forecast≠preuve, lesson #1).
- **Scope = the complete SSOT, not the literal YELLOW-1 text
  (ichor-trader-adjudicated GREEN).** The documented commitment is a
  floor ; shipping holiday-only would leave the byte-identical defect
  armed for ~104 weekends/yr in the production flag-OFF state. One
  coherent predicate ⇒ one coherent SSOT. Anti-half-built (doctrine
  #1) beat a literalist reading — and ichor-trader, asked to adjudicate
  exactly this, confirmed it.
- **Pre-emptively applied the prior round's verification lesson
  (lesson #13).** The recovery SSH used the real import/pure-function
  code path from the start (no schema-guess SQL) — zero verification-
  script artifact this round, exactly as r99 did for r98's `name`-vs-
  `key` lesson.

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening continues**
— R59 first, pick highest value/effort. The holiday-gate is now
complete (weekend-skip r98/r99 + in-briefing caveat r100) ; the sole
deferred holiday increment is the **US-holiday fused-briefing
asset-PRUNE** (low value, YAGNI — defer further unless Eliot wants it).
Higher-value remaining Tier-3: **GBP Driver-3** (`IR3TIB01GBM156N`
ingestion + R53 prod-DB liveness first — chicken-egg multi-round,
the structurally-thinnest of the 5 assets) ; OR the §Cross-endpoint
no-sidecar page-wiring integration test (r96/r97 YELLOW — lower value,
hardens an already-guarded contract). Then **Tier 4 premium UI** (OKLCH
3-layer Tailwind v4 tokens + tabular-nums + SSR SVG microcharts +
motion=function + responsive). The next `continue` executes this
default unless Eliot pivots.

**Session depth:** r100 in a FRESH post-/clear session (1 R59 sub-agent

- 1 mandatory ichor-trader + 1 Hetzner deploy — a normal-sized round,
  well within context budget). pickup v26 + SESSION_LOG
  r95/r96/r97/r98/r99/r100 are the zero-loss anchor (current through
  r100). `/clear` not yet required (fresh session, single round) — a
  `/clear` after a few more rounds per the standing brief.
