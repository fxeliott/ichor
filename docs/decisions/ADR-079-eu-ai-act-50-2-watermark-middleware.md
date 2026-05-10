# ADR-079: EU AI Act §50.2 machine-readable watermark middleware

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes**: none
- **Related**: ADR-009 (Voie D — no Anthropic SDK consumption), ADR-017
  (Living Macro Entity boundary), ADR-026 (frontend WCAG 2.2 AA + Lighthouse),
  ADR-027 (Playwright golden paths + axe-core), ADR-029 (EU AI Act §50 +
  AMF DOC-2008-23 disclosure surface), ADR-077 (Capability 5 STEP-3 — MCP
  server wire), ADR-078 (Cap5 query_db excludes trader_notes)

## Context

EU AI Act Article 50(2) (Regulation (EU) 2024/1689) mandates :

> "Providers of AI systems […] generating synthetic audio, image, video
> or text content, shall ensure that the outputs of the AI system are
> marked in a machine-readable format and detectable as artificially
> generated or manipulated."

Enforcement date for general-purpose AI deployers and downstream users :
**2 August 2026** (Article 113 transitional clause). Today is 2026-05-09 :
**T-3 months ferme**.

ADR-029 already ratified the human-readable disclosure surface (sticky
top banner `AIDisclosureBanner` + `LegalFooter` mounted in the web2
root layout, plus `docs/legal/ai-disclosure.md` matrix of surfaces).
But ADR-029 did NOT ship the §50.2 _machine-readable_ leg — only the
§50.5 _clear-and-distinguishable_ leg.

This ADR closes that gap on the API surface : every Ichor API response
that contains LLM-derived content carries a stable, machine-parseable
watermark in the form of HTTP response headers. The web2 dashboard and
any future API consumer (CLI tools, third-party integrations) can rely
on these headers to know that the body was AI-generated, by which
provider, when, and where to point the user for the human disclosure.

## Decision

Implement `AIWatermarkMiddleware` in `apps/api/src/ichor_api/middleware/
ai_watermark.py` as a Starlette `BaseHTTPMiddleware`. Mount it in
`main.py` between `RateLimitMiddleware` (inside) and
`CSPSecurityHeadersMiddleware` (outside) — this position guarantees :

- 429 rate-limited responses still carry the watermark when their body
  is LLM-derived (defensive : rate-limited briefing responses still
  count as AI output).
- CSP cannot strip the custom `X-Ichor-AI-*` headers (CSP only constrains
  sub-resource and frame loading directives, not response header allow-
  lists ; but staying inside CSP keeps the layering crystal-clear).

### Headers emitted

For every response whose path matches `Settings.ai_watermarked_route_prefixes`
(default : `/v1/briefings`, `/v1/sessions`, `/v1/post-mortems`,
`/v1/today`, `/v1/scenarios`) :

| Header                    | Example value                                          | Spec mapping                                    |
| ------------------------- | ------------------------------------------------------ | ----------------------------------------------- |
| `X-Ichor-AI-Generated`    | `true`                                                 | EU AI Act §50.2 — explicit AI-generated flag    |
| `X-Ichor-AI-Provider`     | `anthropic-claude-opus-4-7`                            | EU CoP draft Dec-2025 — provider identification |
| `X-Ichor-AI-Generated-At` | `2026-05-09T19:55:00Z` (RFC3339 UTC, second precision) | EU CoP draft — generation timestamp             |
| `X-Ichor-AI-Disclosure`   | `https://app-ichor.pages.dev/legal/ai-disclosure`      | EU AI Act §50.5 — human-readable link           |

### Why path-prefix not body-parsing

The middleware is content-agnostic by design : it does not parse the
response body. Three reasons :

1. **Allocation cost** — parsing JSON in middleware adds a per-request
   allocation hit on the hot path. The 5-prefix tuple-startswith lookup
   is O(n) with n=5, allocation-free.
2. **False positives** — body-parsing risks tagging a route that _happens_
   to return JSON containing LLM-shaped strings (e.g. an alert that
   echoes a Claude rationale field). Path-prefix is deterministic.
3. **Ops simplicity** — adding a new route to the watermark surface is
   a config change (`ai_watermarked_route_prefixes`), not a code change.

### Why headers not body-injection

Some AI labelling proposals push C2PA / SynthID-style metadata
_inside_ the content (text watermarks, image C2PA manifests). For
Ichor's text-only API responses, header-based watermarking is :

- **Lossless** for downstream consumers (no body mutation).
- **Compatible** with streaming responses (headers are emitted before
  the body in HTTP semantics).
- **Standard for HTTP** — `X-*` custom-namespace prefix avoids
  collision with future `AI-*` reserved headers (the EU CoP draft
  Dec-2025 hints at standardising `AI-Generated`-style headers but
  does not yet ; using `X-Ichor-AI-*` namespace future-proofs us).

