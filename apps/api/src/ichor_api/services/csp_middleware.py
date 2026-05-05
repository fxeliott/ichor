"""Content-Security-Policy middleware — strict baseline, nonce-aware.

Per OWASP recommendations + 2026 FastAPI hardening guides. Adds a
strict CSP header to every response :

  default-src 'none'
  base-uri    'none'
  frame-ancestors 'none'
  form-action 'self'
  script-src  'self' 'nonce-{N}' 'strict-dynamic'
  style-src   'self' 'nonce-{N}'
  img-src     'self' data:
  connect-src 'self'
  font-src    'self' data:

The per-request nonce is generated via secrets.token_urlsafe(32) and
stored in `request.state.csp_nonce` so HTML-rendering routes
(only the dashboard tunnel — the API itself returns JSON) can inject
it into <script nonce="...">.

For JSON-only responses (the bulk of /v1/*) the nonce is unused but
the header is still emitted defensively in case of error pages /
Swagger UI.

We also set adjacent baseline security headers per OWASP cheat-sheet:
  X-Content-Type-Options: nosniff
  Strict-Transport-Security (HSTS)
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: minimal (no camera/mic/geolocation)
  X-Frame-Options: DENY (legacy browsers)

References:
  - https://github.com/tmotagam/Secweb (Secweb 1.30.10, 2026)
  - https://docs.djangoproject.com/en/6.0/ref/csp/
  - https://owasp.org/www-project-secure-headers/
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

# Static security headers — precomputed once at module load to keep
# the per-request hot path tight.
_BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (
        b"permissions-policy",
        b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    ),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
)

# Routes that serve HTML (Swagger / ReDoc) need the nonce inlined.
# /v1/* + /healthz return JSON ; the nonce header is harmless there.
_HTML_PATH_PREFIXES = ("/docs", "/redoc")


def _build_csp(nonce: str, *, html: bool) -> bytes:
    """Render the CSP directive list. HTML-page routes get a wider
    img-src to allow Swagger's CDN icons ; JSON routes lock down."""
    parts = [
        "default-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'",
        f"style-src 'self' 'nonce-{nonce}'",
        "connect-src 'self'",
        "font-src 'self' data:",
    ]
    if html:
        # Swagger/ReDoc inline some images + cdn.jsdelivr.net assets.
        parts.append("img-src 'self' data: https://cdn.jsdelivr.net")
    else:
        parts.append("img-src 'self' data:")
    return "; ".join(parts).encode("ascii")


class CSPSecurityHeadersMiddleware:
    """ASGI middleware. Plug via:
        app.add_middleware(CSPSecurityHeadersMiddleware)
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "") or ""
        is_html = any(path.startswith(p) for p in _HTML_PATH_PREFIXES)

        # Generate nonce per request. Cheap : ~32 bytes random, no syscall.
        nonce = secrets.token_urlsafe(32)
        # Stash on scope state so endpoint code can read it (FastAPI
        # exposes scope['state'] via request.state).
        if "state" not in scope or scope["state"] is None:
            scope["state"] = {}
        scope["state"]["csp_nonce"] = nonce

        csp_header = _build_csp(nonce, html=is_html)

        async def _send_with_security_headers(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                new_message = dict(message)
                headers = list(message.get("headers", []))
                # Drop any prior CSP that downstream code may have set ;
                # we are the authoritative source.
                headers = [(k, v) for (k, v) in headers if k.lower() != b"content-security-policy"]
                headers.extend(_BASE_HEADERS)
                headers.append((b"content-security-policy", csp_header))
                new_message["headers"] = headers
                await send(new_message)
                return
            await send(message)

        await self.app(scope, receive, _send_with_security_headers)
