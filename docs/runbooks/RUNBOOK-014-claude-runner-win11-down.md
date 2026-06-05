# RUNBOOK-014: claude-runner Win11 down

- **Severity**: P0 — every Couche-1 briefing + Couche-2 agent + 4-pass card depends on the runner. If it's down, the whole `/v1/briefing-task` and `/v1/agent-task` chain returns 5xx and `session_card_audit` writes stop.
- **Last reviewed**: 2026-06-05 (Session 02 — fail-loud guard + self-heal watchdog)
- **Time to resolve (target)**: 5-10 min for the standalone uvicorn fallback ; 30-60 min for full NSSM service repair.

## What changed in Session 02 (2026-06-05)

Two reliability behaviours were hardened — read these before diagnosing a
"cards are empty / stale shown as fresh" report:

1. **The runner now FAILS LOUD on an empty / error envelope.** Previously
   `claude -p` could exit 0 while signalling failure in-band (`is_error`,
   an `error_*` subtype, rate-limit, refusal) with an empty `result`, and
   the runner returned `status="success"` with `briefing_markdown=null`.
   That disguised a FAILED generation as a fresh-but-empty card. Now
   `subprocess_runner.run_claude` raises and the endpoint returns
   `status="subprocess_error"` with the real reason
   (`apps/claude-runner/.../subprocess_runner.py`). The brain client
   (`packages/ichor_brain/.../runner_client.py`) and Couche-2 client now
   both raise `RunnerResultError` / `ClaudeRunnerError` on a non-`success`
   inner status or empty text instead of silently yielding `""`. **Net
   effect:** a failed batch shows up as a loud error in logs (you can SEE
   the cause), never as a silent empty card.
2. **Timeout hierarchy is documented & ordered** (`config.py`):
   runner `claude_timeout_sec` (540 s) < brain poll budget (600 s) <
   Couche-2 poll budget (600 s) < systemd batch wall (1800 s). The runner
   must kill a stuck subprocess and return a clean `timeout` BEFORE the
   consumer gives up, so the failure is classified at the runner.

> Implication for triage: if you see `status="subprocess_error"` /
> `RunnerResultError` in logs, that is the **new, correct** classification
> of a real failure — not a regression. Look at the `error_message` for the
> true cause (timeout, rate-limit, refusal). Empty cards no longer ship.

## Trigger

Any of :

- `curl https://claude-runner.fxmilyapp.com/healthz` returns 5xx, timeout, or connection refused.
- Hetzner-side `Couche-2 agent fallback active` logs spike (cf SESSION_LOG handoff).
- `/v1/admin/pipeline-health` shows briefings or session-cards stale > 1h.
- ntfy/journal alerts on Win11 box (when Phase A.4.b notification path is configured for the runner).

Verify scope first :

```powershell
# Win11 box
Get-Service IchorClaudeRunner
Get-Process -Name "uvicorn", "python" -ErrorAction SilentlyContinue
Test-NetConnection -ComputerName 127.0.0.1 -Port 8766
curl http://127.0.0.1:8766/healthz
```

## Diagnosis

### Path A — NSSM service status

```powershell
Get-Service IchorClaudeRunner
# If 'Stopped' / 'Paused' → state is the issue, not network.
```

Common states observed on this project :

- **`Paused`** : the documented dormant state since 2026-05-02 because
  `ICHOR_RUNNER_ENVIRONMENT=development` was lost from the NSSM env-var
  list. Workaround = standalone uvicorn (see Recovery path B).
- **`Stopped`** : crashed at boot, log under
  `C:\nssm-logs\IchorClaudeRunner.err.log`. Read the last 50 lines.
- **`Running`** but `/healthz` 5xx → the process is up but the FastAPI
  app crashed (see Path C).

### Path B — Standalone uvicorn (current production fallback)

```powershell
Get-Process | Where-Object { $_.ProcessName -eq "python" -and $_.MainWindowTitle -like "*claude-runner*" }
# Expected: 1+ processes when standalone runner is alive.
```

The standalone runner is launched at user-login by
`scripts/windows/start-claude-runner-standalone.bat` placed in the
Startup folder. If Eliot logged out (rare — the box runs headless),
the standalone runner dies with the session.

### Path C — Cloudflare Tunnel side

```powershell
Get-Process cloudflared
# Expected: 1 process (managed-config side, not local config.yml).
```

