# ADR-084 — SearXNG self-hosted on Hetzner replaces Perplexity for Couche-2 web research

**Date** : 2026-05-11
**Status** : Accepted
**Wave** : W103 (sequel of ADR-083 D5, formally ratified)

## Context

ADR-083 D5 already named SearXNG as the chosen web-research backend for
Couche-2 agents (cb_nlp, news_nlp, sentiment, positioning, macro) and
the upcoming Pass 6 scenario decomposer. This ADR ratifies the choice
with the full template and documents the architecture decisions that
were left implicit.

The 2026-05-11 conversation surfaced an explicit user concern :

> _"je me disais potentiellement prendre l'ia perplexity un truc comme
> ça pour les recherches pour ichor quand il devra en faire à chaque
> fois énormément pour toute la data tout en plus des api"_

Three candidates were evaluated against the Voie D constraint
(ADR-009 — zero Anthropic SDK / zero metered API consumption) and the
"massive recurrent search" volume requirement (one Couche-2 batch =
5 agents × ~3 queries/agent × 4 windows/day × 6 assets ≈ 360 queries
per trading day, with episodic geo-event spikes to 1500/day).

| Candidate                     | Annual cost                               | Voie D                                                                                       | Volume capacity                               | Latency             | Reliability 2026                                                                  |
| ----------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| **SearXNG self-host Hetzner** | $0 marginal (CPX21 already paid)          | Yes                                                                                          | Unlimited (limited by upstream engine quotas) | 600-1500 ms typical | High (depends on 70+ upstreams ; one upstream failure does not break the request) |
| Serper.dev free tier          | $0 below 2 500 req/mo                     | Yes (no LLM, just search aggregation)                                                        | 2 500/mo = 8 % of need                        | 200-400 ms          | High but quota-bound                                                              |
| Brave Search API free tier    | $0 below 2 000 req/mo                     | Yes (no LLM)                                                                                 | 2 000/mo = 7 % of need                        | 300-500 ms          | High                                                                              |
| **Perplexity Pro**            | $240/yr ($20/mo)                          | Ambiguous — bundles LLM (Sonar) with search ; metered LLM consumption violates Voie D spirit | 200-500 search-with-summary/mo                | 2-4 s               | High                                                                              |
| Anthropic `web_search` tool   | Metered ($10/1000)                        | **Hard violation** of Voie D (server-tool billed separately from Max 20×)                    | unlimited but metered                         | 800 ms              | High                                                                              |
| Google Custom Search JSON API | $5 per 1 000 queries (after 100/day free) | Hard violation                                                                               | unlimited                                     | 400 ms              | Highest                                                                           |

**Decision : SearXNG self-host on Hetzner CPX21 (already provisioned)**.

## Decisions

### D1. Deployment shape

Run **SearXNG** in Docker on the existing `ichor-hetzner` VPS with the
following architecture :

```
Couche-2 agent / Pass 6 scenario decomposer
  → MCP tool call `mcp__ichor__web_search` (Cap5 pattern, ADR-077)
    → apps/api  POST /v1/tools/web_search    (NEW endpoint, audit-first)
      → asyncio.gather across {SearXNG primary, Serper.dev fallback}
        → SearXNG Docker container :8081 (loopback only, no public expose)
          → 12 enabled upstream engines (DuckDuckGo, Brave, Bing, Wikipedia, arXiv, Reddit, GitHub, Stack Exchange, GoogleScholar, NewsAPI Lite, GDELT Doc API, OpenAlex)
        → Redis cache (24 h TTL per query hash)
      → INSERT INTO tool_call_audit (ADR-029 immutable trigger)
```

### D2. Why Docker not native install

- Reproducibility : `searxng/searxng:latest` image is the upstream-blessed
  artifact, with the same `settings.yml` interface across versions.
- Isolation : SearXNG bundles dozens of Python deps that we do not want
  in the `ichor-api` virtualenv.
- Update cadence : `docker pull` + `docker compose up -d` = 30 s redeploy ;
  no `pip install` reproducibility risk.

