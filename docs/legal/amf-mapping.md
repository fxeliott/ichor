# AMF mapping — Ichor's compliance posture vs Position DOC-2008-23

> **Status**: Draft v1, pending counsel review.
> **Last updated**: 2026-05-02

## Summary

Ichor is positioned as a **non-personalized informational analysis service**.
This places it OUTSIDE the strict definition of "investment advice" (conseil
en investissement) under AMF Position DOC-2008-23, but inside its
**transparency obligations** (clear identification as analysis vs advice).

## The DOC-2008-23 framework (simplified)

DOC-2008-23 distinguishes:

| Service type         | Personalization                             | Regulatory requirement                                                             |
| -------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| Investment advice    | YES — recommendation specific to ONE client | Conseiller en investissements financiers (CIF) licence + ACPR registration + ORIAS |
| General research     | NO — same content for all readers           | Disclosure of nature + author + conflicts                                          |
| Portfolio management | YES + executes                              | Société de gestion + AMF licence                                                   |

The line between "general research" and "investment advice" is drawn by
**personalization**:

- "EUR/USD biased short, IC 55-65%" → general research
- "Eliot, you should sell EUR/USD given your portfolio" → investment advice

## Where Ichor sits

| Ichor feature                   | Classification                                                  | Notes                                                                  |
| ------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Briefings 4×/day                | General research                                                | Same content for all (currently 1) users; no per-portfolio reasoning   |
| Asset cards (bias bar + regime) | General research                                                | Aggregated indicators, no buy/sell                                     |
| Alerts (33 types)               | General research / market data                                  | Threshold breaches on public data                                      |
| `/performance` dashboard        | Self-disclosure (transparency, not regulated)                   | Calibration scores, Brier, etc.                                        |
| Drill-down on click             | Borderline — could become advice if "Eliot's holdings" injected | **DESIGN CONSTRAINT: never inject portfolio data into Claude prompts** |
| Audio briefings                 | General research                                                | Same as text                                                           |

## Hard design constraints to stay general-research

The following constraints are baked into the architecture and MUST NOT be
weakened without legal counsel sign-off:

1. **No portfolio data in prompts.** The `claude-runner` subprocess never
   receives Eliot's holdings, sizes, P&L, or risk budget. The persona prompt
   `personas/ichor.md` mandates probabilistic outputs without sizing.

2. **No "you should" language.** The persona Hard Rules section bans
   "Eliot, you should…" / "buy" / "sell" verbs. Outputs are tilts +
   probabilities, not orders.

3. **AI disclosure on every surface.** See `docs/legal/ai-disclosure.md`.
   The disclosure makes clear that this is automated analysis, not advice.

4. **Single-user during Phase 0/1.** Ichor is internal-use until external
   counsel review. If we ever expose to external users (Phase 7+), counsel
   review of DOC-2008-23 + MiFID II Article 4(1)(4) becomes mandatory before
   launch.

5. **No execution.** Ichor never sends orders to a broker. The user (Eliot)
   makes all execution decisions manually. This is the strongest defense
   against being classified as portfolio management.

## Per-language considerations

- **French content** (default): AMF DOC-2008-23 applies (Eliot is in France).
- **English content** (Phase 7+ if any): UK FCA + EU ESMA equivalents to
  consult separately. Lower priority for Phase 0/1.

## When to re-engage counsel

- Before any public launch (paid or free)
- Before adding portfolio integration (would change classification)
- Before adding execution capability
- Before allowing users to add custom watchlists that Claude sees
- Before introducing per-user persona overrides
- After any AMF guidance update that touches AI-generated analysis

## References

- AMF Position [DOC-2008-23](https://www.amf-france.org/) (search the doc title)
- ESMA [Supervisory Briefing on personalized recommendations](https://www.esma.europa.eu/) (July 2023)
- MiFID II Directive 2014/65/EU Article 4(1)(4) — definition of "investment advice"
