"""`.well-known/ai-content` endpoint — machine-readable inventory of
LLM-derived URL prefixes (W89, ADR-080).

Hint from the EU Code of Practice draft (December 2025) on AI-generated
content marking : a `.well-known` discovery endpoint that lists which
URL families on a host are AI-generated. Crawlers, audit tools, and
downstream API consumers can fetch this once and know the watermark
boundary without parsing every response header.

The endpoint is :
  - GET-only
  - public (no auth, no CF Access)
  - cache-friendly (5 min TTL, content rarely changes)
  - JSON shape stable across releases (versioned via `schema_version`)

The shape is content-addressable to ADR-079's middleware config :
the `watermarked_prefixes` field mirrors `Settings.ai_watermarked_route_prefixes`,
so the discovery endpoint stays in lockstep with the actual middleware
behaviour by construction (single source of truth).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response

from ..config import Settings, get_settings

router = APIRouter(prefix="/.well-known", tags=["well-known"])


@router.get(
    "/ai-content",
    summary="EU AI Act §50.2 watermark inventory (machine-readable)",
    description=(
        "Lists URL prefixes on this host whose responses are tagged with the "
        "`X-Ichor-AI-*` watermark headers. Fetched once by audit tools / "
        "crawlers / downstream API integrations. Hint from the EU Code of "
        "Practice draft Dec-2025 on AI-generated content marking."
    ),
    response_description="Inventory document (JSON).",
    include_in_schema=True,
)
async def get_ai_content_inventory(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return the watermark inventory as a stable JSON document.

    Schema version 1 :
      {
        "schema_version": 1,
        "spec": "EU AI Act Article 50(2)",
        "host_role": "deployer",
        "provider": "anthropic-claude-opus-4-7",
        "disclosure_url": "https://app-ichor.pages.dev/legal/ai-disclosure",
        "watermarked_prefixes": ["/v1/briefings", ...],
        "watermark_headers": ["X-Ichor-AI-Generated", ...],
        "generated_at": "2026-05-09T23:00:00Z"
      }
    """
    # 5-minute browser/CDN cache — inventory changes rarely (only on
    # ADR-079 prefix list edits or model upgrade).
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "schema_version": 1,
        "spec": "EU AI Act Article 50(2)",
        "host_role": "deployer",
        "provider": settings.ai_provider_tag,
        "disclosure_url": settings.ai_disclosure_url,
        "watermarked_prefixes": list(settings.ai_watermarked_route_prefixes),
        "watermark_headers": [
            "X-Ichor-AI-Generated",
            "X-Ichor-AI-Provider",
            "X-Ichor-AI-Generated-At",
            "X-Ichor-AI-Disclosure",
        ],
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


__all__ = ["router"]
