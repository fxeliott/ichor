"""httpx-backed client for the Hetzner /v1/tools/* surface.

Single class with two thin methods so the MCP tool handlers stay
decorator-flat. The client is constructed once during the MCP server
lifespan and shared across tool calls; httpx pools the underlying
TCP/TLS connections.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from .config import Settings

log = structlog.get_logger(__name__)


class ToolApiError(Exception):
    """Raised when the apps/api side returns a non-2xx response.

    `status_code` mirrors the upstream status (400 = validation
    rejection, 401 = auth, 500 = backend execution failure). `detail`
    is the upstream error message verbatim — propagated to the model
    via the MCP `TextContent` so it can self-correct."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class ToolApiClient:
    """Thin wrapper around an httpx.AsyncClient pinned to apps/api."""

    def __init__(self, settings: Settings) -> None:
        headers: dict[str, str] = {"User-Agent": "ichor-mcp/0.0.0"}
        if settings.api_service_token.strip():
            headers["X-Ichor-Tool-Token"] = settings.api_service_token.strip()
        if settings.cf_access_client_id.strip() and settings.cf_access_client_secret.strip():
            headers["CF-Access-Client-Id"] = settings.cf_access_client_id.strip()
            headers["CF-Access-Client-Secret"] = settings.cf_access_client_secret.strip()

        self._client = httpx.AsyncClient(
            base_url=settings.api_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                settings.request_timeout_sec,
                connect=settings.connect_timeout_sec,
            ),
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(path, json=body)
        except httpx.HTTPError as e:
            raise ToolApiError(599, f"network error: {type(e).__name__}: {e}") from e

        if 200 <= resp.status_code < 300:
            return resp.json()

        # Try to surface FastAPI's `{"detail": "..."}` shape; fall back
        # to the raw text body when JSON parsing fails (5xx HTML pages).
        detail: str
        try:
            payload = resp.json()
            detail = str(payload.get("detail") or payload)
        except Exception:
            detail = resp.text[:512] or f"HTTP {resp.status_code}"
        raise ToolApiError(resp.status_code, detail)

    async def query_db(
        self,
        *,
        sql: str,
        max_rows: int | None,
        agent_kind: str,
        pass_index: int,
        session_card_id: str | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "sql": sql,
            "agent_kind": agent_kind,
            "pass_index": pass_index,
        }
        if max_rows is not None:
            body["max_rows"] = max_rows
        if session_card_id is not None:
            body["session_card_id"] = session_card_id
        return await self._post("/v1/tools/query_db", body)

    async def calc(
        self,
        *,
        operation: str,
        values: list[float],
        params: dict[str, Any] | None,
        agent_kind: str,
        pass_index: int,
        session_card_id: str | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "operation": operation,
            "values": values,
            "params": params or {},
            "agent_kind": agent_kind,
            "pass_index": pass_index,
        }
        if session_card_id is not None:
            body["session_card_id"] = session_card_id
        return await self._post("/v1/tools/calc", body)
