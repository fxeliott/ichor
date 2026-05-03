# Launch cloudflared in user mode (no admin) — uses ~/.cloudflared/config.yml
# Runs alongside start-claude-runner-user.ps1 to provide the Hetzner-Win11 tunnel.

$ErrorActionPreference = "Continue"

$cloudflared = "C:\Users\eliot\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe"
$tunnelUUID = (Get-Content "$env:USERPROFILE\.cloudflared\tunnel-uuid.txt" -ErrorAction SilentlyContinue)
if (-not $tunnelUUID) { $tunnelUUID = "97aab1f6-bd98-4743-8f65-78761388fe77" }

# Kill existing
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Start-Process $cloudflared -ArgumentList "tunnel","run",$tunnelUUID `
    -RedirectStandardOutput "$env:USERPROFILE\.cloudflared\cf-user.log" `
    -RedirectStandardError "$env:USERPROFILE\.cloudflared\cf-user.err" `
    -WindowStyle Hidden -PassThru | Select-Object Id, ProcessName

Start-Sleep -Seconds 8
Write-Host "cloudflared launched. Latest log lines:"
Get-Content "$env:USERPROFILE\.cloudflared\cf-user.log" -Tail 5 -ErrorAction SilentlyContinue
