# ADR-110 — Engine doctrine: Opus 4.8 at max effort (`xhigh`), Fable-5 migration cancelled

**Status** : Accepted (2026-06-11)

**Extends** : ADR-108 (full-Opus everywhere — model choice unchanged here;
this ADR raises the _effort_ dimension on the Couche-1 reasoning surfaces).
**Revises** : the 2026-06-10 owner decision "LLM engine upgrades from Opus
4.8 to Fable 5" (PLAN_DIRECTEUR §9 decision 2b) — explicitly **cancelled**
by the owner on 2026-06-11 (§9 decision 3).

## Context

1. **Owner decision (2026-06-11, verbatim recorded in PLAN_DIRECTEUR §9.3)**:
   "toutes les analyses sont avec claude opus 4.8 en ultra code … pour la
   meilleure qualité possible car fable 5 stop le 22 juin avec l'abonnement
   seul pro max x20". Verified at primary source the same day: Fable 5 is
   included on Pro/Max plans **only June 9–22**; from June 23 it draws
   prepaid usage credits at API rates ($10/$50 MTok = 2× Opus 4.8). A
   Fable-5 engine would breach the **ZERO-Anthropic-spend invariant**
   (ADR-009 Voie D) on June 23 and silently die mid-flight.
2. **As-built before this ADR**: every Couche-1 surface ran Opus 4.8 at
   effort `high` — a caller convention, not an enforced cap: the runner
   schema already accepted `xhigh`/`max`
   (`apps/claude-runner/.../models.py:28,104`).
3. The Session-02 spec demands the engine "full performance, effort
   maximal pour toutes les analyses et recherches". With Fable 5 excluded,
   that is **Opus 4.8 at `xhigh`** (`max` exists but is
   overthinking-prone per Anthropic guidance and not persistable as a
   default in the wider tooling — `xhigh` is the highest durable level).

## Decision

Raise effort `high` → **`xhigh`** on every Couche-1 generation surface;
Couche-2 stays `low` (ADR-108 cost/latency split — structured extraction,
not deep reasoning):

| Surface                                   | Call site                                     | Before    | After                |
| ----------------------------------------- | --------------------------------------------- | --------- | -------------------- |
| 4-pass analysis (régime/asset/stress/inv) | `ichor_brain/orchestrator.py` (4 RunnerCall)  | opus high | opus xhigh           |
| Pass-6 scenarios                          | `orchestrator.scenarios_effort` default       | opus high | opus xhigh           |
| Macro briefings (all types)               | `ichor_api/cli/run_briefing.py` payload       | opus high | opus xhigh           |
| Brain RunnerCall default                  | `ichor_brain/runner_client.py:RunnerCall`     | high      | xhigh                |
| Web-research passes (S03/G1)              | via RegimePass → orchestrator RunnerCall      | opus high | opus xhigh           |
| streaming_refresh regen (ADR-109)         | reuses `run_session_card._run` → orchestrator | opus high | opus xhigh           |
| Couche-2 agents ×5                        | `ichor_agents/agents/*.py`                    | opus low  | opus low (unchanged) |

### Timeout hierarchy (revised — xhigh multiplies per-pass wall-time)

The pre-S02 360 s runner timeout false-killed valid `high` runs; the same
class would reappear at `xhigh` against 540 s. The whole hierarchy moves
together, preserving the ordering invariant (the runner must kill a stuck
subprocess and classify it BEFORE any consumer's poll budget expires):

```
runner per-call  claude_timeout_sec            540 →  900 s
  <  brain per-pass poll   poll_max_total_sec   600 →  960 s
  ≤  Couche-2 poll budget  poll_timeout_sec     600 →  960 s
  <  briefing CLI poll     max_total_sec        600 →  960 s (consumer)
  <  systemd batch wall    TimeoutStartSec     1800 → 5400 s (anti-hang guard,
                                                NOT a pacing device)
```

`TimeoutStartSec=5400` is sized from: ~25 min witnessed batch at `high` ×
the xhigh latency multiplier with margin. **Re-validate against the first
witnessed xhigh batch** and shrink if reality allows.

### Incident-class kill (Chantier D quick-wins, same change set)

The 2026-06-10 P0 (runner dead all day, zero alert — third firing of the
class: 05-29, 06-02, 06-10) is killed on all three masking layers:

1. **`run_session_cards_batch` exit-code contract**: rc=1 = PARTIAL failure
   only (≥1 card ok); rc=2 = TOTAL failure (0 cards) — NOT whitelisted by
   `SuccessExitStatus=0 1` → systemd `Result=failed` → `OnFailure=
ichor-notify@` fires.
2. **API `/healthz` probes the runner** (cached 60 s, 3 s timeout):
   `claude_runner_reachable` is now always a real bool in prod (was null),
   and a down runner flips status to `degraded`. Deploy gates check the
   HTTP code (200), so auto-rollback behaviour is unchanged.
3. **Proactive monitor** `ichor-runner-health-check.timer` (5 min cadence,
   transition-based notify + hourly re-notify): detection latency ≤ 6 min,
   under the 15-min Chantier D gate.
4. **Win11 watchdog self-heals the WinError-2 class**: on `status=down /
claude_cli_available=false` it now recycles ONCE per 30-min window
   through the self-probing `.bat` (which re-resolves `claude.exe` at every
   launch), instead of only reporting. The `:8765` NSSM zombie
   (`IchorClaudeRunner` service, SYSTEM): retirement is **decided but
   pending an admin elevation only the owner can perform** (stop +
   disable — the service held file locks inside `.venv`, which is why the
   canonical runner now runs from the lock-clean `.venv-live`, isolating
   prod from the zombie meanwhile). Until then: one canonical SERVING
   runner on `:8766` (tunnel-routed, witnessed), one inert listener on
   `:8765`.

## Consequences

- **Voie D held**: same Max 20x subscription, zero Anthropic API spend.
- **Quota/latency**: xhigh multiplies thinking tokens per card. The §6.1
  contention rule hardens: **no heavy interactive Claude session within
  30 min before a batch window** (06/12/17/22h CEST). Watch the first
  witnessed batches for duration + quota pressure; the rollback is a
  one-line effort string per surface.
- **Revisit clause**: move to a Mythos-class engine (Fable 5+) **only when
  it is included in the subscription plans again** — never on usage
  credits (ZERO-spend invariant).
- **Interactive sessions ≠ engine**: Claude-Code interactive sessions may
  use Fable 5 until June 22; this ADR governs the production engine only.

## Invariant (test-guarded)

- `test_orchestrator.py::TestEffortDoctrine` locks the 4 pass RunnerCalls
  AND the emitted Pass-6 RunnerCall (`enable_scenarios=True` exercised
  with a stub pass) to `effort="xhigh"`.
- `test_session_cards_batch_exit_codes.py` locks the batch CLI exit-code
  contract (0 / 1 partial / 2 total).
- `test_invariants_ichor.py::test_couche2_agents_effort_low` locks the
  five Couche-2 agents to `effort="low"` (ADR-108 split).
