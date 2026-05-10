# ADR-080: Disclosure surface contract — `/legal/ai-disclosure` + `/methodology` + `/.well-known/ai-content`

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes**: none
- **Related**: ADR-026 (frontend WCAG 2.2 AA + Lighthouse), ADR-029
  (EU AI Act §50 + AMF DOC-2008-23 disclosure surface), ADR-077
  (Capability 5 STEP-3 MCP wire), ADR-078 (Cap5 query_db excludes
  trader_notes), ADR-079 (EU AI Act §50.2 watermark middleware)

## Context

ADR-079 (W88) ratified the machine-readable watermark middleware
that emits `X-Ichor-AI-{Generated, Provider, Generated-At,
Disclosure}` on every LLM-derived API response. The
`X-Ichor-AI-Disclosure` header points to
`https://app-ichor.pages.dev/legal/ai-disclosure`.

A 2026-05-09 audit of `apps/web2/app/` revealed two **silent
404s** that constitute a compliance regression :

1. `apps/web2/app/legal/ai-disclosure/page.tsx` did **not exist**
   on disk despite ADR-079 hardcoding the URL into every API
   response watermark.
2. `apps/web2/app/methodology/page.tsx` did **not exist** despite
   `LegalFooter:47` (`<a href="/methodology">`) and
   `AIDisclosureBanner:44` (`<a href="/methodology">`) linking to
   it. Both components are mounted in `apps/web2/app/layout.tsx`,
   so every rendered page contains broken disclosure links.

This is a hard EU AI Act §50.5 violation : the standard requires
disclosure "in a clear and distinguishable manner" — a 404 link is
neither clear nor distinguishable.

## Decision

This ADR codifies the **disclosure surface contract** as a set of
three URLs that MUST stay reachable, public, and content-stable :

| URL                       | Purpose                                                      | Owner                                          |
| ------------------------- | ------------------------------------------------------------ | ---------------------------------------------- |
| `/legal/ai-disclosure`    | Human-readable EU AI Act §50 + AMF + Anthropic AUP narrative | `apps/web2/app/legal/ai-disclosure/page.tsx`   |
| `/methodology`            | Pipeline overview (4-pass + Couche-2 + data-pool + Critic)   | `apps/web2/app/methodology/page.tsx`           |
| `/.well-known/ai-content` | Machine-readable watermark inventory (EU CoP draft Dec-2025) | `apps/api/src/ichor_api/routers/well_known.py` |

### `/legal/ai-disclosure` (web2)

Public static page (`export const dynamic = "force-static"`).
Sections :

1. Avis canonique (verbatim wording from `docs/legal/ai-disclosure.md`).
2. Cadres réglementaires : EU AI Act Article 50 verbatim, AMF
   DOC-2008-23 5-criteria mapping, Anthropic Usage Policy 2026.
3. Watermark machine-lisible : the 4 headers + their semantics.
4. Frontière contractuelle : ADR-017 boundary + ADR-078 journal
   exclusion + Voie D + cap 95 %.

WCAG 2.2 AA compliant per ADR-026 (semantic HTML, contrast tokens,
heading hierarchy, focus-visible).

### `/methodology` (web2)

Public static page. Sections :

1. Pipeline 4-pass + Pass 5 description (régime → asset → stress
   → invalidation, Critic gate).
2. Couche-2 agents (5 agents on Haiku low per ADR-023).
3. Data-pool (43 sections W79 cross-asset matrix v2, key sources
   enumerated).
4. Calibration Brier publique (ADR-025 reference).
5. Frontière contractuelle (link to `/legal/ai-disclosure`).

### `/.well-known/ai-content` (apps/api)

GET-only public endpoint, schema v1 :

```json
{
  "schema_version": 1,
  "spec": "EU AI Act Article 50(2)",
  "host_role": "deployer",
  "provider": "anthropic-claude-opus-4-7",
  "disclosure_url": "https://app-ichor.pages.dev/legal/ai-disclosure",
  "watermarked_prefixes": [
    "/v1/briefings",
    "/v1/sessions",
    "/v1/post-mortems",
    "/v1/today",
    "/v1/scenarios"
  ],
  "watermark_headers": [
    "X-Ichor-AI-Generated",
    "X-Ichor-AI-Provider",
    "X-Ichor-AI-Generated-At",
    "X-Ichor-AI-Disclosure"
  ],
  "generated_at": "2026-05-09T23:00:00Z"
}
```

