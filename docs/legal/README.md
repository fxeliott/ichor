# Legal & compliance

Documentation of Ichor's compliance posture across:

- **AMF (France)** — Position DOC-2008-23 (modified 2024-02-13). Ichor is
  non-personalized analysis (no specific recommendation per client),
  positioned outside the strict definition of "investment advice". Detailed
  mapping in `amf-mapping.md` (TBD).
- **EU AI Act (effective 2026-08-02)** — Articles 8-15 (high-risk),
  **Article 50 (transparency / AI-generated content disclosure)**, Articles
  53-56 (GPAI), Article 101 (fines €15M or 3% global turnover). Ichor likely
  qualifies as "limited risk" but **Article 50 mandates AI disclosure on every
  user-facing output**.
- **Anthropic Usage Policy** — "personalized financial advice" classified as
  **high-risk use case** (NOT prohibited categorically). Requires:
  human-in-the-loop validation + AI disclosure on every export. Ichor
  non-personalized = OK with disclosure.

## Documents (TBD)

| File                                                | Status            | Trigger                     |
| --------------------------------------------------- | ----------------- | --------------------------- |
| `ai-disclosure.md`                                  | ⬜ TBD Phase 0 W4 | Article 50 mandate          |
| `amf-mapping.md`                                    | ⬜ TBD Phase 0 W4 | DOC-2008-23 vs Ichor        |
| `cgu-v0.md` (Conditions Générales)                  | ⬜ TBD Phase 1    | Pre-launch                  |
| `privacy-policy-v0.md`                              | ⬜ TBD Phase 1    | RGPD baseline               |
| `dpia-draft.md` (Data Protection Impact Assessment) | ⬜ TBD Phase 1    | If processing personal data |
| `terms-of-use-disclaimer.md`                        | ⬜ TBD Phase 0 W4 | Disclaimer modal in UI      |

## AI disclosure — minimum text (placeholder)

> _« Contenu généré par intelligence artificielle. Ichor produit des analyses
> non personnalisées à but informatif. Ce contenu ne constitue pas un conseil
> en investissement personnalisé au sens de la position AMF DOC-2008-23.
> Vérifiez les sources avant toute décision. »_

This wording is to be reviewed by counsel before any external publication.

## References

- AMF Position [DOC-2008-23](https://www.amf-france.org/) (search the title)
- EU AI Act [implementation timeline](https://artificialintelligenceact.eu/implementation-timeline/)
- Anthropic [Usage Policy](https://www.anthropic.com/legal/aup)
