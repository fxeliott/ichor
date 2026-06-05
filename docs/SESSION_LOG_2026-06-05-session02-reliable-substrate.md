# SESSION LOG — 2026-06-05 · Session 02/09 · Reliable live substrate

> Master-plan reference: [`PLAN_DIRECTEUR.md`](PLAN_DIRECTEUR.md) §5 row **02 —
> "Reliable live substrate"** (gap 🅰 RELIABILITY, the #1 lived problem).
> The prompt framed S02 as "architecture & socle technique"; on a mature
> system that means **make the existing substrate reliable + honest**, not
> rebuild. No rebuild was done.

## 0 · Verdict

The live pipeline was failing **silently**: whole `ny_close` batches
produced 0/6 cards and 5 Couche-2 agents were down, while the front-end kept
showing the previous (stale) card as "real-time". Root cause located by
reading the code end-to-end (not guessed). Shipped a **fail-loud + self-heal**
hardening of the runner substrate. Code is tested; **deploy + 48h fresh
witness remain** (gated on Eliot's "go" for the live restart/redeploy, plus
one guided Cloudflare step).

## 1 · Verified root-cause chain (read, not assumed)

1. **Single serialized slot.** `config.max_concurrent_subprocess=1` → one
   `claude -p` at a time. A `ny_close` batch (`run_session_cards_batch`,
   sequential, `--inter-card-sleep 30`, `TimeoutStartSec=1800`) competes for
   that one slot with the briefing, the ~12-min streaming-refresh watcher and
   the 5 Couche-2 crons. Under contention, Opus-4.8-`high` passes exceed the
   runner's **360 s** timeout (`config.py:36`) → `status="timeout"`.
2. **Runner silent-success-on-empty.** `subprocess_runner.run_claude` +
   `main.py` returned `status="success", briefing_markdown=None` when
   `claude -p` exited 0 with an error envelope (`is_error` / `error_*`
   subtype / refusal). The runner could not tell "succeeded with content"
   from "succeeded with an error".
3. **Brain client swallowed it.** `HttpRunnerClient._run_async_polling`
   returned `text = briefing_markdown or ""` and **never checked
   `result["status"]`** → a runner `timeout`/`subprocess_error` looked like a
   `PassError` (parse) to the orchestrator, not a timeout. (Couche-2's client
   already raised — which is why Couche-2 failed loud while cards failed
   quietly.)
4. **`501`** is not in the Python code (grep = 0) → it is a tunnel/port
   artefact (rogue `python -m http.server 8766` squatter / `localhost`→`::1`),
   consistent with the 2026-06-04 notes.

## 2 · Changes shipped (this branch, tested)

| File                                                     | Change                                                                                                                                                                                                                           |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/claude-runner/.../subprocess_runner.py`            | **Fail-loud**: `run_claude` raises `ClaudeSubprocessError` on `is_error` / `error_*` subtype / no usable text (helper `_result_has_usable_text`). Endpoints then return `status="subprocess_error"` with the real reason.        |
| `apps/claude-runner/.../config.py`                       | `claude_timeout_sec` 360→**540** + documented timeout hierarchy (runner 540 < brain poll 600 < Couche-2 poll 600 < systemd batch 1800).                                                                                          |
| `packages/ichor_brain/.../runner_client.py`              | New `RunnerResultError` + `_unwrap_runner_result`; both `_run_async_polling` and `_run_legacy_sync` now **raise on `status ∈ {timeout, subprocess_error, throttled, auth_failed}` or empty markdown** instead of returning `""`. |
| `apps/claude-runner/tests/test_subprocess_runner.py`     | +5 tests (empty / missing / error-subtype / is_error / content-blocks-ok).                                                                                                                                                       |
| `packages/ichor_brain/tests/test_runner_client_async.py` | +3 tests (timeout status / subprocess_error / empty markdown → raise).                                                                                                                                                           |
| `scripts/windows/runner-watchdog.ps1`                    | **NEW** self-heal watchdog: probes `/healthz`, restarts a down runner, recycles our own hung runner, reports `status=down` loudly, evicts a FOREIGN port squatter only with `-KillRogue` (safe by default).                      |
| `docs/runbooks/RUNBOOK-014-...md`                        | Extended: S02 fail-loud semantics, foreign-`:8766` recovery, watchdog install (5-min Task Scheduler).                                                                                                                            |

**Net effect:** a failed generation is now a **loud, classified error** in
logs (you can see _why_), never a silent empty card. This is the honesty
foundation S03's freshness gate and S09's observability build on.

### Deliberately NOT changed

- `max_concurrent_subprocess` stays **1** (Max-20x single-user; running 2
  concurrent `claude -p` risks the ban — rule 16). Throughput is addressed via
  timeout coherence + not over-scheduling, not by parallelism.
- Frontend untouched (premium, not a rebuild — S08).

## 3 · Verification (functional, not "it compiles")

PYTHONPATH forced to this worktree (venv `.pth` footgun) — confirmed both
modules resolve here.

- `apps/claude-runner/tests` → **27 passed** (incl. 5 new).
- `ichor_brain` `test_runner_client_async.py` → **9 passed** (incl. 3 new).
- `ichor_brain` retry + orchestrator → **18 passed** (no regression).
- `ruff format` + `ruff check` on edited files → clean.
- watchdog → PowerShell AST parse: **0 errors**.

## 4 · Remaining for S02 "done" (= fresh + coherent witnessed live)

These need Eliot's go (live prod) or one CF action — guided in the wrap-up:

1. **Deploy** the runner change (restart the Win11 standalone uvicorn) + the
   brain change (Hetzner `redeploy-brain-tar.sh` + restart). Outward/prod →
   awaiting "go".
2. **Install the watchdog** as a 5-min scheduled task (RUNBOOK-014 snippet).
3. **Stable named-tunnel URL for web2** (RUNBOOK-012 §Long-term fix) —
   guided CF action (domain + DNS decision is Eliot's).
4. **48 h witness**: 4×/day × 6 assets fresh, Couche-2 green, `ny_close`
   producing cards — the actual S02 acceptance criterion.

## 5 · Invariants held

ADR-017 (no BUY/SELL — none added), Voie D (zero `import anthropic`),
Couche-2 model selection untouched, watermark/audit untouched. ZERO Anthropic
API spend.
