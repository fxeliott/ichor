# ADR-105: Market-closed gate for session-card generation (ADR-099 §Tier-3 autonomy hardening)

- **Status**: Accepted (r98, 2026-05-17) — authored under the ADR-099
  §D-4 standing autonomy mandate (local / reversible / additive),
  audit-grounded by 2 parallel read-only R59 sub-agents
  (ichor-navigator code-map + infra-auditor blast-radius). Ships
  **feature-flag OFF** ⇒ inert until Eliot inserts the flag row.
- **Date**: 2026-05-17
- **Decider**: Claude r98 (audit-grounded) ; Eliot (standing mandate ;
  the flag-enable gesture is his)
- **Implements**: [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md)
  §Tier-3 (autonomy hardening) + closes the backend half of the
  ground-truth gap ADR-099 §"Coverage" line 57-59 ("Holiday/weekend =
  NOT handled ; backend timers fire 365 d/yr — an explicit unmet
  requirement"). The **frontend signal** half was closed r78+r79
  (ADR-099 §T1.3, `services/market_session.py` + `/v1/calendar/
session-status`) ; this ADR closes the **backend card-gen gate** half.
- **Supersedes**: none.

---

## Context

`ichor-session-cards@.timer` fires 4×/day, 365 d/yr (06:00 / 12:00 /
17:00 / 22:00 Europe/Paris). On weekends and US market holidays the
batch still generates and persists 6 fresh 4-pass cards built on a
**closed-market context**, which the dashboard then serves as if it
were a live pre-session read — a real correctness/honesty defect (a
trader opening Ichor on a US-holiday Monday sees a card that _looks_
fresh but analyses a market that will not open). Eliot's vision
explicitly requires "conscience fériés/week-end pour adapter la
session".

The **market-state signal already exists** — `services/market_session.py`
(r78, ADR-099 §T1.3): `compute_session_status() -> SessionStatus`,
pure-stdlib (`zoneinfo` DST-correct + the standard NYSE holiday
computus), exposing `market_closed_fx` / `market_closed_us_equity`
booleans. The signal was wired to the frontend (`SessionStatus.tsx`,
r79) but **never gates the backend cron card-gen** — that gate is the
sole missing piece.

R59 (2 sub-agents) established the blast-radius: editing a
`scripts/hetzner/register-cron-*.sh` that writes a shared
`@.service` template + re-running `sudo bash` is exactly the
2026-05-04 incident class (overwrites the template, degrades every
sibling timer instance — ADR-030). `ExecStartPre=` is worse (a
non-zero pre marks the unit FAILED → fires `OnFailure=ichor-notify@`
→ a false-alarm notifier storm every weekend). A pure-Python guard at
the batch entrypoint touches **zero** systemd/register-cron and
collapses the blast-radius to a normal additive API redeploy.

## Decision

Add a **market-closed gate inside the Python batch entrypoint**
`cli/run_session_cards_batch.py:_run_batch`, after the
`_VALID_SESSIONS` check and before the batch header, gated by a new
feature flag `session_cards_market_closed_gate_enabled`:

1. **Mechanism = pure-Python guard (a).** ZERO systemd /
   register-cron / `@.service` change. Deploys as a normal additive
   `scripts/hetzner/redeploy-api.sh` (timestamped `.bak`,
   auto-rollback on `/healthz`≠200, manual `rollback` < 30 s).
   Mechanisms (b) `ExecCondition=` (no repo precedent, needs an
   ADR-030 amendment), (c) `ExecStartPre=` (FAILED-state notifier
   storm), (d) cron wrapper (new shared file in the dangerous dir) are
   **rejected** — all touch the 2026-05-04 blast class for zero
   additional benefit (the early-exit precedes every `HttpRunnerClient`
   POST, so the timers no-op'ing on closed days consume **zero
   claude-runner quota** — the only "leak" is a sub-second timer wake +
   one flag read).

2. **Per-asset semantics** (the `market_session` SSOT already carries
   the asset-class distinction in its docstring): a new pure SSOT
   function `market_closed_for_asset(asset, status)` in
   `market_session.py` —
   - `market_closed_fx` True (weekend) ⇒ **all 6 assets** skipped ;
   - US holiday (`market_closed_fx=False`, `market_closed_us_equity=True`)
     ⇒ skip **only** the US equities `SPX500_USD` + `NAS100_USD` ;
     `EUR_USD` / `GBP_USD` / `USD_CAD` / `XAU_USD` (FX/XAU) **continue**
     (they trade through US holidays).
     The gate decides on the **booleans at cron-fire time**, NOT on
     `SessionStatus.state` (which is "now"-only and has no
     `ny_mid`/`ny_close` members — R59 nuance).

3. **FAIL-OPEN invariant (non-negotiable).** The gate may suppress a
   card **only** when it has POSITIVELY and without error determined
   the asset's market is closed. Any exception (flag-DB read, market
   computation, anything) ⇒ **proceed with generation**. A missed real
   Monday pre-London session is unrecoverable (the timer does not
   re-fire) and is categorically worse than a redundant closed-day
   card (harmless wasted sub-second compute, itself flag-gated). The
   gate never converts an error into a skip. Mirrors the existing
   best-effort `except → continue` convention
   (`run_session_card.py:235,271`).

