# One-off setup for apps/ichor-mcp on Win11 (W85, ADR-077).
#
# The MCP stdio server itself is spawned per-session by `claude -p
# --mcp-config ichor.mcp.json`, so there is NO daemon to register
# (unlike the claude-runner). This script just (1) bootstraps a
# Python 3.12 venv at `apps/ichor-mcp/.venv`, (2) installs the
# package in editable mode + dev deps, (3) verifies the boot
# smoke (`_make_server()` returns a Server instance).
#
# Re-run idempotently after a `git pull` to refresh deps.

[CmdletBinding()]
param(
    [string]$RepoRoot = "D:\Ichor"
)

$ErrorActionPreference = "Stop"

$ProjectDir = Join-Path $RepoRoot "apps\ichor-mcp"
$VenvDir = Join-Path $ProjectDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "[setup-ichor-mcp] project: $ProjectDir"

if (-not (Test-Path $VenvDir)) {
    Write-Host "[setup-ichor-mcp] creating venv (Python 3.12)..."
    & uv venv $VenvDir --python 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed" }
}

Write-Host "[setup-ichor-mcp] installing package + deps..."
& uv pip install -e $ProjectDir --python $PythonExe
if ($LASTEXITCODE -ne 0) { throw "uv pip install -e failed" }

& uv pip install "pytest>=8.3.0" "pytest-asyncio>=0.25.0" "respx>=0.21.0" --python $PythonExe
if ($LASTEXITCODE -ne 0) { throw "uv pip install dev deps failed" }

Write-Host "[setup-ichor-mcp] running boot smoke..."
& $PythonExe -c "from ichor_mcp.server import _make_server, _build_tools; s = _make_server(); print('server:', s.name); print('tools:', [t.name for t in _build_tools()])"
if ($LASTEXITCODE -ne 0) { throw "boot smoke failed" }

Write-Host "[setup-ichor-mcp] OK. Next: set ICHOR_MCP_API_SERVICE_TOKEN, then"
Write-Host "    claude -p --mcp-config $ProjectDir\ichor.mcp.json --strict-mcp-config --allowedTools mcp__ichor__query_db mcp__ichor__calc 'list 3 latest session_card_audit rows'"
