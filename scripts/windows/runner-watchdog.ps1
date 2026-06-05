<#
.SYNOPSIS
  Self-heal watchdog for the Ichor Win11 claude-runner (Session 02, 2026-06-05).

.DESCRIPTION
  The live pipeline depends on a single local uvicorn serving
  `ichor_claude_runner.main:app` on 127.0.0.1:8766. Historically it has
  failed in three environmental ways that silently killed whole batches
  (ny_close 0/6 + Couche-2 down):

    1. The process died / never started (Win11 reboot without login, crash,
       a moved `claude.exe` -> WinError 2).
    2. A FOREIGN process squats the port (witnessed 2026-06-04: a rogue
       `python -m http.server 8766` held :8766, so the runner could not bind
       and clients got connection/501 errors).
    3. The runner is up but `/healthz` reports `status=down`
       (claude CLI not reachable) -- restarting the same broken thing does
       NOT help; a human must fix the binary path.

  This watchdog probes /healthz and self-heals cases 1 & 2 (our own hung
  runner is auto-restarted; a FOREIGN squatter is only killed with the
  explicit -KillRogue switch, so the default run is never destructive).
  Case 3 is reported loudly, not loop-restarted.

  Designed to be run every ~5 min by Task Scheduler (see RUNBOOK-014
  "Self-heal watchdog"). Idempotent, single-shot, exits with a status code.

.PARAMETER Port            Runner port (default 8766, IPv4 127.0.0.1).
.PARAMETER Bat             Canonical launcher .bat.
.PARAMETER LogFile         Append-only log.
.PARAMETER KillRogue       Kill a FOREIGN process squatting the port, then restart.
.PARAMETER TimeoutSec      Per-HTTP probe timeout.

.OUTPUTS
  Exit 0 = healthy or healed. 2 = restarted, still not healthy.
  3 = status=down (claude CLI broken, human needed). 4 = foreign squatter,
  -KillRogue not set (no action taken). 5 = unexpected error.
#>
[CmdletBinding()]
param(
    [int]$Port = 8766,
    [string]$Bat = 'D:\Ichor\scripts\windows\start-claude-runner-standalone.bat',
    [string]$LogFile = 'D:\Ichor\.cache\runner-watchdog.log',
    [switch]$KillRogue,
    [int]$TimeoutSec = 6
)

$ErrorActionPreference = 'Continue'
$healthUrl = "http://127.0.0.1:$Port/healthz"

function Write-WatchLog {
    param([string]$Level, [string]$Message)
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'o'), $Level, $Message
    try {
        $dir = Split-Path -Parent $LogFile
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Add-Content -Path $LogFile -Value $line -Encoding utf8
    } catch { }
    Write-Output $line
}

function Get-Healthz {
    try {
        $r = Invoke-RestMethod -Uri $healthUrl -TimeoutSec $TimeoutSec -ErrorAction Stop
        return [pscustomobject]@{ Ok = $true; Body = $r }
    } catch {
        return [pscustomobject]@{ Ok = $false; Body = $null; Error = $_.Exception.Message }
    }
}

function Get-PortOwner {
    # Returns the listening process (or $null) on 127.0.0.1:$Port, with command line.
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    } catch {
        return $null
    }
    foreach ($c in $conns) {
        $proc = $null
        try { $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction Stop } catch { }
        return [pscustomobject]@{
            Pid         = $c.OwningProcess
            Name        = if ($proc) { $proc.Name } else { 'unknown' }
            CommandLine = if ($proc) { $proc.CommandLine } else { '' }
            LocalAddr   = $c.LocalAddress
        }
    }
    return $null
}

function Test-IsOurRunner {
    param([string]$CommandLine)
    if (-not $CommandLine) { return $false }
    return ($CommandLine -match 'ichor_claude_runner' -or `
            $CommandLine -match 'claude-runner' -or `
            $CommandLine -match "uvicorn.*$Port")
}

function Start-Runner {
    Write-WatchLog 'ACTION' "launching runner via $Bat"
    if (-not (Test-Path $Bat)) {
        Write-WatchLog 'CRIT' "launcher not found at $Bat -- cannot start"
        return
    }
    # Launch the .bat detached; it `start`s uvicorn in the background itself.
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $Bat -WindowStyle Hidden | Out-Null
}

