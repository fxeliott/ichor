# Fix Ichor claude-runner auth: configure NSSM service to use Eliot's user profile
# (so `claude -p` finds OAuth credentials in C:\Users\eliot\.claude\.credentials.json)
#
# Why: Windows services run as LocalSystem by default and look in
# C:\Windows\System32\config\systemprofile\.claude\ which is empty. We override
# USERPROFILE / APPDATA / LOCALAPPDATA env vars so the claude CLI finds Eliot's
# credentials.
#
# Run as Administrator.

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Must run as Administrator."
    exit 1
}

$nssm = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*" -Recurse -Filter "nssm.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if (-not $nssm) {
    $nssm = "C:\nssm\nssm.exe"
}
if (-not (Test-Path $nssm)) {
    Write-Error "NSSM not found. Install via 'winget install --id NSSM.NSSM'"
    exit 1
}
Write-Host "Using NSSM: $nssm"

Write-Host "Setting AppEnvironmentExtra (Ichor + claude binary path + user profile)..."
& $nssm set IchorClaudeRunner AppEnvironmentExtra `
    "ICHOR_RUNNER_HOST=127.0.0.1" `
    "ICHOR_RUNNER_PORT=8765" `
    "ICHOR_RUNNER_LOG_LEVEL=INFO" `
    "ICHOR_RUNNER_REQUIRE_CF_ACCESS=false" `
    "ICHOR_RUNNER_CLAUDE_BINARY=C:\Users\eliot\.local\bin\claude.exe" `
    "USERPROFILE=C:\Users\eliot" `
    "APPDATA=C:\Users\eliot\AppData\Roaming" `
    "LOCALAPPDATA=C:\Users\eliot\AppData\Local" `
    "HOMEDRIVE=C:" `
    "HOMEPATH=\Users\eliot"

Write-Host "Restarting service..."
Restart-Service IchorClaudeRunner -Force
Start-Sleep -Seconds 5

Write-Host "---Service status---"
Get-Service IchorClaudeRunner | Format-List Name, Status, StartType

Write-Host "---healthz---"
try {
    $h = Invoke-RestMethod http://127.0.0.1:8765/healthz -TimeoutSec 10
    $h | ConvertTo-Json -Depth 5
} catch {
    Write-Warning "healthz failed: $_"
}

Write-Host ""
Write-Host "DONE — tell Claude 'runner restart ok'"