4. **Ship FLAG-OFF.** `session_cards_market_closed_gate_enabled` —
   `is_enabled` returns False when the flag row is absent
   (`feature_flags.py`), so deploy is **inert** (zero behaviour change)
   until Eliot explicitly inserts the flag row. The flag-OFF default
   is orthogonal to the §3 fail-open invariant (which governs
   behaviour _when enabled and erroring_).

5. **Scope = session-card batch only.** The `run_briefing` path is a
   natural symmetric follow-up (r99) — explicitly deferred, not
   silently skipped (anti-accumulation: the shared decision is already
   an SSOT pure function, so r99 reuses it byte-identically — the
   2nd-use SSOT trigger, doctrine #4).

ADR-017 / Voie D: untouched — the gate is a pure calendar decision, no
LLM, no signal, no BUY/SELL.

## Consequences

**Positive** — closes the long-standing "365 d/yr fire" honesty gap on
the primary product surface ; zero blast-radius (no infra file
touched) ; fully reversible (git revert + `redeploy-api.sh` < 30 s) ;
inert until explicitly enabled ; per-asset correctness (FX/XAU keep
running through US holidays — no over-suppression).

**Negative / trade-offs** — the timers still wake on closed days
(sub-second no-op, negligible) ; the gate is "now"-evaluated at
process start (correct because timers fire at the window wall-time) ;
shipping flag-OFF means the real-weekend skip is not pixel-witnessable
on prod until Eliot enables the flag (honest scope, not a defect).
The following are explicitly stated, not silently skipped
(ichor-trader R28 YELLOW-2 honesty):

- **Push-silence on a full skip.** A legitimate full skip returns 0
  with `successes == 0`, so the end-of-batch push notification
  (`run_session_cards_batch.py` `if live and ... successes > 0`) does
  NOT fire — Eliot gets _silence_ on a weekend skip, not a positive
  "skipped intentionally" message. Acceptable (it's a weekend) ; there
  is no batch-success watchdog that the rc=0 would mislead (verified —
  none in the register-cron scripts), and systemd's
  `SuccessExitStatus=0 1` treats skip and success identically _by
  design_ (no false `OnFailure=ichor-notify@` storm — the intended
  behaviour).
- **Canadian holidays not modelled.** `USD_CAD` is treated as FX-24/5
  ; CA-specific holidays (Victoria Day, Canada Day, …) are NOT a skip
  trigger. FX spot trades _through_ single-jurisdiction holidays with
  thinner liquidity (not closed), so generating a context card is
  defensible — a deliberate scope cut, not a defect.
- **NYSE half-days not modelled.** Early-close sessions (day after
  Thanksgiving, Christmas Eve) are treated as full trading days —
  cards still generate. This is **under**-suppression, i.e. the
  fail-safe direction, consistent with the §3 FAIL-OPEN doctrine
  (never risk a missed real session to avoid a redundant one).
- **The full-skip early-return is structurally gated** (ichor-trader
  R28 YELLOW-1) : `return 0` fires only when the market is _positively_
  closed (`market_closed_fx or market_closed_us_equity`). An empty
  keep-set on a NON-closed market (a future SSOT regression) logs a
  loud `*_anomaly_failed_open` warning and generates the FULL original
  set — the fail-open invariant is structural, not emergent.

**Neutral** — no migration, no systemd/register-cron change, no
`After=` chain impact (session-card/briefing units are time-triggered,
no downstream `After=` dependents). CI structural-lint (ADR-030
shell-lint) not exercised (no `.sh` modified).

## Alternatives considered

- **systemd `ExecCondition=`** — rejected: no repo precedent, rewrites
  the shared `@.service` template (2026-05-04 blast class), needs an
  ADR-030 amendment, for zero benefit over (a).
- **systemd `ExecStartPre=`** — rejected: a non-zero pre marks the
  unit FAILED → `OnFailure=ichor-notify@` false-alarm storm every
  weekend.
- **Cron wrapper script** — rejected: a new shared file in the
  dangerous `scripts/hetzner/` dir, least aligned with the ADR-030
  single-binary `ExecStart` contract.
- **Branch on `SessionStatus.state`** — rejected: "now"-only, and the
  state enum has no `ny_mid`/`ny_close` members ; the booleans are the
  correct, window-agnostic signal.
- **Fail-closed (skip on error)** — rejected: a missed real session is
  unrecoverable ; the asymmetry is total.
- **Gate both session-cards and briefing now** — deferred to r99
  (anti-accumulation: one verified atomic increment ; the SSOT
  function makes the r99 reuse byte-identical).

## References

- 2 parallel R59 sub-agents, 2026-05-17 (ichor-navigator card-gen
  cron + `market_session` code-map ; infra-auditor blast-radius +
  mechanism ranking + fail-safe direction). Findings cited
  `[file:line]` inline.
- [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md)
  §Tier-3 + §Coverage line 57-59 (the unmet requirement this closes
  on the backend side ; r78+r79 closed the frontend signal side).
- [ADR-030](ADR-030-resolvecron-protection-post-incident.md)
  (the 2026-05-04 register-cron incident class this design avoids by
  construction).
- [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary —
  pure calendar, no signal), [ADR-009](ADR-009-voie-d-no-api-consumption.md)
  (Voie D — no LLM in the gate).
- `services/market_session.py` (r78, the signal SSOT this extends),
  `cli/run_session_cards_batch.py` (the gated entrypoint),
  `cli/run_bundesbank_bund.py:42,79-87` (the canonical feature-flag
  fail-pattern mirrored).
