# AI Disclosure — Ichor

> **Status**: Draft v1, pending counsel review before any external publication.
> **Last updated**: 2026-05-02

## Why this document exists

Three legal frameworks converge on a hard requirement: **every Ichor output
shown to a human must explicitly disclose AI generation**.

1. **EU AI Act Article 50** (transparency obligation, effective 2026-08-02):
   "Providers shall ensure that AI systems intended to interact directly with
   natural persons are designed and developed in such a way that the natural
   persons concerned are informed that they are interacting with an AI system."
2. **Anthropic Usage Policy** (sept 2025): "personalized financial advice"
   classified as **high-risk use case**, mandating AI disclosure + human-in-
   the-loop on every output.
3. **AMF Position DOC-2008-23** (modified 2024-02-13): the line between
   "informational analysis" (allowed without licence) and "investment advice"
   (regulated) is partly defined by transparency about the source.

## Disclosure surfaces

| Surface | Disclosure required | Implementation |
|---|---|---|
| Web dashboard | `<DisclaimerBanner />` always visible | `packages/ui/src/components/DisclaimerBanner.tsx` |
| Briefing markdown | Persona-baked footer | `apps/claude-runner/.../personas/ichor.md` |
| Audio (TTS) | Spoken prefix before content | `packages/agents/.../voice/tts.py` (TBD Phase 0 W4) |
| Email export (Phase 1+) | HTML banner + text footer | TBD |
| PDF export (Phase 2+) | Cover page + every-page footer | TBD |
| API responses | Header `X-Ichor-AI-Generated: true` | TBD |
| Push notifications (PWA) | Subject prefix `[IA]` | TBD |

## Canonical wording (French — the user's language)

Long form (full screen, PDF cover, email body):

> *« Contenu généré par intelligence artificielle (Claude, Anthropic),
> assemblé par la chaîne Ichor. Analyse non personnalisée à but informatif
> uniquement. Ne constitue pas un conseil en investissement personnalisé au
> sens de la position AMF DOC-2008-23. Vérifiez les sources avant toute
> décision. »*

Compact form (top bar, push subject, every-page footer):

> *« Avis IA · Analyse non personnalisée · Pas un conseil en investissement (AMF DOC-2008-23) »*

Audio prefix (spoken before every briefing):

> *« Briefing Ichor généré par intelligence artificielle. Analyse non
> personnalisée. »*

## Hard rules (do not weaken without counsel sign-off)

1. The disclosure **MUST** appear on the same screen as the analysis,
   not behind a click. (The "click to dismiss" disclosure has been litigated
   and lost — the user must see it without action.)
2. The disclosure **MUST** be in the user's language (French for Eliot,
   localized when we add other locales).
3. The disclosure **MUST NOT** be smaller than 11pt or 80% of body text
   contrast (visible at a glance).
4. The disclosure **MUST** mention both the AI provider (Anthropic, "the
   model") AND the system orchestrator (Ichor, "the assembler").
5. The footer in every briefing markdown is enforced by the persona prompt
   — modifying or removing the footer at runtime constitutes a TOS violation
   and is a P0 incident.

## When the rules might soften (future)

- If Ichor moves to "informational tool only" with no per-asset directional
  bias output (regulators may treat this differently — likely Phase 7+).
- If the EU AI Act drafting clarifies which use cases are exempt
  (very unlikely for FX/equity intelligence).
- If Anthropic publishes a paid tier with explicit production licence
  including waiver of the high-risk classification (no such product
  announced as of 2026-05).

Until then: **the canonical wording above is non-negotiable on every
user-facing surface**.

## References

- [EU AI Act full text](https://artificialintelligenceact.eu/)
- [EU AI Act implementation timeline](https://artificialintelligenceact.eu/implementation-timeline/)
- [Anthropic Usage Policy](https://www.anthropic.com/legal/aup)
- [AMF DOC-2008-23 (search)](https://www.amf-france.org/fr/recherche/resultat?form_build_id=&form_id=amf_search_form&search_input=DOC-2008-23)
