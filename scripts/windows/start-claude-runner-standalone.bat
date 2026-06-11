@echo off
REM Standalone launcher for the claude-runner — bypass the NSSM
REM service while the production-guard environment fix is pending
REM admin attention. Runs in the background under the user account.
REM
REM Why this exists:
REM   The IchorClaudeRunner NSSM service is in 'Paused' state because
REM   ICHOR_RUNNER_ENVIRONMENT=development was lost from the NSSM env
REM   list, so the runner's startup guard refuses to boot in
REM   "production with require_cf_access=false". Fixing NSSM needs
REM   admin elevation; this script provides a user-level fallback that
REM   keeps Couche-2 operational in the meantime.
REM
REM Port 8766 is what cloudflared forwards to (verified 2026-05-06).

setlocal
set ICHOR_RUNNER_HOST=127.0.0.1
set ICHOR_RUNNER_PORT=8766
set ICHOR_RUNNER_LOG_LEVEL=INFO
set ICHOR_RUNNER_REQUIRE_CF_ACCESS=false
REM 2026-05-29 DURABLE fix: auto-detect the real claude.exe at every launch so a
REM  future Claude install/update that moves the binary can NEVER re-break the
REM  runner (the WinError 2 outage was a now-deleted hardcoded ~/.local/bin path).
REM  Probes the 3 known install locations: npm-global bundle -> native -> legacy.
set "ICHOR_RUNNER_CLAUDE_BINARY="
if exist "%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe" set "ICHOR_RUNNER_CLAUDE_BINARY=%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
if not defined ICHOR_RUNNER_CLAUDE_BINARY if exist "%LOCALAPPDATA%\AnthropicClaude\claude.exe" set "ICHOR_RUNNER_CLAUDE_BINARY=%LOCALAPPDATA%\AnthropicClaude\claude.exe"
if not defined ICHOR_RUNNER_CLAUDE_BINARY if exist "%USERPROFILE%\.local\bin\claude.exe" set "ICHOR_RUNNER_CLAUDE_BINARY=%USERPROFILE%\.local\bin\claude.exe"
set ICHOR_RUNNER_ENVIRONMENT=development
REM 8 assets x 4 passes per session-card batch = 32 reqs in ~15 min.
REM Default rate_limit_per_hour=30 throttles the 8th asset on a clean
REM batch (observed 2026-05-08 wave 23 SPX500 429). Raise to 120/h
REM (~2 reqs/min sustainable) so a full 4-pass session-card sweep
REM plus concurrent Couche-2 traffic fits under quota.
set ICHOR_RUNNER_RATE_LIMIT_PER_HOUR=120

cd /d D:\Ichor\apps\claude-runner

REM 2026-06-02 — --timeout-keep-alive 75 fixes the async-poll 502 race.
REM uvicorn closes idle keep-alive connections after 5s by default; the
REM Hetzner orchestrator polls /v1/.../async/{id} every 5s, so cloudflared
REM reuses a connection right as uvicorn closes it -> EOF -> 502 -> the
REM whole card aborts mid-generation. A keep-alive >> the 5s poll interval
REM removes the race entirely (witnessed: full 4-pass+Pass-6 card, 0x 502).
REM 2026-06-11 (ADR-110 session) — .venv-live, not .venv: the NSSM zombie
REM  (IchorClaudeRunner service, SYSTEM, port 8765) holds file locks inside
REM  .venv (uvicorn.exe + loaded .pyd), which corrupted a `uv sync` mid-flight.
REM  .venv-live is a clean lock-synced env the zombie has never touched.
REM  After the NSSM service is stopped+disabled (needs admin), either venv
REM  works; .venv-live stays canonical until then.
start "" /B "D:\Ichor\apps\claude-runner\.venv-live\Scripts\uvicorn.exe" ichor_claude_runner.main:app --host 127.0.0.1 --port 8766 --no-access-log --timeout-keep-alive 75
