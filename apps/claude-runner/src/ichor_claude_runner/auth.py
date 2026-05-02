"""Cloudflare Access JWT verification — the only thing standing between Hetzner
and the local Claude Code subscription.

Every request from Hetzner carries `Cf-Access-Jwt-Assertion` (signed by
Cloudflare) — we verify the signature against Cloudflare's published JWKS,
then check the audience tag matches our app.

If `require_cf_access=False` (dev mode), this is a no-op.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import jwt
from jose.exceptions import JWTError

from .config import Settings, get_settings


# JWKS cache: {(team_domain, fetched_at): keys}
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_TTL_SEC = 3600  # refresh hourly


async def _fetch_jwks(team_domain: str) -> dict[str, Any]:
    """Cloudflare publishes its rotating signing keys at a stable URL."""
    cached = _jwks_cache.get(team_domain)
    if cached and (time.time() - cached[0]) < _JWKS_TTL_SEC:
        return cached[1]

    url = f"https://{team_domain}.cloudflareaccess.com/cdn-cgi/access/certs"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        keys = r.json()

    _jwks_cache[team_domain] = (time.time(), keys)
    return keys


async def verify_cf_access(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify the request's CF Access JWT.

    Returns the authenticated identity (email or service-token name) on
    success. Raises 401 on any failure.
    """
    if not settings.require_cf_access:
        # Dev mode — skip entirely
        return "dev-mode-no-auth"

    if not settings.cf_access_team_domain or not settings.cf_access_aud_tag:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudflare Access not configured — server misconfigured",
        )

    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Cf-Access-Jwt-Assertion header",
        )

    try:
        jwks = await _fetch_jwks(settings.cf_access_team_domain)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch Cloudflare JWKS: {e}",
        ) from e

    try:
        header = jwt.get_unverified_header(token)
        kid = header["kid"]
        key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"JWT key id '{kid}' not in Cloudflare JWKS",
            )

        claims = jwt.decode(
            token,
            key,
            algorithms=[header.get("alg", "RS256")],
            audience=settings.cf_access_aud_tag,
            issuer=f"https://{settings.cf_access_team_domain}.cloudflareaccess.com",
            options={"require_exp": True, "require_iat": True},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid CF Access JWT: {e}",
        ) from e

    # CF Access service tokens use `common_name`; user tokens use `email`.
    return claims.get("email") or claims.get("common_name") or "anonymous"
