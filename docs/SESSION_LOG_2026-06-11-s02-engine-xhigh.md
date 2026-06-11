# SESSION LOG — 2026-06-11 · Session 02/09 re-run · Engine xhigh + silent-outage class killed

> Master-plan reference: [`PLAN_DIRECTEUR.md`](PLAN_DIRECTEUR.md) v4.1 §5
> session-file execution mapping — **02 → transverse engine chantier +
> Chantier D socle slices**. Second S02 pass (first: 2026-06-05
> reliable-substrate). PR [#222](https://github.com/fxeliott/ichor/pull/222)
> squash-merged → `main 2135874`. ADR:
> [`ADR-110`](decisions/ADR-110-engine-opus48-max-effort-xhigh.md).

## 0 · Verdict

The production engine now runs **Opus 4.8 at effort `xhigh` on every
Couche-1 generation surface** (owner decision 06-11 — Fable-5 migration
cancelled, ZERO-spend invariant), and the **silent total-failure outage
class that fired 3× (05-29, 06-02, 06-10) is killed on four masking
layers**. Everything is deployed AND runtime-witnessed: a real EUR_USD
card was generated end-to-end at xhigh on prod (5 passes, **449,953 ms
total LLM time, ~90-123 s per pass**, critic=approved, persisted
`generated_at 2026-06-11 03:37:45+02`), and prod `/healthz` now answers
`claude_runner_reachable: true`.

## 1 · Engine uplift (commit 1, ADR-110)

- `orchestrator.py` 4 passes + `scenarios_effort` default → `xhigh`;
  `RunnerCall.effort` default → `xhigh`; `run_briefing.py` payload →
  `xhigh`. Couche-2 untouched (`low`, ADR-108 split).
- **Timeout hierarchy moved together** (the 360 s false-kill lesson):
  runner 540→900 < brain/Couche-2/briefing polls 600→960 < systemd walls
  couche2 600→1200 · counterfactual 900→1200 · streaming-refresh
  1800→3600 · session-cards 1800→5400.
- Lockstep tests: `TestEffortDoctrine` (4 passes + the EMITTED Pass-6
  RunnerCall via stub pass + defaults) + `test_couche2_agents_effort_low`.

## 2 · Outage-class kill (commit 2, Chantier D quick-wins)

1. `run_session_cards_batch` exit contract: 0 all-ok · 1 PARTIAL (≥1 ok,
   stays whitelisted) · **2 TOTAL (0 cards) → systemd Result=failed →
   OnFailure=ichor-notify@ fires**. 6 tests.
2. API `/healthz` probes the runner (60 s cache, 3 s timeout):
   `claude_runner_reachable` always a real bool in prod; runner-down ⇒
   `status: degraded` (HTTP stays 200 — deploy gates unchanged).
3. NEW `ichor-runner-health-check.timer` (5 min, transition-based notify
   - hourly re-notify while down): detection ≤ 6 min < 15-min D gate.
     First prod run witnessed exit 0, state `up`.
4. Win11 watchdog now **self-heals the WinError-2 class** (recycle once
   per 30-min window through the self-probing `.bat`).

## 3 · Independent fresh-context verifier (mandatory S02 protocol)

42-tool adversarial pass returned 9 findings — ALL folded before merge
(commit 3): 2 systemd walls that inverted my own hierarchy (couche2 600,
streaming-refresh 1800), 1 false ADR claim (NSSM "retired" while
Running), Pass-6 test gap, missing Couche-2 `low` guard, watchdog
sentinel-dir crash path, stale hierarchy docs (RUNBOOK-014/ARCHITECTURE/
PLAN_DIRECTEUR), missing market-closed rc test, **+ a pre-existing
runtime TypeError on the DSPy path** (`call_agent_task_async` kwargs) it
discovered — fixed.

## 4 · Ops incidents during the session (honest record)

- A `uv sync` on the runner venv failed mid-flight: the **NSSM zombie
  service (`IchorClaudeRunner`, SYSTEM, port :8765) holds file locks
  inside `.venv`** (uvicorn.exe + loaded .pyd) — it stripped
  `ichor_claude_runner` from the venv with the prod runner unable to
  restart from it. Recovered without admin: lock-synced **`.venv-live`**
  - `.bat` repointed; runner restarted with `claude_timeout_sec=900`
    loaded; watchdog logged `healthy status=ok` from 02:33 onward.
- **NSSM zombie stop+disable needs admin elevation — pending owner**
  (30 s, commands in the wrap-up). Until then `.venv-live` isolates prod
  from its locks; tunnel routes :8766 (witnessed).
- SSH port-22 rate-limit bit twice during deploys (lesson #24): brain
  and agents syncs landed but their restart steps needed a spaced manual
  retry. Both verified healthy after.

## 5 · Verification (runtime, not "it compiles")

- brain 30+9 pass · claude-runner **27/27** (the httpx2/starlette
  collection error was venv drift, gone on the lock-clean venv) · api
  13+6+55 pass · ruff clean · watchdog AST 0 errors · CI 100% green ×2.
- Deploys: brain (tar+restart, healthz 200) · api (backup
  `ichor_api.20260611-012102`, healthz+sample 200) · agents (remote
  `claude_runner.py:421 = 960.0` verified at source) · 5 unit registers
  applied (timers re-armed, pre_londres 06:00 next).
- **Runtime witness**: EUR_USD event_driven card at xhigh — pass-2 122.8 s,
  total 449.9 s, bias long conv 21.15 cap-aware, critic approved, in DB.
- Projection: 6-card batch ≈ 50-70 min at xhigh → fits the 5400 s wall;
  **re-validate on the first natural batch (06-11 06:00 pre_londres)**.

## 6 · Invariants held

ADR-017 (no BUY/SELL — verifier-confirmed zero tokens added), Voie D
(zero `import anthropic`), Couche-2 Opus low (now test-guarded),
watermark/audit untouched. **ZERO Anthropic API spend** (engine stays on
the Max 20x subscription).