function Wait-Healthy {
    param([int]$Seconds = 18)
    for ($i = 0; $i -lt $Seconds; $i++) {
        Start-Sleep -Seconds 1
        $h = Get-Healthz
        if ($h.Ok -and ($h.Body.status -eq 'ok' -or $h.Body.status -eq 'degraded')) {
            return $h
        }
    }
    return (Get-Healthz)
}

# ── Main ────────────────────────────────────────────────────────────────
try {
    $h = Get-Healthz

    if ($h.Ok) {
        $status = $h.Body.status
        $cli = $h.Body.claude_cli_available
        if ($status -eq 'down' -or $cli -eq $false) {
            Write-WatchLog 'CRIT' "runner UP but status=$status claude_cli_available=$cli -- claude CLI unreachable. Restarting the same process will NOT fix this; check the claude.exe path (WinError 2 class). See RUNBOOK-014 Path D."
            exit 3
        }
        Write-WatchLog 'OK' ("healthy status={0} in_flight={1} req_last_hour={2} version={3}" -f `
            $status, $h.Body.in_flight_subprocess, $h.Body.requests_last_hour, $h.Body.version)
        exit 0
    }

    # /healthz did not answer. Is anything holding the port?
    Write-WatchLog 'WARN' "healthz unreachable ($($h.Error)). Inspecting port $Port."
    $owner = Get-PortOwner

    if ($null -eq $owner) {
        # Port is free -> the runner is simply not running. Start it.
        Write-WatchLog 'INFO' "no listener on $Port -- runner not running. Starting."
        Start-Runner
        $after = Wait-Healthy
        if ($after.Ok -and ($after.Body.status -eq 'ok' -or $after.Body.status -eq 'degraded')) {
            Write-WatchLog 'HEALED' "runner restarted, status=$($after.Body.status)"
            exit 0
        }
        Write-WatchLog 'CRIT' "restarted but still unhealthy ($($after.Error)$($after.Body.status))"
        exit 2
    }

    # Something IS listening but /healthz failed.
    if (Test-IsOurRunner -CommandLine $owner.CommandLine) {
        # Our own hung runner -> safe to recycle (it's our process).
        Write-WatchLog 'INFO' "our runner appears hung (PID=$($owner.Pid) $($owner.Name)). Recycling."
        try { Stop-Process -Id $owner.Pid -Force -ErrorAction Stop } catch { Write-WatchLog 'WARN' "stop failed: $_" }
        Start-Sleep -Seconds 2
        Start-Runner
        $after = Wait-Healthy
        if ($after.Ok -and ($after.Body.status -eq 'ok' -or $after.Body.status -eq 'degraded')) {
            Write-WatchLog 'HEALED' "hung runner recycled, status=$($after.Body.status)"
            exit 0
        }
        Write-WatchLog 'CRIT' "recycled but still unhealthy ($($after.Error)$($after.Body.status))"
        exit 2
    }

    # FOREIGN process squats the port (e.g. rogue `python -m http.server 8766`).
    if ($KillRogue) {
        Write-WatchLog 'ACTION' "FOREIGN squatter on $Port PID=$($owner.Pid) name=$($owner.Name) cmd=[$($owner.CommandLine)] -- -KillRogue set, terminating."
        try { Stop-Process -Id $owner.Pid -Force -ErrorAction Stop } catch { Write-WatchLog 'WARN' "stop failed: $_" }
        Start-Sleep -Seconds 2
        Start-Runner
        $after = Wait-Healthy
        if ($after.Ok -and ($after.Body.status -eq 'ok' -or $after.Body.status -eq 'degraded')) {
            Write-WatchLog 'HEALED' "squatter removed, runner up status=$($after.Body.status)"
            exit 0
        }
        Write-WatchLog 'CRIT' "squatter removed but runner still unhealthy ($($after.Error)$($after.Body.status))"
        exit 2
    }

    Write-WatchLog 'CRIT' "FOREIGN process squats port $Port PID=$($owner.Pid) name=$($owner.Name) cmd=[$($owner.CommandLine)] -- refusing to kill a non-runner process. Re-run with -KillRogue to evict, or stop it manually. See RUNBOOK-014 'rogue process on :8766'."
    exit 4
} catch {
    Write-WatchLog 'ERROR' "watchdog exception: $_"
    exit 5
}
