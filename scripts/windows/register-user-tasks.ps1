# Register user-level scheduled tasks for claude-runner + cloudflared
# Runs as the current user (Eliot), no admin elevation needed.
# Tasks fire at logon and restart on failure.
#
# Run as Eliot (not admin).

$ErrorActionPreference = "Continue"

# --- Task 1: claude-runner (uvicorn user-mode :8766) ---
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File D:\Ichor\scripts\windows\start-claude-runner-user.ps1"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "IchorClaudeRunnerUser" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered task: IchorClaudeRunnerUser"

# --- Task 2: cloudflared tunnel ---
$action2 = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File D:\Ichor\scripts\windows\start-cloudflared-user.ps1"
$trigger2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName "IchorCloudflaredUser" -Action $action2 -Trigger $trigger2 -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered task: IchorCloudflaredUser"

# --- Task 3: runner self-heal watchdog (every 5 min) ---
# Probes 127.0.0.1:8766/healthz and self-heals the runner SPOF (dead process,
# foreign port squatter, stale claude.exe path / WinError-2 class). Single-shot
# + idempotent (see runner-watchdog.ps1 .SYNOPSIS + RUNBOOK-014). Default run is
# NON-destructive (no -KillRogue): a foreign squatter is reported, not killed.
# Before the S02 audit (2026-06-17) this watchdog existed but was registered by
# NO script -- so a reconstruct-from-repo left the runner with zero auto-repair.
$wdAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File D:\Ichor\scripts\windows\runner-watchdog.ps1"
# PowerShell has no direct -AtLogOn + -RepetitionInterval, so graft the
# 5-min repetition from a -Once trigger onto the AtLogOn trigger (standard idiom).
$wdTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$wdTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition
Register-ScheduledTask -TaskName "IchorRunnerWatchdog" -Action $wdAction -Trigger $wdTrigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered task: IchorRunnerWatchdog (self-heal probe every 5 min)"

Write-Host ""
Write-Host "All three tasks will start at next logon. To start NOW manually:"
Write-Host "  Start-ScheduledTask -TaskName IchorClaudeRunnerUser"
Write-Host "  Start-ScheduledTask -TaskName IchorCloudflaredUser"
Write-Host "  Start-ScheduledTask -TaskName IchorRunnerWatchdog"