C2PA/SynthID may follow in a successor ADR if/when Ichor produces
synthetic images (knowledge-graph thumbnails, regime quadrant
charts) — out of scope for this ADR.

### Pure-data routes excluded

The default prefix list explicitly **omits** :

- `/v1/market` — collector OHLCV (Stooq, yfinance, Polygon)
- `/v1/fred` — FRED Observations API passthrough
- `/v1/calendar`, `/v1/sources` — pure metadata
- `/v1/correlations`, `/v1/macro-pulse` — computed from collector
  outputs without LLM enrichment
- `/v1/tools/*` — Capability 5 client tools (data-only return shape)
- `/healthz`, `/metrics` — infra
- All routers that return SQLAlchemy ORM rows verbatim

Watermarking pure-data routes would be **legally incorrect** : EU AI
Act §50.2 applies to _AI-generated_ content. Macro observations are
collector outputs. ADR-029 §"Methodology page only" already documents
the legal distinction.

## Consequences

### Positive

- Compliance with EU AI Act §50.2 enforcement date (2026-08-02) on
  the API surface, complementary to ADR-029's web2 disclosure surface.
- Machine-parseable for downstream consumers (web2 dashboard can
  show a "AI-generated" badge ; future CLI tools and API integrations
  can audit at the network layer).
- Per-route configurable via Settings — adding a new LLM-derived
  endpoint requires only a Settings update.
- Allocation-free hot path (path-prefix tuple lookup).

### Accepted

- Streaming responses (none currently in apps/api — all routes return
  JSON object) would need a different watermark strategy (in-stream
  metadata frames). Not in scope ; revisit if streaming endpoints
  ship.
- Server-Sent Events (`/ws/dashboard`) are not currently watermarked
  by this middleware. The WS protocol upgrades the connection and
  bypasses the response cycle ; if WS frames ever carry LLM-derived
  text, a separate frame-level watermark is required (likely a
  dedicated SSE event type like `event: ai-generated`).
- The `X-Ichor-AI-Provider` tag must be kept in sync with the actual
  model used. Model upgrades already trigger ADRs (cf ADR-029 §Cons :
  "model changes already trigger an ADR") ; the same wave updates this
  tag.

### Required follow-ups

- **Frontend consumption** — `apps/web2` should read
  `X-Ichor-AI-Provider` from the response and surface it in the UI
  (e.g. tooltip on the AI banner). Not a blocker for §50.2 compliance,
  but improves UX. Ticket : W89 candidate.
- **API documentation** — add a section to the OpenAPI schema (via
  FastAPI route extras) documenting the watermark headers. Not
  blocking ; W89.
- **Robots.txt + Well-Known** — EU CoP draft suggests publishing a
  `/.well-known/ai-content` endpoint that lists watermarked URL
  patterns. Currently the watermark is per-response only. Future
  ADR if/when CoP final guidance mandates it.

### Future-revisit clauses

- If the EU final Code of Practice (mid-2026) mandates a different
  header naming scheme (e.g. `Content-AI-Generated`), this ADR is
  superseded by an `ADR-NNN-eu-cop-final-watermark` that renames the
  headers and bumps a translation period.
- If Ichor ever generates synthetic images (e.g. matplotlib regime
  charts that are LLM-prompted), C2PA manifests need a parallel
  middleware (image-content-type aware). Successor ADR.

## Implementation references

- `apps/api/src/ichor_api/middleware/ai_watermark.py` — the middleware
  class (~110 lines).
- `apps/api/src/ichor_api/middleware/__init__.py` — package entry.
- `apps/api/src/ichor_api/config.py` — three new Settings fields :
  `ai_watermarked_route_prefixes`, `ai_provider_tag`, `ai_disclosure_url`.
- `apps/api/src/ichor_api/main.py` — middleware mount between
  `RateLimitMiddleware` and `CSPSecurityHeadersMiddleware`.
- `apps/api/tests/test_ai_watermark_middleware.py` — 7 tests covering
  the LLM/pure-data dichotomy, RFC3339 timestamp, default prefix set,
  config overrides, parametrized path-prefix matching.

## References

- Regulation (EU) 2024/1689 (EU AI Act) Article 50 — transparency
  obligations for providers and deployers.
- EU AI Act Article 113 — transitional clauses, §50 enforcement
  2026-08-02.
- EU Code of Practice on AI-Generated Content — draft 2 (Dec 2025).
- AMF DOC-2008-23 vf4_3 (fév 2024) — French investment-advice
  taxonomy (already covered by ADR-029).
- Anthropic Usage Policy 2026 — high-risk financial advice
  disclosure requirements (already covered by ADR-029).
- ADR-009, ADR-017, ADR-026, ADR-027, ADR-029, ADR-077, ADR-078.
