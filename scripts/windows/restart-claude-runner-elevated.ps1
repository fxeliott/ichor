# Elevated restart of IchorClaudeRunner service.
# Sets the missing ICHOR_RUNNER_ENVIRONMENT=development var that
# the runner's startup guard requires, then restarts.
#
# Writes a structured result to D:\Ichor\.cache\restart-result.txt so
# the caller can read it back without scraping console output.

$ErrorActionPreference = 'Continue'
$out = 'D:\Ichor\.cache\restart-result.txt'
$lines = @()
$lines += "started_at=$(Get-Date -Format 'o')"

try {
    $nssm = 'C:\nssm\nssm.exe'
    if (-not (Test-Path $nssm)) { throw "NSSM not found at $nssm" }

    # Stop first; ignore failures since the service may already be stopped
    & $nssm stop IchorClaudeRunner 2>&1 | Out-Null
    Start-Sleep -Seconds 2

    # Atomically replace the env var list (NSSM CLI: each "KEY=VAL" is one arg)
    & $nssm set IchorClaudeRunner AppEnvironmentExtra `
        'ICHOR_RUNNER_HOST=127.0.0.1' `
        'ICHOR_RUNNER_PORT=8765' `
        'ICHOR_RUNNER_LOG_LEVEL=INFO' `
        'ICHOR_RUNNER_REQUIRE_CF_ACCESS=false' `
        'ICHOR_RUNNER_CLAUDE_BINARY=C:\Users\eliot\.local\bin\claude.exe' `
        'ICHOR_RUNNER_ENVIRONMENT=development' 2>&1 | ForEach-Object { $lines += "nssm_set: $_" }

    & $nssm start IchorClaudeRunner 2>&1 | ForEach-Object { $lines += "nssm_start: $_" }

    # Poll healthz for up to 20 s
    $ok = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/healthz' -TimeoutSec 3
            $lines += "healthz_attempt_$($i)=$($r | ConvertTo-Json -Compress)"
            if ($r.status -eq 'ok') { $ok = $true; break }
        } catch {
            # not ready yet
        }
    }

    # Probe the new endpoint route too (404 is fine — auth/routing test)
    try {
        $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/v1/agent-task' -Method Post `
            -ContentType 'application/json' `
            -Body '{"system":"smoke","prompt":"smoke"}' `
            -SkipHttpErrorCheck -TimeoutSec 5
        $lines += "agent_task_status=$($resp.StatusCode)"
        $body = $resp.Content
        if ($body.Length -gt 400) { $body = $body.Substring(0, 400) }
        $lines += "agent_task_body=$body"
    } catch {
        $lines += "agent_task_error=$_"
    }

    $lines += "result=$(if ($ok) { 'OK' } else { 'FAIL' })"
} catch {
    $lines += "exception=$_"
    $lines += "result=EXCEPTION"
}

$lines += "finished_at=$(Get-Date -Format 'o')"
Set-Content -Path $out -Value $lines -Encoding utf8
