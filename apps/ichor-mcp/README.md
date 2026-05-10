# apps/ichor-mcp

Local Win11 stdio MCP server exposing the two Capability-5 client
tools (`query_db`, `calc`) to Claude CLI. ADR-071 STEP-3 / ADR-077.

## Architecture

```
[Claude CLI Win11]
   ↓ stdio MCP (jsonrpc)
[apps/ichor-mcp (this package)]
   ↓ httpx HTTPS
[apps/api Hetzner /v1/tools/*]
   ↓ asyncpg + ToolCallAudit insert
[Postgres (immutable trigger from migration 0038)]
```

The server does NO trade logic and holds NO DB credentials. Every
invocation forwards to apps/api which runs the tool body and writes
the immutable `tool_call_audit` row in a dedicated session.

## Run locally (smoke handshake)

```powershell
# 1. Create the venv (one-off)
uv venv D:\Ichor\apps\ichor-mcp\.venv --python 3.12
D:\Ichor\apps\ichor-mcp\.venv\Scripts\python.exe -m pip install -e D:\Ichor\apps\ichor-mcp

# 2. Set the service token (must match apps/api ICHOR_API_TOOL_SERVICE_TOKEN)
$env:ICHOR_MCP_API_SERVICE_TOKEN = "<paste-token-here>"
$env:ICHOR_MCP_API_BASE_URL = "https://api.fxmilyapp.com"

# 3. Wire into Claude CLI for one shot
claude -p `
    --mcp-config D:\Ichor\apps\ichor-mcp\ichor.mcp.json `
    --strict-mcp-config `
    --allowedTools mcp__ichor__query_db mcp__ichor__calc `
    "List the 3 most recent session_card_audit rows for EUR_USD."
```

## Tools

| Tool                   | Operation                                                                                                            | Input                                                              |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `mcp__ichor__query_db` | Read-only SQL across 6 allowlist tables (sqlglot AST whitelist, hard-cap 1000 rows)                                  | `sql`, `max_rows?`, `agent_kind`, `pass_index`, `session_card_id?` |
| `mcp__ichor__calc`     | 9 deterministic ops: zscore, rolling_mean/std, pct_change, log_returns, correlation, percentile, ewma, annualize_vol | `operation`, `values`, `params`, audit fields                      |

## Tests

```powershell
D:\Ichor\apps\ichor-mcp\.venv\Scripts\python.exe -m pytest D:\Ichor\apps\ichor-mcp\tests -q
```

Unit tests stub the apps/api edge with `respx` — no network, no
Hetzner connection required.

## Env vars

| Var                                 | Effect                                                            |
| ----------------------------------- | ----------------------------------------------------------------- |
| `ICHOR_MCP_API_BASE_URL`            | apps/api root, default `https://api.fxmilyapp.com`                |
| `ICHOR_MCP_API_SERVICE_TOKEN`       | Sent as `X-Ichor-Tool-Token`. Must match Hetzner side.            |
| `ICHOR_MCP_CF_ACCESS_CLIENT_ID`     | Cloudflare Access service-token id (PRE-1, optional today).       |
| `ICHOR_MCP_CF_ACCESS_CLIENT_SECRET` | Pair with the id above.                                           |
| `ICHOR_MCP_REQUEST_TIMEOUT_SEC`     | Hard timeout per round-trip (default 30 s).                       |
| `ICHOR_MCP_LOG_LEVEL`               | DEBUG/INFO/WARNING/ERROR (logs go to stderr to keep stdio clean). |

Logs are emitted to **stderr** so the MCP stdio JSON-RPC stream on
stdout stays parseable.
