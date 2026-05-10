# ADR-076: Frontend `MOCK_*` constants are graceful fallbacks, not stale demos — keep the pattern

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-018 (frontend rebuild Phase 2),
  ADR-026 (frontend WCAG 2.2 AA + Lighthouse)

## Context

The W78 wave was scoped as "Frontend MOCK retire batch — 12 pages
hardcoded MOCK*\*". The `CLAUDE.md` "Things subtly broken or deferred"
section listed it as a tech-debt item, and the project memory had it
flagged as "12 pages still hardcoded MOCK*".

W78 audit (2026-05-09, dedicated subagent run on the 12 listed pages)
revealed the framing was wrong:

- **None of the 12 pages are hardcoded MOCK\_\***. All 12 use a
  `apiGet(...) → isLive(data) ? adapt(data) : MOCK_FALLBACK`
  pattern, where `MOCK_FALLBACK` is a graceful offline state shown
  only when the API returns no data, an error, or a non-ready flag.
- **The corresponding API endpoint exists and is wired in all 12
  cases**. The `adapt(data)` shape-transform is already implemented
  in `apps/web2/lib/<page>-adapters.ts` for each page.
- **One genuine missing endpoint**: the `WHALES` constant in
  `app/polymarket/page.tsx:76` (a Polymarket trade-tape feed). It's
  not a `MOCK_*` and has no backend collector — would need a new
  Polymarket trades-ingestion collector to retire.

So W78 isn't a "wire the frontend" wave — the wiring is done. The
`MOCK_*` constants serve as graceful UX fallbacks: when the API is
slow, restarting, or returning an empty payload, the dashboard still
shows reasonable demo data with the obvious caveat that it's a
fallback (every page renders an "offline · stale" badge when
`isLive()` returns false).

The audit produced an effort-tier breakdown:

| Tier        | Pages                                                                                                    | What "retire" means                                                                                             |
| ----------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| TRIVIAL ×10 | briefings, post-mortems, alerts, news, narratives, calibration, assets, today, correlations, macro-pulse | Replace `MOCK_*` with empty-state component + retry button. No backend change.                                  |
| EASY ×1     | replay                                                                                                   | Same as TRIVIAL + extend `SessionCardOut` with `thesis` field (currently derived via `deriveExcerpt`).          |
| MEDIUM ×1   | polymarket                                                                                               | TRIVIAL for `MOCK_MARKETS` + `MOCK_DIVERGENCES`; HARD for `WHALES` (needs new Polymarket trade-tape collector). |

## Decision

**Keep the graceful-fallback pattern**. Reframe the tech-debt item
from "12 pages hardcoded MOCK\_\*" (incorrect framing) to "12 pages
have demo-data fallbacks; choose UX strategy when API is slow/empty".

The pattern is **defensible** under three angles:

1. **UX**: an empty dashboard with no data is worse than a dashboard
   with reasonable demo numbers + visible "offline / stale" badge.
   The user can still see the layout, the explanation, the structure.
2. **Resilience**: API outages (cold start, restart, transient
   timeout) don't break the UI catastrophically.
3. **Demo path**: investor demos / screenshots remain coherent
   without depending on a hot live API.

The previous CLAUDE.md framing ("12 pages hardcoded MOCK\_") was
inherited from an earlier audit that didn't catch the `isLive()`
guard. This ADR corrects the record.

### Mandatory annotations

To make the pattern self-documenting and prevent future audits from
re-litigating the same finding, every `MOCK_*` constant declaration
must carry a comment of the form:

```ts
// MOCK_FALLBACK — graceful offline state per ADR-076.
// API endpoint: /v1/<route>. Adapter: adapt<X>().
// Replaced by empty-state component when ADR-076 is superseded.
const MOCK_BRIEFINGS: BriefingItem[] = [
  /* ... */
];
```

Annotation work is **out of scope for this ADR** — it's a small
cleanup that any subsequent frontend pass should apply en passant.

### When to revisit

ADR-076 should be re-litigated if:

- The empty-state UX with retry button is implemented as a reusable
  component and proven equivalent or better than the current fallback.
- Investor / partner stakeholders explicitly object to the fallback
  pattern (e.g. concern about misleading demo data).
- A regulatory framework (post-AMF DOC-2008-23 review) demands the
  UI never show synthetic data without a clear watermark.

## Consequences

### Positive

- **CLAUDE.md tech-debt list shrinks by one item** — the "12 pages
  MOCK\_" line is corrected.
- **No frontend code change required**. The 12 pages are already
  doing the right thing.
- **Future frontend wave isn't blocked** by a misframed tech-debt
  item. The actual remaining work is one EASY (replay thesis field)
  - one HARD (Polymarket trade-tape collector for WHALES). Both are
    isolated and can be picked up independently.

### Negative

- **The `MOCK_*` constants do duplicate the canonical shape** for
  each page. If the API shape evolves, the fallback can drift. The
  TypeScript `Adapter` typing catches most cases at compile time,
  but not all. Mitigation: future Storybook coverage on the
  fallback states would lock the contract.
- **A future audit may again misread the pattern** as hardcoded
  mocks. The mandatory annotation (above) prevents this.

### Out of scope

- **`replay` thesis field extension**: deferred to next frontend
  pass (1h estimate). Add `thesis: str | None` to `SessionCardOut`
  and feed `card.thesis` instead of the `deriveExcerpt` proxy.
- **Polymarket WHALES trade-tape**: a separate ADR + new collector
  is required if Eliot decides this surface is worth shipping.
  Suggested ADR-NNN: "Polymarket trades collector — whale-detect
  on session cards."

## Alternatives considered

- **Retire all `MOCK_*` immediately** — rejected: would degrade UX
  on transient API issues. The cost of the fallback is small (a few
  KB per bundle); the benefit (no broken-empty UI) is large.
- **Replace `MOCK_*` with skeleton UI** — accepted as a future
  enhancement (see "When to revisit"), not as immediate work. A
  reusable `<EmptyStateWithRetry asset="..." />` component would
  be the right path.

## References

- W78 audit summary: 2026-05-09 (this ADR)
- `apps/web2/app/{briefings,post-mortems,alerts,news,narratives,calibration,assets,today,correlations,macro-pulse,replay/[asset],polymarket}/page.tsx`
- Adapters: `apps/web2/lib/{today,session-card,calibration,...}-adapters.ts`
- Backend routes audited: `apps/api/src/ichor_api/routers/{briefings,post_mortems,alerts,news,narratives,calibration,today,correlations,macro_pulse,sessions,polymarket_impact,divergence}.py`
- ADR-018 (frontend rebuild Phase 2 baseline)
- ADR-026 (WCAG 2.2 AA + Lighthouse — empty-state UX is in scope of
  the next frontend hardening pass)
