# enable-cf-access-runner.ps1 — flip Win11 IchorClaudeRunner to require CF Access
#
# Pre-requisites (Eliot must complete these first via guide §1) :
#   1. Cloudflare Zero Trust Access enabled on the account.
#   2. Access Application "Ichor Claude Runner" created for hostname
#      claude-runner.fxmilyapp.com with `Service Auth` policy.
#   3. Service token generated. The credentials live in
#      /etc/ichor/api.env on Hetzner already (verified W93 — present).
#   4. The Application's AUD (Audience) tag is known. Get it via
#      Cloudflare dashboard -> Zero Trust -> Access -> Applications ->
#      Ichor Claude Runner -> Overview -> "Application Audience (AUD) Tag".
#
# Usage (PowerShell as Administrator) :
#   .\enable-cf-access-runner.ps1 -TeamDomain ichor-team.cloudflareaccess.com `
#                                  -ApplicationAud <AUD-from-CF-dashboard>
#
# After running, the NSSM service IchorClaudeRunner is restarted with
# REQUIRE_CF_ACCESS=true, and the tunnel will reject any request that
# doesn't carry a valid CF Access JWT (= signed by the team domain
# with the matching AUD).
#
# Reference : ADR-077 PRE-1, guide §1 Tier 5.

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$TeamDomain,

    [Parameter(Mandatory=$true)]
    [string]$ApplicationAud
)

$ErrorActionPreference = "Stop"

# Sanity check : NSSM available + service exists.
$nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssm) {
    Write-Error "nssm.exe not found on PATH. Install via 'winget install NSSM.NSSM' first."
    exit 2
}

$status = & nssm status IchorClaudeRunner 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Service IchorClaudeRunner not registered. Cannot continue."
    exit 2
}
Write-Output "[1/4] NSSM service status : $status"

# Read current AppEnvironmentExtra so we keep all pre-existing vars
# and only flip the CF Access ones. NSSM `set AppEnvironmentExtra`
# REPLACES the whole list, so we must reconstruct it fully.
$currentEnv = & nssm get IchorClaudeRunner AppEnvironmentExtra 2>&1
Write-Output "[2/4] Current AppEnvironmentExtra :"
$currentEnv | ForEach-Object { Write-Output "      $_" }

# Build the new env list :
#  - keep ICHOR_RUNNER_HOST, ICHOR_RUNNER_PORT, ICHOR_RUNNER_LOG_LEVEL,
#    ICHOR_RUNNER_CLAUDE_BINARY, ICHOR_RUNNER_ENVIRONMENT (pre-existing)
#  - flip ICHOR_RUNNER_REQUIRE_CF_ACCESS to true
#  - add ICHOR_RUNNER_CF_ACCESS_TEAM_DOMAIN
#  - add ICHOR_RUNNER_CF_ACCESS_APPLICATION_AUD
$newEnv = @()
$cfAccessVars = @(
    "ICHOR_RUNNER_REQUIRE_CF_ACCESS",
    "ICHOR_RUNNER_CF_ACCESS_TEAM_DOMAIN",
    "ICHOR_RUNNER_CF_ACCESS_APPLICATION_AUD"
)
foreach ($line in $currentEnv) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $key = ($line -split "=", 2)[0]
    if ($cfAccessVars -contains $key) { continue }  # drop pre-existing CF Access vars
    $newEnv += $line
}
$newEnv += "ICHOR_RUNNER_REQUIRE_CF_ACCESS=true"
$newEnv += "ICHOR_RUNNER_CF_ACCESS_TEAM_DOMAIN=$TeamDomain"
$newEnv += "ICHOR_RUNNER_CF_ACCESS_APPLICATION_AUD=$ApplicationAud"

Write-Output "[3/4] New AppEnvironmentExtra :"
$newEnv | ForEach-Object { Write-Output "      $_" }

# Atomic update : NSSM `set` replaces, then restart.
& nssm set IchorClaudeRunner AppEnvironmentExtra @newEnv
if ($LASTEXITCODE -ne 0) {
    Write-Error "nssm set failed (exit $LASTEXITCODE). Service env unchanged."
    exit 3
}
& nssm restart IchorClaudeRunner
Start-Sleep -Seconds 3

$newStatus = & nssm status IchorClaudeRunner 2>&1
Write-Output "[4/4] NSSM status after restart : $newStatus"

if ($newStatus -ne "SERVICE_RUNNING") {
    Write-Warning "Service did NOT come back up. Check NSSM stderr log :"
    Write-Warning "  nssm get IchorClaudeRunner AppStderr"
    exit 4
}

# Smoke test : local healthz must still work.
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/healthz" -TimeoutSec 5
    Write-Output ""
    Write-Output "Local healthz OK : status=$($health.status), claude_cli=$($health.claude_cli_available)"
} catch {
    Write-Warning "Local healthz failed : $_"
    Write-Warning "Service may still be booting. Re-run curl in 30s."
}

Write-Output ""
Write-Output "DONE. CF Access enforcement is now ACTIVE on the Win11 runner."
Write-Output ""
Write-Output "Next : verify the tunnel rejects unauthenticated requests :"
Write-Output "  curl -i https://claude-runner.fxmilyapp.com/healthz"
Write-Output "  (expect HTTP 401 / 403)"
Write-Output ""
Write-Output "And accepts authenticated ones :"
Write-Output "  curl -i -H 'CF-Access-Client-Id: <id>' -H 'CF-Access-Client-Secret: <secret>' \\"
Write-Output "       https://claude-runner.fxmilyapp.com/healthz"
Write-Output "  (expect HTTP 200)"