If `cloudflared` is gone but uvicorn is up, the tunnel is the issue.
See RUNBOOK-012 for tunnel-specific recovery.

### Path D — claude CLI quota / 403

```powershell
& "C:\Users\eliot\.claude\local\claude.cmd" -p "ping" 2>&1 | Select-Object -First 5
```

If this returns 403 / "organization does not have access" → see
RUNBOOK-008. If 429 → see RUNBOOK-013.

## Recovery

### Quickest path : restart the standalone uvicorn (≤ 5 min)

```powershell
# 1. Kill any existing standalone uvicorn
Get-Process python | Where-Object { $_.MainWindowTitle -like "*claude-runner*" } | Stop-Process -Force

# 2. Re-launch via the canonical .bat
#    (r87 fix: was C:\Users\eliot\Ichor\... — that path does not exist;
#     projects live on D:\ and the .bat cd's to D:\Ichor\apps\claude-runner)
& "D:\Ichor\scripts\windows\start-claude-runner-standalone.bat"

# 3. Verify
Start-Sleep -Seconds 3
curl http://127.0.0.1:8766/healthz
# Expected: HTTP 200 with JSON {"status":"ok",...}
```

### Recovery : a FOREIGN process squats port 8766 (2026-06-04 class)

Symptom : `/healthz` connection-refused or returns non-runner content, but
`Get-NetTCPConnection -LocalPort 8766` shows a listener. Witnessed cause :
a rogue `python -m http.server 8766` (or a leftover dev server) held the
port, so the runner could not bind and clients saw connection / 501 errors.

```powershell
# Identify the squatter (PID + command line)
$c = Get-NetTCPConnection -LocalPort 8766 -State Listen
Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" |
  Select-Object ProcessId, Name, CommandLine
# If it is NOT the ichor runner (no `ichor_claude_runner` / `uvicorn` in the
# command line), stop it, then relaunch the runner:
Stop-Process -Id $c.OwningProcess -Force
& "D:\Ichor\scripts\windows\start-claude-runner-standalone.bat"
Start-Sleep 3 ; curl http://127.0.0.1:8766/healthz
```

> Bind-interface note: the runner binds `127.0.0.1` (IPv4). If a client
> resolves `localhost` → `::1` (IPv6) it will fail to connect even though
> the runner is up. Always probe `127.0.0.1` explicitly, and keep
> `cloudflared` pointed at `http://127.0.0.1:8766`, never `localhost`.

### Self-heal watchdog (install once — prevents most P0s)

`scripts/windows/runner-watchdog.ps1` probes `/healthz` and auto-heals the
two recoverable failure modes (process down → restart ; our own hung runner
→ recycle). A FOREIGN squatter is only evicted with the explicit
`-KillRogue` switch, so the default run is never destructive. `status=down`
(claude CLI unreachable) is reported loudly, not loop-restarted.

Run it manually first to see the decision it makes:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\Ichor\scripts\windows\runner-watchdog.ps1"
# add -KillRogue only after confirming a foreign squatter is safe to kill
```

Register it to run every 5 minutes (user-scope Task Scheduler, no admin):

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "D:\Ichor\scripts\windows\runner-watchdog.ps1"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'IchorRunnerWatchdog' -Action $action `
  -Trigger $trigger -Description 'Self-heal the Ichor claude-runner (RUNBOOK-014)'
# Log: D:\Ichor\.cache\runner-watchdog.log  (HEALED / CRIT lines)
```

Exit codes: `0` healthy/healed · `2` restarted-still-unhealthy · `3`
status=down (fix claude.exe path, RUNBOOK-014 Path D) · `4` foreign
squatter, `-KillRogue` not set · `5` unexpected error.

### Recommended path : repair the NSSM service properly (30-60 min)

```powershell
# 1. Stop & remove the broken NSSM service
nssm stop IchorClaudeRunner
nssm remove IchorClaudeRunner confirm

