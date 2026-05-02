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

# --- 2. Locate or install NSSM (try winget package first, then nssm.cc) ---
$nssmExe = $null
# Path 1: winget-installed NSSM (fastest, most reliable)
$wingetNssm = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*" `
    -Recurse -Filter "nssm.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($wingetNssm) {
    $nssmExe = $wingetNssm.FullName
    Write-Host "Found NSSM via winget: $nssmExe"
}
# Path 2: previously-installed at C:\nssm\
elseif (Test-Path "C:\nssm\nssm.exe") {
    $nssmExe = "C:\nssm\nssm.exe"
    Write-Host "Found NSSM at: $nssmExe"
}
# Path 3: download from nssm.cc
else {
    Write-Host "NSSM not found. Trying winget install..."
    & winget install --id NSSM.NSSM --accept-source-agreements --accept-package-agreements --silent 2>&1 | Out-Null
    $wingetNssm = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*" `
        -Recurse -Filter "nssm.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetNssm) {
        $nssmExe = $wingetNssm.FullName
        Write-Host "Installed NSSM via winget: $nssmExe"
    } else {
        Write-Host "winget failed, falling back to nssm.cc download..."
        try {
            $url = "https://nssm.cc/release/nssm-2.24.zip"
            $tmp = "$env:TEMP\nssm.zip"
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -TimeoutSec 30
            Expand-Archive -Path $tmp -DestinationPath "C:\nssm-tmp" -Force
            New-Item -ItemType Directory -Force -Path "C:\nssm" | Out-Null
            Copy-Item "C:\nssm-tmp\nssm-2.24\win64\nssm.exe" -Destination "C:\nssm\nssm.exe" -Force
            Remove-Item -Recurse -Force "C:\nssm-tmp"
            Remove-Item $tmp
            $nssmExe = "C:\nssm\nssm.exe"
        } catch {
            Write-Error "All NSSM install methods failed. Last error: $_"
            Write-Error "Manual fix: install NSSM via winget install --id NSSM.NSSM"
            exit 1
        }
    }
}

# --- 3. Locate claude binary (needed for claude-runner subprocess calls) ---
$claudeBin = $null
try { $claudeBin = (Get-Command claude -ErrorAction Stop).Source } catch {}
if (-not $claudeBin) {
    # Common install locations for Claude Code
    $places = @(
        "$env:USERPROFILE\.local\bin\claude.exe",
        "$env:LOCALAPPDATA\Programs\claude\claude.exe",
        "$env:USERPROFILE\AppData\Roaming\npm\claude.cmd"
    )
    foreach ($p in $places) {
        if (Test-Path $p) { $claudeBin = $p; break }
    }
}
if ($claudeBin) {
    Write-Host "Found claude binary: $claudeBin"
} else {
    Write-Warning "claude binary NOT found. Service will start but /healthz will report 'down' until you install Claude Code."
    $claudeBin = "claude"  # fallback to PATH lookup at runtime
}

# --- 4. Setup Python venv for the service ---
$venvDir = "$IchorRoot\apps\claude-runner\.venv"
$pyExe = "$venvDir\Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    Write-Host "Creating venv at $venvDir..."
    python -m venv $venvDir
    & $pyExe -m pip install --upgrade pip
}
# Always (re)install — handles stale venv from previous runs
Write-Host "Installing claude-runner deps + package (editable)..."
& $pyExe -m pip install -e "$IchorRoot\apps\claude-runner[dev]"

# --- 5. Stop + remove existing service if present ---
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Stopping + removing existing service..."
    if ($existing.Status -eq "Running") { Stop-Service $ServiceName -Force }
    & $nssmExe remove $ServiceName confirm
}

# --- 6. Install service via NSSM ---
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
# REQUIRE_CF_ACCESS starts at false so the service can boot before the tunnel
# is configured. Re-set to true once Cloudflare Tunnel + Access app exist:
#   nssm set IchorClaudeRunner AppEnvironmentExtra ... ICHOR_RUNNER_REQUIRE_CF_ACCESS=true ICHOR_RUNNER_CF_ACCESS_TEAM_DOMAIN=... ICHOR_RUNNER_CF_ACCESS_AUD_TAG=...
& $nssmExe set $ServiceName AppEnvironmentExtra `
    "ICHOR_RUNNER_HOST=127.0.0.1" `
    "ICHOR_RUNNER_PORT=$Port" `
    "ICHOR_RUNNER_LOG_LEVEL=INFO" `
    "ICHOR_RUNNER_REQUIRE_CF_ACCESS=false" `
    "ICHOR_RUNNER_CLAUDE_BINARY=$claudeBin"

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
