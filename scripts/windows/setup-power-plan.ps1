# Configure Win11 power plan to never sleep + never hibernate.
# Required for Voie D: claude-runner must be available 24/7 for Hetzner cron.
# Run as Administrator.

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Must run as Administrator."
    exit 1
}

Write-Host "=== Setting power plan to High Performance ==="
# High Performance plan GUID
$highPerfGuid = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
powercfg /setactive $highPerfGuid

Write-Host "=== Disable sleep + hibernate (AC + DC) ==="
# Sleep timeout
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
# Hibernate timeout
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
# Disable hibernate file entirely (saves ~16 GB on disk)
powercfg /hibernate off
# Display timeout (allowed to turn off, claude-runner doesn't need display)
powercfg /change monitor-timeout-ac 15
powercfg /change monitor-timeout-dc 5

Write-Host "=== Disable USB selective suspend (keeps tunnel + ethernet stable) ==="
powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /setdcvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /setactive SCHEME_CURRENT

Write-Host ""
Write-Host "=== Current state ==="
powercfg /getactivescheme
powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
powercfg /q SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE

Write-Host ""
Write-Host "Done. Verify: machine should never sleep on its own."
Write-Host "Note: this does NOT prevent Windows Update from rebooting."
Write-Host "      To window updates outside Paris briefing hours, see"
Write-Host "      gpedit.msc -> Computer Configuration -> Administrative Templates"
Write-Host "                 -> Windows Components -> Windows Update -> Configure"
Write-Host "                 -> Active hours: e.g. 08:00 -> 23:00 Europe/Paris."
