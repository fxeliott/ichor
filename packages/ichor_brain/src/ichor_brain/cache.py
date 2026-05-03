"""Prompt-cache key derivation.

Anthropic prompt caching is keyed on a deterministic SHA-256 prefix of
the system prompt up to a `cache_control` breakpoint. We track two
breakpoints :

  - **framework cache** : the asset-specific framework template + the
    régime-detection rubric. Stable for ~1h (recompute when any
    template file mtime changes).
  - **asset-data cache** : the consolidated 24h-window data pool
    (FRED + GDELT + COT + Polymarket + ...). Stable for ~5min.

The cache key is purely diagnostic at the brain layer — Anthropic
applies caching server-side based on the prompt text. We compute the
hash so we can :
  1. log cache hit/miss expectations,
  2. dedupe repeated runs in `session_card_audit.source_pool_hash`.
"""

from __future__ import annotations

import hashlib


_FRAMEWORK_TTL_SEC = 3600
_ASSET_DATA_TTL_SEC = 300


def framework_cache_ttl() -> int:
    """1h, exposed for tests + observability."""
    return _FRAMEWORK_TTL_SEC


def asset_data_cache_ttl() -> int:
    """5min, exposed for tests + observability."""
    return _ASSET_DATA_TTL_SEC


def hash_pool(*chunks: str) -> str:
    """Stable SHA-256 hex over an ordered list of text chunks.

    Chunks are joined by a NUL separator so concatenation ambiguity
    can't collide two distinct pools.
    """
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()