# 2. Re-create with the full env-var list (this is the bug — env vars
#    must be passed via `nssm set IchorClaudeRunner AppEnvironmentExtra`).
nssm install IchorClaudeRunner "C:\Users\eliot\Ichor\apps\claude-runner\.venv\Scripts\python.exe"
nssm set IchorClaudeRunner AppParameters "-m uvicorn ichor_claude_runner.main:app --host 127.0.0.1 --port 8766"
nssm set IchorClaudeRunner AppDirectory "C:\Users\eliot\Ichor\apps\claude-runner"
nssm set IchorClaudeRunner AppEnvironmentExtra `
  "ICHOR_RUNNER_ENVIRONMENT=development" `
  "ICHOR_RUNNER_REQUIRE_CF_ACCESS=false" `
  "ICHOR_RUNNER_LOG_LEVEL=info"
nssm set IchorClaudeRunner AppStdout "C:\nssm-logs\IchorClaudeRunner.out.log"
nssm set IchorClaudeRunner AppStderr "C:\nssm-logs\IchorClaudeRunner.err.log"

# 3. Start + verify
nssm start IchorClaudeRunner
Start-Sleep -Seconds 5
Get-Service IchorClaudeRunner
curl http://127.0.0.1:8766/healthz
```

### Migration option : switch to **Servy** (cf ROADMAP A.7)

NSSM is unmaintained since 2017. Servy (aelassas/servy on GitHub)
is the modern alternative for Win11 — better env-var management,
process tree control, toast notifications. Phase A.7 of the
ROADMAP plans this migration. **Do NOT do it during an outage** —
schedule it.

### Path E — Couche-2 530 storm (recurrence, round-27 ADR-087 ref)

**Symptom** : 3+ HTTP 530 errors in <60 s on `/v1/agent-task/async`, all retries exhausted, Couche-2 agent (cb_nlp / news_nlp / sentiment / positioning / macro) fails with `AllProvidersFailed` after both the inner envelope (4 retries × backoff 5/15/45/90 s = 155 s) AND the outer CLI retry (60 s × 3 attempts = ~5 min) exhausted.

**Diagnostic steps** :

1. Confirm CF tunnel is alive on Win11 :

   ```powershell
   cloudflared.exe tunnel list
   # Look for tunnel 97aab1f6 status "active"
   ```

2. Bypass-tunnel origin check (must return 200) :

   ```powershell
   curl http://127.0.0.1:8766/healthz
   ```

3. Check QUIC vs HTTP/2 protocol :
   ```powershell
   Get-Process cloudflared | Select-Object CommandLine
   # If --protocol quic seen, this is likely the storm cause.
   ```

**Fix sequence** :

A. **Force `--protocol http2`** (the major lever — round-27 researcher identified QUIC handshake timeouts as primary 530 storm cause, cf [cloudflared issue #1534](https://github.com/cloudflare/cloudflared/issues/1534)) :

```powershell
# Edit start script to add --protocol http2 flag
notepad "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\start-cloudflared-user.ps1"
# Replace argument list to include : --protocol http2
# Restart :
Stop-Process -Name cloudflared -Force
& "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\start-cloudflared-user.ps1"
```

B. **Verify retry envelope shipped** (round-27 PR) :

```bash
# Inner async envelope (claude_runner.py:332)
grep "submit_backoff = (5.0, 15.0, 45.0, 90.0)" packages/agents/src/ichor_agents/claude_runner.py
# Outer CLI envelope (run_couche2_agent.py:99-100)
grep -E "max_attempts = 3|HTTP 530" apps/api/src/ichor_api/cli/run_couche2_agent.py
```

C. **If origin OK but edge 530 > 5 min** : CF edge POP issue, escalate Cloudflare Tunnel support — out of Ichor scope.

**Escalation** : if Couche-2 has full 24h of 530s, the cron will keep firing with full retries (~5 min/fire × 5 agents × 4 sessions/day = ~100 min/day worst case). Watch `journalctl -u ichor-couche2-cb_nlp.service` for storm pattern recognition.

## Post-incident

- Log incident in `docs/SESSION_LOG_YYYY-MM-DD.md` with timeline.
- If standalone uvicorn was the recovery path, **add a note to
  return to NSSM** when the cause-of-paused is debugged.
- If the issue is Cloudflare Tunnel, also follow RUNBOOK-012.
- File a post-mortem if MTTR > 30 min.
- Update this RUNBOOK if a step was missing or wrong.

## Related

- RUNBOOK-008 — Anthropic key revoked (cause of `claude -p` 403).
- RUNBOOK-012 — CF quick tunnel down.
- RUNBOOK-013 — Claude Max quota saturated.
- ADR-009 — Voie D constraint (no Anthropic SDK ; runner is the only path).
- ADR-021/023 — Couche-2 routing through this runner.
