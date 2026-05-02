# Install Ichor claude-runner as a Windows service (NSSM-based)
# Run as Administrator.
#
# Uses NSSM (Non-Sucking Service Manager) because Python apps don't natively
# integrate with Windows SCM. NSSM wraps `python.exe -m uvicorn ...` as a
# proper service that auto-starts on boot, restarts on crash, etc.

param(
    [string]$IchorRoot = "D:\Ichor",
    [string]$ServiceName = "IchorClaudeRunner",
    [string]$Port = "8765"
)

$ErrorActionPreference = "Stop"

# --- 1. Verify admin ---
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Must run as Administrator."
    exit 1
}

# --- 2. Install NSSM if missing ---
$nssmExe = "C:\nssm\nssm.exe"
if (-not (Test-Path $nssmExe)) {
    Write-Host "Installing NSSM..."
    $url = "https://nssm.cc/release/nssm-2.24.zip"
    $tmp = "$env:TEMP\nssm.zip"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    Expand-Archive -Path $tmp -DestinationPath "C:\nssm-tmp" -Force
    New-Item -ItemType Directory -Force -Path "C:\nssm" | Out-Null
    Copy-Item "C:\nssm-tmp\nssm-2.24\win64\nssm.exe" -Destination $nssmExe -Force
    Remove-Item -Recurse -Force "C:\nssm-tmp"
    Remove-Item $tmp
}
Write-Host "NSSM at $nssmExe"

# --- 3. Setup Python venv for the service ---
$venvDir = "$IchorRoot\apps\claude-runner\.venv"
$pyExe = "$venvDir\Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    Write-Host "Creating venv at $venvDir..."
    python -m venv $venvDir
    & $pyExe -m pip install --upgrade pip
    & $pyExe -m pip install -e "$IchorRoot\apps\claude-runner[dev]"
} else {
    Write-Host "Reusing existing venv $venvDir"
    & $pyExe -m pip install -e "$IchorRoot\apps\claude-runner[dev]" --quiet
}

# --- 4. Stop + remove existing service if present ---
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Stopping + removing existing service..."
    if ($existing.Status -eq "Running") { Stop-Service $ServiceName -Force }
    & $nssmExe remove $ServiceName confirm
}

# --- 5. Install service via NSSM ---
$uvicornCmd = "$venvDir\Scripts\uvicorn.exe"
$uvicornArgs = "ichor_claude_runner.main:app --host 127.0.0.1 --port $Port --no-access-log"

Write-Host "Installing service '$ServiceName'..."
& $nssmExe install $ServiceName $uvicornCmd $uvicornArgs
& $nssmExe set $ServiceName AppDirectory "$IchorRoot\apps\claude-runner"
& $nssmExe set $ServiceName DisplayName "Ichor Claude Runner"
& $nssmExe set $ServiceName Description "Local FastAPI :$Port wrapping `claude -p` for Hetzner cron jobs (Voie D)"
& $nssmExe set $ServiceName Start SERVICE_AUTO_START
& $nssmExe set $ServiceName AppStdout "$IchorRoot\apps\claude-runner\logs\stdout.log"
& $nssmExe set $ServiceName AppStderr "$IchorRoot\apps\claude-runner\logs\stderr.log"
& $nssmExe set $ServiceName AppRotateFiles 1
& $nssmExe set $ServiceName AppRotateBytes 10485760  # 10 MB

# Restart on failure: 5s delay, infinite retries
& $nssmExe set $ServiceName AppExit Default Restart
& $nssmExe set $ServiceName AppRestartDelay 5000

# Environment variables for the service
& $nssmExe set $ServiceName AppEnvironmentExtra `
    "ICHOR_RUNNER_HOST=127.0.0.1" `
    "ICHOR_RUNNER_PORT=$Port" `
    "ICHOR_RUNNER_LOG_LEVEL=INFO" `
    "ICHOR_RUNNER_REQUIRE_CF_ACCESS=true"
# Cloudflare-specific vars (CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD_TAG) must be
# added by hand once Eliot has created the Access application — see
# infra/cloudflare/README.md.

# --- 6. Ensure log directory exists ---
New-Item -ItemType Directory -Force -Path "$IchorRoot\apps\claude-runner\logs" | Out-Null

# --- 7. Start the service ---
Write-Host "Starting service..."
Start-Service $ServiceName

Start-Sleep -Seconds 3
Get-Service $ServiceName

# --- 8. Verify health ---
Write-Host "Verifying /healthz..."
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 10
    Write-Host "Health: $($r | ConvertTo-Json -Compress)"
} catch {
    Write-Warning "Health check failed: $_"
    Write-Warning "Check logs at $IchorRoot\apps\claude-runner\logs\stderr.log"
}

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Service: $ServiceName"
Write-Host "URL: http://127.0.0.1:$Port"
Write-Host "Logs: $IchorRoot\apps\claude-runner\logs\"
Write-Host ""
Write-Host "Next: install + configure cloudflared (see infra/cloudflare/README.md)"
