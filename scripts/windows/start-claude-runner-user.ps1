# Launch Ichor claude-runner as user (no admin needed)
# Bound to port 8766 — runs as Eliot user so claude CLI finds OAuth credentials.
#
# This replaces the LocalSystem NSSM service approach (which couldn't access
# user-keychain credentials).

$ErrorActionPreference = "Continue"

$ichorBin = "D:\Ichor\apps\claude-runner\.venv\Scripts\uvicorn.exe"
$logDir = "$env:USERPROFILE\.cloudflared"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Kill any existing uvicorn on 8766
Get-Process uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$env:ICHOR_RUNNER_HOST = "127.0.0.1"
$env:ICHOR_RUNNER_PORT = "8766"
$env:ICHOR_RUNNER_LOG_LEVEL = "INFO"
$env:ICHOR_RUNNER_REQUIRE_CF_ACCESS = "false"
$env:ICHOR_RUNNER_CLAUDE_BINARY = "C:\Users\eliot\.local\bin\claude.exe"

Start-Process $ichorBin -ArgumentList "ichor_claude_runner.main:app","--host","127.0.0.1","--port","8766","--no-access-log" `
    -WorkingDirectory "D:\Ichor\apps\claude-runner" `
    -RedirectStandardOutput "$logDir\uvicorn-user.log" `
    -RedirectStandardError "$logDir\uvicorn-user.err" `
    -WindowStyle Hidden -PassThru | Select-Object Id, ProcessName

Start-Sleep -Seconds 4
try {
    $h = Invoke-RestMethod http://127.0.0.1:8766/healthz -TimeoutSec 5
    Write-Host "claude-runner OK: $($h | ConvertTo-Json -Compress)"
} catch {
    Write-Warning "healthz failed: $_"
}
