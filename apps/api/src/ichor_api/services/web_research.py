"""Live web research (W103, ADR-084) — self-hosted SearXNG meta-search.

Read-only async service that queries a self-hosted SearXNG instance
(`http://127.0.0.1:8081` loopback, ratified ADR-084 over metered
Perplexity) and returns clean, deduped, **ADR-017-safe** snapshots
suitable for injection into the LLM data_pool (`_section_web_research`).

ADR-084 design points honoured here :
  - Self-hosted SearXNG JSON API (`?format=json`) — no paid LLM, no
    Anthropic SDK (Voie D pure by construction : SearXNG is search, not
    inference).
  - 24h per-query cache (`_CACHE_TTL_SEC = 86400`) to avoid hammering
    upstream engines + getting rate-limited.
  - Optional Serper.dev fallback ONLY when `ICHOR_API_SERPER_API_KEY`
    is set (it is NOT today) — skipped silently otherwise.
  - NOT exposed to the 4-pass briefings as a tool ; this is a read-only
    section builder. The audit trail stays intact (we stamp the source).

ADR-017 boundary (the #1 correctness requirement) : web snippets are
arbitrary text and WILL contain "buy" / "sell" / "target" / "stop loss"
(analyst headlines). Each title + snippet is run through the canonical
`services.adr017_filter` BEFORE being returned. **Policy = DROP** : a
result whose title OR snippet trips the filter is dropped entirely
(never neutralized/redacted). Rationale : a research snippet that reads
like a trade call must NEVER reach the LLM prompt, and dropping is
unambiguous + auditable (false-positive drops are cheap — there are
always more search results ; a single smuggled signal is not).

Fail-open : any SearXNG error / timeout / non-200 returns `[]` and logs
a structured warning — NEVER raises. Web research must never break card
generation (mirrors `collectors/fred.py:fetch_latest` graceful
degradation + the reconciler's broad-catch pattern).

Voie D : `httpx.AsyncClient` only. No `anthropic` import. No LLM call.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import structlog

from ..config import get_settings
from .adr017_filter import is_adr017_clean

log = structlog.get_logger(__name__)

# SearXNG JSON-API timeout (seconds). Meta-search fans out to multiple
# upstream engines so it is slower than a single FRED call ; 8s gives
# margin without blocking card generation if the instance is wedged.
_HTTP_TIMEOUT_SECONDS = 8.0

# Per-query result cache TTL — ADR-084 = 24h. Avoids re-hitting the
# upstream engines (which rate-limit) for repeated identical queries
# across the 4 daily session windows.
_CACHE_TTL_SEC = 86400

# Default number of clean results returned per query.
_DEFAULT_LIMIT = 6

# Hard ceiling on results requested from SearXNG before dedup/sanitize,
# so a single noisy query can't balloon the prompt.
_MAX_FETCH = 30

# Near-duplicate title detection : two titles whose normalized forms
# share this Jaccard token overlap (or are equal) are treated as
# duplicates ; the first-seen (most relevant, SearXNG ranks by score)
# is kept.
_TITLE_DUP_JACCARD = 0.85

_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class WebResultSnapshot:
    """One clean, ADR-017-safe web search result.

    Frozen by design (mirrors `StirPoint` / `ReconcilerResult` house
    style) — these flow into the data_pool section and must not mutate.
    """

    title: str
    url: str
    snippet: str
    engine: str
    published_at: str | None
    source_domain: str


def _source_domain(url: str) -> str:
    """Bare registrable-ish domain for a URL (strip scheme + leading www).

    Best-effort, pure — used for display + dedup grouping. Returns "" on
    an unparseable URL rather than raising.
    """
    try:
        host = urlparse(url).netloc.lower()
    except (ValueError, TypeError):
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _normalize_title(title: str) -> str:
    """Lowercased, whitespace-collapsed title for near-dup comparison."""
    return _WS_RE.sub(" ", title.strip().lower())


def _titles_near_duplicate(a: str, b: str) -> bool:
    """True iff two normalized titles are equal or share ≥ Jaccard overlap.

    Pure token-set Jaccard over whitespace-split words. Cheap and
    sufficient for collapsing "EUR/USD slips as ECB holds" vs
    "EUR/USD slips after ECB holds rates" style near-dupes that the same
    story produces across syndicating outlets.
    """
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return union > 0 and (inter / union) >= _TITLE_DUP_JACCARD


def _is_clean(title: str, snippet: str) -> bool:
    """ADR-017 DROP policy : both title AND snippet must be clean.

    Any forbidden trade-signal token in EITHER field disqualifies the
    whole result (DROP, not neutralize) per the module docstring.
    """
    return is_adr017_clean(title) and is_adr017_clean(snippet)


def _parse_searxng_results(payload: dict) -> list[dict]:
    """Extract the `results` list from a SearXNG JSON payload.

    Defensive : returns [] if the shape is unexpected (fail-open). The
    SearXNG JSON API returns `{"results": [{title, url, content, engine,
    publishedDate, ...}], ...}`.
    """
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


def _dedupe_and_sanitize(raw: list[dict], *, limit: int) -> list[WebResultSnapshot]:
    """Dedup (URL + near-dup title) + ADR-017 DROP + cap at `limit`.

    Pure. Iterates in SearXNG rank order (most relevant first), so the
    first-seen of a duplicate cluster — the higher-ranked result — wins.
    """
    seen_urls: set[str] = set()
    kept: list[WebResultSnapshot] = []
    for r in raw:
        url = (r.get("url") or "").strip()
        title = _WS_RE.sub(" ", (r.get("title") or "").strip())
        snippet = _WS_RE.sub(" ", (r.get("content") or "").strip())
        if not url or not title:
            continue
        # Exact-URL dedup.
        if url in seen_urls:
            continue
        # ADR-017 DROP (the #1 correctness requirement).
        if not _is_clean(title, snippet):
            log.info("web_research.dropped_adr017", url=url, title=title[:80])
            continue
        # Near-duplicate title dedup against already-kept (informative)
        # results.
        if any(_titles_near_duplicate(title, k.title) for k in kept):
            continue
        seen_urls.add(url)
        published = r.get("publishedDate")
        kept.append(
            WebResultSnapshot(
                title=title,
                url=url,
                snippet=snippet,
                engine=str(r.get("engine") or "searxng"),
                published_at=str(published) if published else None,
                source_domain=_source_domain(url),
            )
        )
        if len(kept) >= limit:
            break
    return kept


# ── In-process TTL cache ────────────────────────────────────────────
#
# Module-level dict keyed by the normalized query string. Each value is
# `(fetched_at_epoch, results_tuple)`. The 4-pass orchestrator runs in a
# single process so an in-process cache is sufficient (per the W103
# brief — no clean shared redis helper exists for this read path). The
# cache stores the ALREADY-sanitized snapshots so a cache hit never
# re-runs the ADR-017 filter (correctness is locked at insert time).
_CACHE: dict[str, tuple[float, tuple[WebResultSnapshot, ...]]] = {}


def _cache_key(query: str, limit: int, max_age_days: int | None) -> str:
    """Normalized cache key — query is case/whitespace-insensitive."""
    norm = _WS_RE.sub(" ", query.strip().lower())
    return f"{norm}|{limit}|{max_age_days}"


def _cache_get(key: str, *, now_epoch: float) -> list[WebResultSnapshot] | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    fetched_at, results = entry
    if (now_epoch - fetched_at) > _CACHE_TTL_SEC:
        # Expired — drop it so the dict doesn't grow unbounded.
        _CACHE.pop(key, None)
        return None
    return list(results)


def _cache_put(key: str, results: list[WebResultSnapshot], *, now_epoch: float) -> None:
    _CACHE[key] = (now_epoch, tuple(results))


def clear_web_research_cache() -> None:
    """Test/ops helper — flush the in-process query cache."""
    _CACHE.clear()


async def _query_searxng(
    query: str,
    *,
    base_url: str,
    client: httpx.AsyncClient,
) -> list[dict]:
    """Single SearXNG JSON-API call → raw results list (fail-open → [])."""
    try:
        r = await client.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return _parse_searxng_results(r.json())
    except Exception as exc:  # noqa: BLE001 — graceful degradation (never raise)
        log.warning("web_research.searxng_failed", query=query, error=str(exc))
        return []


async def fetch_web_research(
    query: str,
    *,
    limit: int = _DEFAULT_LIMIT,
    max_age_days: int | None = None,
) -> list[WebResultSnapshot]:
    """Query SearXNG → clean, deduped, ADR-017-safe `WebResultSnapshot`s.

    Args :
        query : free-text search query (e.g. "EUR USD ECB Fed today").
        limit : max clean results to return (default 6 ; capped at
            `_MAX_FETCH` candidates fetched before dedup/sanitize).
        max_age_days : reserved freshness hint carried into the cache key
            (SearXNG `time_range` is engine-dependent and unreliable, so
            we don't filter on it server-side ; the param differentiates
            cache entries and is available for a future client-side
            published-date filter). None = no constraint.

    Returns :
        A list of `WebResultSnapshot` (possibly empty). Never raises —
        any upstream failure logs a structured warning and returns [].
        ADR-017 DROP policy applied : results whose title/snippet trip
        the trade-signal filter are excluded.

    Caching : results are cached per normalized (query, limit,
    max_age_days) for `_CACHE_TTL_SEC` (24h, ADR-084). A cache hit does
    NOT re-hit httpx and does NOT re-run the ADR-017 filter (snapshots
    are sanitized at insert time).
    """
    if not query or not query.strip():
        return []

    limit = max(1, min(int(limit), _MAX_FETCH))
    key = _cache_key(query, limit, max_age_days)
    now_epoch = datetime.now(UTC).timestamp()

    cached = _cache_get(key, now_epoch=now_epoch)
    if cached is not None:
        return cached

    settings = get_settings()
    base_url = settings.web_research_searxng_url

    async with httpx.AsyncClient() as client:
        raw = await _query_searxng(query, base_url=base_url, client=client)

        # Optional Serper.dev fallback — ONLY when the key is set AND
        # SearXNG returned nothing. Guarded + minimal (the key is unset
        # today, so this path is dormant by construction).
        if not raw and os.environ.get("ICHOR_API_SERPER_API_KEY"):
            raw = await _query_serper_fallback(query, client=client)

    snapshots = _dedupe_and_sanitize(raw, limit=limit)
    _cache_put(key, snapshots, now_epoch=now_epoch)
    return snapshots


async def _query_serper_fallback(
    query: str,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    """Serper.dev fallback → SearXNG-shaped raw results (fail-open → []).

    Only invoked when `ICHOR_API_SERPER_API_KEY` is present in the
    environment (NOT today). Minimal by design — maps Serper's `organic`
    results into the {title, url, content, engine, publishedDate} shape
    `_dedupe_and_sanitize` expects, so the downstream pipeline (dedup +
    ADR-017 DROP) is identical regardless of provider.
    """
    api_key = os.environ.get("ICHOR_API_SERPER_API_KEY")
    if not api_key:
        return []
    try:
        r = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        organic = r.json().get("organic", [])
        return [
            {
                "title": o.get("title", ""),
                "url": o.get("link", ""),
                "content": o.get("snippet", ""),
                "engine": "serper",
                "publishedDate": o.get("date"),
            }
            for o in organic
            if isinstance(o, dict)
        ]
    except Exception as exc:  # noqa: BLE001 — graceful degradation
        log.warning("web_research.serper_failed", query=query, error=str(exc))
        return []


__all__ = [
    "WebResultSnapshot",
    "clear_web_research_cache",
    "fetch_web_research",
]
