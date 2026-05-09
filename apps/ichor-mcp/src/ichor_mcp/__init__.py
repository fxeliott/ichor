"""Ichor MCP — local Win11 stdio MCP server for Capability 5 client tools.

Forwards `query_db` and `calc` invocations to the Hetzner FastAPI
(`/v1/tools/*`) via HTTPS. The server is launched per-session by the
Claude CLI when it sees the `--mcp-config` flag pointing at this
package's `ichor.mcp.json`.
"""

__version__ = "0.0.0"
