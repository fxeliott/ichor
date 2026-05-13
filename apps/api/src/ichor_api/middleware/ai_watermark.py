"""EU AI Act Article 50(4) DEPLOYER machine-readable watermark middleware.

Adds `X-Ichor-AI-*` response headers on routes whose body contains
LLM-derived content (briefings, sessions, scenarios, post-mortems,
today). Pure-data routes (`/v1/market`, `/v1/fred`, etc.) are NOT
watermarked because they only return collector outputs.

**ICHOR ROLE under EU AI Act** (round-35 correction) : Ichor is an
Article 50(4) **DEPLOYER** of Anthropic's GPAI Claude family — NOT
an Article 50(2) GPAI provider. The heavier signed-C2PA + PKI +
detector-API obligations from the 2nd-draft Code of Practice
(published early March 2026, consultation closed 30 March 2026, final
Code expected early June 2026) bind Anthropic upstream, not Ichor.

This middleware's lighter deployer-tier transparency surface
(4 `X-Ichor-AI-*` HTTP headers) satisfies §50(4) "disclose that the
output is AI-generated" plus the human-readable §50(5) page
(`/legal/ai-disclosure`).

The header set provides :

  - explicit AI-generated flag (X-Ichor-AI-Generated),
  - identification of the upstream provider / model family (X-Ichor-AI-Provider),
  - timestamp of response (X-Ichor-AI-Generated-At — generation
    timestamp not separately recorded),
  - link to the human-readable disclosure page (X-Ichor-AI-Disclosure).

Enforcement date : 2 August 2026 (EU AI Act Article 113 transitional
clause). When Anthropic emits C2PA-signed outputs (driven by §50(2)
GPAI provider obligations under the 2nd-draft Code of Practice),
Ichor inherits the signed metadata automatically — no first-party
upgrade required on this middleware.

The middleware is content-agnostic : it does not parse the body. It
matches by route path-prefix, configurable via
`Settings.ai_watermarked_route_prefixes`. Hot path allocation-free.

See :
  - ADR-029 (EU AI Act §50 + AMF DOC-2008-23 disclosure footer)
  - ADR-079 (this middleware's design rationale, original §50(2)
    framing — superseded round-35 by §50(4) deployer correction)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Default prefixes — kept in sync with ADR-029 surface inventory.
# Pure-data routes (market / fred / calendar / sources / etc.) are
# deliberately excluded : they return collector output, not LLM text.
DEFAULT_WATERMARKED_PREFIXES: tuple[str, ...] = (
    "/v1/briefings",
    "/v1/sessions",
    "/v1/post-mortems",
    "/v1/today",
    "/v1/scenarios",
)

# Disclosure URL surfaced via `X-Ichor-AI-Disclosure`. Must resolve
# to a human-readable page (cf ADR-029 §"Methodology page only" alt).
DEFAULT_DISCLOSURE_URL = "https://app-ichor.pages.dev/legal/ai-disclosure"

# Provider tag — bumped in lockstep with model upgrades. ADR-029
# §Cons notes that model changes already trigger an ADR ; this tag
# is updated in the same wave.
DEFAULT_PROVIDER_TAG = "anthropic-claude-opus-4-7"


class AIWatermarkMiddleware(BaseHTTPMiddleware):
    """Tag LLM-derived responses with AI Act §50.2 headers.

    Args:
        app: The downstream ASGI app.
        watermarked_prefixes: Iterable of path prefixes to tag.
            Defaults to `DEFAULT_WATERMARKED_PREFIXES`.
        provider_tag: Value for `X-Ichor-AI-Provider`. Defaults to
            the current production model identifier.
        disclosure_url: Value for `X-Ichor-AI-Disclosure`.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        watermarked_prefixes: Iterable[str] | None = None,
        provider_tag: str = DEFAULT_PROVIDER_TAG,
        disclosure_url: str = DEFAULT_DISCLOSURE_URL,
    ) -> None:
        super().__init__(app)
        prefixes = (
            tuple(watermarked_prefixes) if watermarked_prefixes else DEFAULT_WATERMARKED_PREFIXES
        )
        # Tuple lookup is O(n) but n is tiny (5-ish) ; avoids a frozenset
        # allocation per request.
        self._prefixes: tuple[str, ...] = prefixes
        self._provider_tag = provider_tag
        self._disclosure_url = disclosure_url

    def _is_watermarked(self, path: str) -> bool:
        return any(path.startswith(p) for p in self._prefixes)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if not self._is_watermarked(request.url.path):
            return response
        # RFC3339 / ISO8601 with explicit UTC offset, second precision.
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        response.headers["X-Ichor-AI-Generated"] = "true"
        response.headers["X-Ichor-AI-Provider"] = self._provider_tag
        response.headers["X-Ichor-AI-Generated-At"] = now
        response.headers["X-Ichor-AI-Disclosure"] = self._disclosure_url
        return response


__all__ = [
    "DEFAULT_DISCLOSURE_URL",
    "DEFAULT_PROVIDER_TAG",
    "DEFAULT_WATERMARKED_PREFIXES",
    "AIWatermarkMiddleware",
]