### D3. Loopback bind (no public exposure)

`docker-compose.yml` binds SearXNG to `127.0.0.1:8081`. The `apps/api`
calls it via `http://127.0.0.1:8081/search?...&format=json`. Reasons :

- SearXNG has no built-in auth — public exposure invites scraping abuse
  that would burn upstream-engine quotas.
- Avoids needing a Cloudflare Tunnel route for it.
- Hetzner firewall already restricts inbound to 22/80/443 (UFW), but
  defence in depth.

### D4. Redis cache, 24 h TTL

Couche-2 agents tend to query identical strings within a single batch
(e.g. "FOMC March 2026 SEP dots", "ECB depo path 2026") and across
asset cards (the macro context repeats). Without cache, 6 cards × 5
agents = 30 redundant calls. With Redis `query_hash → result_json`,
24 h TTL, redundancy drops to one upstream call per unique query per
day. Reuses the existing `ichor-redis` (Redis 8) on the same VPS.

### D5. Rate-limit + circuit-breaker

`/v1/tools/web_search` enforces :

- Max 5 concurrent calls (semaphore) to keep upstream-engine pressure
  bounded.
- Max 200 calls per 5 min per service-token caller.
- Circuit-breaker : if 3 consecutive SearXNG calls fail (5xx, timeout)
  within 60 s, the next 30 s of calls bypass SearXNG and go straight
  to Serper.dev fallback (within its free quota).

### D6. Fallback : Serper.dev free tier

If SearXNG returns CAPTCHA from too many of its upstreams in a row, or
the container is down, fallback to `https://google.serper.dev/search`
with the free-tier API key. Quota 2 500/mo = enough to cover a SearXNG
outage of ~24 h before exhaustion. Tracked in `tool_call_audit.metadata`
with the field `backend = "serper" | "searxng"`.

### D7. MCP tool surface

The MCP tool `mcp__ichor__web_search` (added in `apps/ichor-mcp/`
following the W85 STEP-3 pattern, ADR-077) accepts :

```python
@dataclass
class WebSearchInput:
    query: str             # max 256 chars, sanitised
    category: Literal["news", "general", "science"]  # SearXNG category
    max_results: int = 8   # 1-20
    time_range: Literal["day", "week", "month", "year", None] = None
```

Returns :

```python
@dataclass
class WebSearchResult:
    backend: Literal["searxng", "serper"]
    results: list[WebSearchHit]
    cached: bool
    elapsed_ms: int

@dataclass
class WebSearchHit:
    title: str
    url: str
    snippet: str
    source_engine: str | None
    published_at: datetime | None
```

### D8. Allowlist for Cap5 tool wiring

Couche-1 (4-pass orchestrator) **does not** receive `web_search` in its
default tool config. Only **Couche-2 agents** + **Pass 6 scenario
decomposer** (W105) get it in their respective `allowed_tools` arrays.
Rationale : the 4-pass briefing operates on data_pool snapshots that
are already source-stamped and Critic-verifiable ; adding live web
search there breaks the audit trail (web result freshness is not
deterministic between two runs of the same card).

## Consequences

- **Cost** : $0 incremental. Voie D respected absolutely.
- **Risk** : SearXNG depends on upstream engine availability ; partial
  upstream failures degrade quality gracefully (other engines still
  return). Serper.dev free tier as 24 h safety net.
- **Audit trail** : every search recorded in `tool_call_audit` with the
  query, backend used, result-count, and cache-hit flag. MiFID-friendly.
- **Wave dependency** : W105 (Pass 6 scenario decomposer) depends on
  W103 (this ADR shipping). W104 (asset universe align) does not.
- **Operational dependency** : `RUNBOOK-019-searxng-down.md` (NEW) to
  be drafted in W103 to document fallback procedures.

## References

- ADR-009 Voie D
- ADR-077 Capability 5 MCP server wire
- ADR-083 D5 (initial SearXNG choice, ratified here)
- SearXNG upstream : https://docs.searxng.org/
- 2026-05-11 researcher subagent audit (in conversation transcript)
