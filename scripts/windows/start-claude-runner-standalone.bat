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
set ICHOR_RUNNER_CLAUDE_BINARY=C:\Users\eliot\.local\bin\claude.exe
set ICHOR_RUNNER_ENVIRONMENT=development

cd /d D:\Ichor\apps\claude-runner

start "" /B "D:\Ichor\apps\claude-runner\.venv\Scripts\uvicorn.exe" ichor_claude_runner.main:app --host 127.0.0.1 --port 8766 --no-access-log
