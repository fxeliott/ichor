# Launch cloudflared in user mode (no admin) — uses ~/.cloudflared/config.yml
# Runs alongside start-claude-runner-user.ps1 to provide the Hetzner-Win11 tunnel.
#
# Round-28 (2026-05-13) : added --protocol http2 to eliminate the QUIC
# handshake-timeout class of 530 storms observed 2026-05-13 08:47 CEST
# on news_nlp. See RUNBOOK-014 Path E + cloudflared issue #1534. QUIC
# handshake retries (2/4/8/16/32/64s) can synthesise multi-second 530s
# at the CF edge ; http2 long-connection is more stable for our use
# case (1 origin, low QPS). Round-28 fix verified live : 4 tunnel
# connections registered with protocol=http2 (mrs04/mrs06 POPs).

$ErrorActionPreference = "Continue"

$cloudflared = "C:\Users\eliot\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe"
$tunnelUUID = (Get-Content "$env:USERPROFILE\.cloudflared\tunnel-uuid.txt" -ErrorAction SilentlyContinue)
if (-not $tunnelUUID) { $tunnelUUID = "97aab1f6-bd98-4743-8f65-78761388fe77" }

# Kill existing
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# --protocol http2 : forces HTTP/2 transport, bypassing the QUIC default
# that can cause 530 storms under handshake-timeout conditions.
Start-Process $cloudflared -ArgumentList "tunnel","--protocol","http2","run",$tunnelUUID `
    -RedirectStandardOutput "$env:USERPROFILE\.cloudflared\cf-user.log" `
    -RedirectStandardError "$env:USERPROFILE\.cloudflared\cf-user.err" `
    -WindowStyle Hidden -PassThru | Select-Object Id, ProcessName

Start-Sleep -Seconds 8
Write-Host "cloudflared launched. Latest log lines:"
Get-Content "$env:USERPROFILE\.cloudflared\cf-user.log" -Tail 5 -ErrorAction SilentlyContinue
