# ADR-024: session-cards 4-pass pipeline — five-bug fix and ny_mid/ny_close enablement

- **Status**: Accepted
- **Date**: 2026-05-06
- **Decider**: Eliot (validated 2026-05-06 during the session-cards
  emergency-recovery sprint)

## Context

The 2026-05-05 ultra-atomic audit surfaced
`n_couche2_outputs_7d = 0` in `/v1/admin/pipeline-health`. While
fixing that, a second much more critical issue emerged :
`session_card_audit` had not received a single new row since
2026-05-04 14:23 — **two full days without the 4-pass pipeline
producing its main output**, the per-asset bias card.

Root-cause investigation surfaced **five distinct bugs** stacked in
the path between the systemd `ichor-session-cards@*.service` units
and the persisted `session_card_audit` row :

1. **`SessionType` Literal too narrow.**
   `packages/ichor_brain/src/ichor_brain/types.py:20` declared
   `Literal["pre_londres", "pre_ny", "event_driven"]`. The 17:00
   (`ny_mid`) and 22:00 (`ny_close`) timers had been registered but
   the runtime type-validation rejected every batch with
   `unknown session_type`. The CLI exit code 2 happened before any
   Claude call, masking the real cause in the logs.

2. **`run_session_card._VALID_SESSIONS` drifted vs. the batch wrapper.**
   `apps/api/src/ichor_api/cli/run_session_card.py:30` had the same
   3-element set (older copy of the source-of-truth). The batch
   wrapper (`run_session_cards_batch.py:54`) carried the correct
   5-element set, but it delegates to `run_session_card._run` which
   re-validated and rejected. Drift between two adjacent files in
   the same package.

3. **CHECK constraint in DB still allowed only 3 values.**
   Migration `0005_phase1_collector_tables.py:277` created
   `ck_session_card_session_type_valid` with the 3 original values.
   Even after fixing #1 and #2, the persistence layer hit
   `IntegrityError` on the CHECK violation. The fix needed a
   migration (added as `0027_session_type_extend_ny.py`).

4. **`HttpRunnerClient` had no retry envelope.**
   `packages/ichor_brain/src/ichor_brain/runner_client.py:103-120`
   posted directly with no retry. The runner's
   `max_concurrent_subprocess=1` causes near-simultaneous timer
   firings (briefing@HH:00 + session-cards@HH:01) to collide on
   503 "Another briefing in flight". The session-cards batch
   would then surface 0/8 with elapsed 21 s — looking like a
   different bug entirely.

5. **`MarketDataBar.bar_ts` AttributeError in two services.**
   `services/analogues.py:99,101,112` and
   `services/ml_signals.py:64-65` queried
   `MarketDataBar.bar_ts`, but the model only defines `bar_date`
   (cf. `models/market_data.py:26`). This silently emitted
   `ml_signals adapter ... failed` warnings during the otherwise-
   working passes, but in `services/data_pool.py` the
   `render_analogues_block` path threw and aborted the whole card
   build. Confusion with `PolygonIntradayBar.bar_ts` from
   `models/polygon_intraday.py:25`.

## Decision

Five surgical fixes, all shipped in a single sprint :

| Bug | Fix | File |
|---|---|---|
| 1 | `SessionType = Literal["pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"]` | `packages/ichor_brain/src/ichor_brain/types.py:20` |
| 2 | `_VALID_SESSIONS` extended to match `run_session_cards_batch.py:54` | `apps/api/src/ichor_api/cli/run_session_card.py:30` |
| 3 | New migration drops + recreates the CHECK with the 5-value set | `apps/api/migrations/versions/0027_session_type_extend_ny.py` |
| 4 | Exponential-backoff retry envelope (5/15/45 s) on HTTP 503/429; 524 fails fast | `packages/ichor_brain/src/ichor_brain/runner_client.py:103-160` |
| 5 | `bar_ts` → `bar_date` (with `.date()` coercion on the cutoff) in 2 services | `services/analogues.py`, `services/ml_signals.py` |

Five tests added to
`packages/ichor_brain/tests/test_runner_client_retry.py` covering :
first-call success, 503-then-success, 429-then-success, no-retry
on 524, and exhaustion of retry budget.

## Consequences

**Easier**:

- Session-cards pipeline alive again. Manual end-to-end run
  (2026-05-06 02:38 CEST) produced EUR_USD ny_close in 84 249 ms,
  critic verdict `approved`, persisted with hash 93631db1…
- Subsequent ny_close batch finished 8/8 in ~12 min (7 approved,
  1 amendments — critic gate did its job on AUD_USD).
- The retry envelope makes the briefing → session-cards back-to-back
  pattern (HH:00 → HH:01) work without hand-tuning timer offsets.
- ADR-021 / ADR-023 plumbing (Couche-2 → Claude Haiku) is now
  matched by an equivalent retry posture on Couche-1 (Claude Opus
  via `HttpRunnerClient`).

**Harder**:

- Two adjacent files (`run_session_card.py` + `run_session_cards_batch.py`)
  carry their own `_VALID_SESSIONS` set. A future drift is possible
  again — both should ultimately import `SessionType` from
  `ichor_brain.types` and derive the set via `get_args`. This was
  not done in this fix to keep the change set minimal and avoid
  cross-package import cycles. Marked as Phase C cleanup.
- The CHECK-constraint pattern means every future SessionType
  extension requires both a code change AND a migration. Migration
  template should be added to the runbooks index.

**Trade-offs**:

- The retry budget (5/15/45 s) burns up to 65 s before falling back
  to error. With a Cloudflare Free tunnel cap of 100 s, this is
  intentionally close to the wall — better to retry once than
  miss a card on a transient 503.

## Alternatives considered

- **Stagger timers** (briefing@HH:00, session-cards@HH:05) instead
  of retry: rejected. Brittle, doesn't handle bursts of 8 cards
  inside one batch when the briefing is already done. Retry handles
  both naturally.
- **Pin `_VALID_SESSIONS` to a single source of truth across both
  CLI files**: deferred to Phase C. Requires the api package to
  import from ichor_brain at module load time, which conflicts with
  the lazy-import discipline used everywhere else in `apps/api`.
- **Fix `MarketDataBar.bar_ts` by adding the alias to the model**:
  rejected. The model owns one timestamp column (`bar_date`); adding
  a synonym `bar_ts` would mask the bug class rather than fix it.

## References

- [migration 0027](../../apps/api/migrations/versions/0027_session_type_extend_ny.py)
- [`packages/ichor_brain/src/ichor_brain/runner_client.py`](../../packages/ichor_brain/src/ichor_brain/runner_client.py)
- [`packages/ichor_brain/src/ichor_brain/types.py`](../../packages/ichor_brain/src/ichor_brain/types.py)
- [`apps/api/src/ichor_api/services/analogues.py`](../../apps/api/src/ichor_api/services/analogues.py)
- [`apps/api/src/ichor_api/services/ml_signals.py`](../../apps/api/src/ichor_api/services/ml_signals.py)
- [SESSION_LOG_2026-05-06](../SESSION_LOG_2026-05-06.md)
