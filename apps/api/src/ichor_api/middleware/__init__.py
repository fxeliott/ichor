"""Custom Starlette middlewares for the Ichor API.

Currently :
  - `ai_watermark.AIWatermarkMiddleware` — EU AI Act Article 50(2)
    machine-readable watermark on LLM-derived responses.

Other middlewares historically live under `services/` for legacy
reasons (`audit_log`, `rate_limiter`, `csp_middleware`). New ones
land here.
"""

from .ai_watermark import (
    DEFAULT_DISCLOSURE_URL,
    DEFAULT_PROVIDER_TAG,
    DEFAULT_WATERMARKED_PREFIXES,
    AIWatermarkMiddleware,
)

__all__ = [
    "DEFAULT_DISCLOSURE_URL",
    "DEFAULT_PROVIDER_TAG",
    "DEFAULT_WATERMARKED_PREFIXES",
    "AIWatermarkMiddleware",
]