Driven by `Settings.ai_*` fields (single source of truth — same
config that the W88 middleware reads). 5-minute public cache. Schema
version is bumped only when the field set changes structurally ;
content updates inside the existing fields do NOT bump the version.

### Static rendering invariant

Both web2 pages set `export const dynamic = "force-static"` so they
are pre-rendered at build time and served from Cloudflare Pages
cache. This guarantees they cannot 404 due to a runtime DB outage,
and keeps the disclosure URL stable even if `apps/api` is briefly
unreachable.

The pages must NOT depend on backend data fetches. If a page wants
to enrich content (e.g. show the live model version), it must do so
via build-time generation, not request-time. This invariant is
enforced by code review until a CI lint rule lands (W90 candidate).

## Why three surfaces and not one

| Audience                           | Surface                                 | Format                           |
| ---------------------------------- | --------------------------------------- | -------------------------------- |
| Human (Eliot, regulator, auditor)  | `/legal/ai-disclosure` + `/methodology` | HTML, French native, WCAG 2.2 AA |
| Audit tools, crawlers, API clients | `/.well-known/ai-content`               | JSON, schema-versioned, English  |
| API runtime consumers              | `X-Ichor-AI-*` response headers         | HTTP headers, RFC3339 timestamps |

Each surface answers a different question :

- Header watermark → "is _this specific response_ AI-generated ?"
- Well-known endpoint → "what URL families on this host are AI-generated ?"
- HTML pages → "what's the human-readable explanation of the above ?"

Splitting them lets the compliance-reading regulator click `/legal/ai-disclosure`
without parsing JSON, while the audit crawler hits `/.well-known/ai-content`
without rendering React. Neither subsumes the other.

## Consequences

### Positive

- EU AI Act §50.5 ("clear and distinguishable") closed on the web
  surface (was silently broken before this ADR).
- EU AI Act §50.2 ("machine-readable") fully closed across both
  per-response headers (W88) and host-level discovery endpoint (W89).
- AMF DOC-2008-23 5-criteria mapping is rendered explicitly on the
  legal page — matches the audit-mapping document.
- Static-rendered pages cannot 404 via runtime failure.

### Accepted

- Content drift risk : the `/legal/ai-disclosure` page narrative is
  hand-maintained alongside `docs/legal/ai-disclosure.md`. Same wording
  must propagate to both. Reviewer must cross-check on any update.
- The `disclosure_url` and `provider` in `/.well-known/ai-content` come
  from Settings — they MUST be updated in the same wave that bumps
  the model version (cf ADR-029 §Cons "model changes already trigger
  an ADR").
- Static pre-rendering means the model version surfaced in the HTML
  is whatever was current at build time. If the model upgrade ships
  separately from the build, there's a transient inconsistency
  window. Acceptable — the watermark headers (live config) take
  precedence and are the authoritative source per-response.

### Required follow-ups

- **W90 candidate** — Frontend banner reads `X-Ichor-AI-Provider` from
  the response and displays it in the AIDisclosureBanner tooltip.
  Closes the static-rendering inconsistency window mentioned above.
- **W91 candidate** — CI lint rule that prevents `/legal/ai-disclosure`
  and `/methodology` from importing fetch-based data (force-static
  invariant enforcement).
- **Future revisit** — If the EU final Code of Practice (mid-2026)
  standardises a different `.well-known` path or schema, supersede
  this ADR.

## Implementation references

- `apps/web2/app/legal/ai-disclosure/page.tsx` — disclosure page.
- `apps/web2/app/methodology/page.tsx` — methodology page.
- `apps/api/src/ichor_api/routers/well_known.py` — endpoint.
- `apps/api/tests/test_well_known_ai_content.py` — 7 tests covering
  the JSON schema, prefix-set alignment, RFC3339 timestamp,
  cache-control header.
- `apps/api/src/ichor_api/middleware/ai_watermark.py` — header source
  (ADR-079 reference).
- `docs/legal/ai-disclosure.md` — canonical wording document.

## References

- ADR-026, ADR-029, ADR-077, ADR-078, ADR-079.
- EU AI Act Article 50(2) and (5).
- EU Code of Practice on AI-Generated Content — draft 2 (Dec 2025).
- AMF Position DOC-2008-23 vf4_3 (fév 2024).
- Anthropic Usage Policy 2026.
