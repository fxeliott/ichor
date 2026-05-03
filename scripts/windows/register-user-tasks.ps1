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

Write-Host ""
Write-Host "Both tasks will start at next logon. To start NOW manually:"
Write-Host "  Start-ScheduledTask -TaskName IchorClaudeRunnerUser"
Write-Host "  Start-ScheduledTask -TaskName IchorCloudflaredUser"
