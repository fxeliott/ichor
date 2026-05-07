# ADR-029: EU AI Act §50 + AMF DOC-2008-23 disclosure footer

- **Status**: Accepted (ratification post-implementation, commit `19f2a68`)
- **Date**: 2026-05-06 (code landed); ratification 2026-05-06
- **Deciders**: Eliot
- **Implements**: legal floor declared in ADR-017 boundary, made surface

## Context

Two regulatory deadlines hit Ichor's surface in 2026 :

### EU AI Act Article 50 (transparency)

- **Enforcement date** : **2026-08-02** (ferme, no further deferral
  per the December 2025 EU Code of Practice draft on marking &
  labelling).
- **§50.1** mandates informing the user when interacting with an AI
  system.
- **§50.5** requires that the disclosure be made "in a clear and
  distinguishable manner at the latest at the time of the first
  interaction or exposure".
- **§50.4** applies to AI-generated public content (cards, briefings)
  with an editorial-review exemption that we DO NOT claim — Ichor
  briefings are unsupervised LLM output by design.

### AMF DOC-2008-23 (French regulator — investment advice boundary)

- Position vf4_3 (février 2024) defines the **5 cumulative criteria**
  for an investment advice service. Ichor produces probability
  distributions and bias direction but :
  - is not personalised (1 user, no client base),
  - emits no order recommendation tied to a specific transaction,
  - does not present results as suitable for a particular person,
  - is not a paid service (Eliot's own use),
  - none of the 5 criteria is met cumulatively.
- Therefore Ichor sits outside DOC-2008-23 by construction (cf
  ADR-017 boundary "Ichor never executes any order, ever").
- AMF expects this to be **stated explicitly on the surface** when
  the platform produces market-flavoured output.

## Decision

Surface both disclosures permanently in the web2 dashboard layout :

### `AIDisclosureBanner` — sticky top, persistent, non-dismissible

- Lives in `apps/web2/components/ui/ai-disclosure-banner.tsx`,
  mounted in `apps/web2/app/layout.tsx` next to the WCAG skip-link.
- **Names Claude Opus 4.7 explicitly** (per Dec 2025 EU CoP draft on
  marking & labelling — "the AI provider must be identified, not just
  the system class").
- Never blocks interaction (no modal, no overlay, no opt-in delay).
- Points to `/methodology` for full disclosure depth.

### `LegalFooter` — bottom of every page

- Lives in `apps/web2/components/ui/legal-footer.tsx`,
  mounted globally.
- Spells out the AMF DOC-2008-23 (vf4_3, fév 2024) boundary :
  - "non-personalised generic macro analysis"
  - "none of the 5 cumulative criteria of investment advice service
    are met"
- Reaffirms the trade-disclaimer + Brier-calibration pointer per
  ADR-017 contractual boundary.

## Consequences

### Pros

- **EU AI Act §50 compliance** before the 2026-08-02 deadline. No
  scramble in late July.
- **AMF DOC-2008-23 boundary visible** to anyone visiting the
  surface — preempts a regulator question.
- **Trust signal for Eliot** (single user) : if/when Ichor is shared
  to an inner circle, the disclosures are already there.

### Cons

- **Vertical real estate cost** : top banner + bottom footer eat
  ~80 px combined. On dense data-tables (e.g. `/admin`, `/sources`)
  this is non-trivial. Mitigation : banner is height-fixed; footer
  scrolls into view rather than docking.
- **Maintenance** : the banner names Claude Opus 4.7 by ID. Any
  model change (Opus 4.8, Haiku 4.5 fallback for Couche-2) requires
  banner copy update. Acceptable because model changes already
  trigger an ADR.

### Neutral

- The banner/footer copy is in French. If/when an EN locale is
  added, both components will need translation strings — but the
  legal substance does NOT change (AMF doctrine is FR-jurisdiction
  scoped, EU AI Act EN/FR mapping is canonical).

## Alternatives considered

### A — Modal on first visit

Rejected : §50.5 says "clear and distinguishable manner", a modal
that's dismissible doesn't remain "clear" after first dismissal.
Persistent surface element is safer.

### B — Methodology page only, no banner

Rejected : §50.5 says "at the time of the first interaction or
exposure". A buried page doesn't satisfy "first exposure" — user
might never click `/methodology`.

### C — Disclosure in /robots.txt or HTTP header

Rejected : §50.1 mandates the human-facing disclosure. Machine-only
metadata is necessary but not sufficient.

## Implementation

Code already shipped in commit `19f2a68` :

- `apps/web2/components/ui/ai-disclosure-banner.tsx` (NEW)
- `apps/web2/components/ui/legal-footer.tsx` (NEW)
- `apps/web2/app/layout.tsx` (banner + footer mounted)
- `apps/web2/app/methodology/page.tsx` (disclosure depth target)

Verified at 2026-05-06 :

- Banner visible on every route
- Footer visible at scroll bottom of every route
- Names Claude Opus 4.7 (model identifier per EU CoP marking spec)

## Related

- ADR-017 — boundary contractual (no order ever ; this ADR makes the
  boundary visible to the user, not just to the codebase).
- Future ADR — locale (EN translation when audience expands).
- `docs/legal/ai-disclosure.md` and `docs/legal/amf-mapping.md`
  contain the full legal-counsel-grade rationale.
