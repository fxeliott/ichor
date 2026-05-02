# ADR-009: Voie D confirmed — no API consumption, 0€ surprise costs

- **Status**: Accepted (re-confirmed 2026-05-02)
- **Date**: 2026-05-02
- **Decider**: Eliot (explicitly re-stated 2026-05-02 afternoon)

## Context

Earlier in the day I proposed creating an Anthropic Workspace API key
`ichor-prod` for production agent calls. Eliot rejected this and re-confirmed
the original Voie D architecture (`docs/ARCHITECTURE_FINALE.md`):

> "je veux fonctionner full avec l'abonnement claude pro maxx20 que j'ai et
>  mon ordi localement tourne h24 et le serveur hetzner mais je veux pas
>  d'api avec des cout surprise donc voila"

Translation: 100% on the $200/mo Claude Max 20x flat subscription + local
Win11 24/7 + Hetzner. **No usage-based API costs anywhere.**

## Decision

### Allowed cost surfaces

| Service | Cost | Cap |
|---------|------|-----|
| Claude Max 20x | $200/mo flat | 5h rolling + weekly caps |
| Hetzner CX32 (current) | ~€20/mo flat | none (fixed VM) |
| Cloudflare R2 | $0/mo (free 10 GB) | hard limit at 10 GB until paid plan |
| Cloudflare Pages | $0/mo (free) | 500 builds/mo, illimited bandwidth |
| Cloudflare Tunnel | $0/mo (free) | unlimited |
| GitHub | $0/mo (free private repos) | 2000 actions min/mo |
| Cerebras free | $0/mo | **30 RPM hard cap** Llama 3.3-70B |
| Groq free | $0/mo | **1000 RPD hard cap** (most models) |
| Azure Speech free F0 | $0/mo | **5M chars/mo hard cap** Neural TTS |
| OANDA Practice | $0/mo | rate limits, no overage cost |
| FRED API | $0/mo | rate limits, no overage cost |

**Total $200/mo + €20/mo Hetzner = ~$220/mo flat, no surprise costs.**

### Forbidden / blocked

- ❌ **Anthropic API key** (would be usage-based) — rejected
- ❌ **OpenAI API** (already excluded by Eliot rule L12)
- ❌ **Voyage embeddings** (paid) — use bge-large-en-v1.5 self-hosted on Hetzner
- ❌ **ElevenLabs** (paid Pro $99-330/mo) — use Azure Neural FR free
- ❌ **Tradier streaming** (paid Pro $10/mo) — use OANDA practice streaming
- ❌ **Any API where usage scaling = bill scaling**

### Couche 1 (qualitative analysis) — Max 20x via local subprocess

`apps/claude-runner` runs on Win11 24/7. FastAPI on `:8765` exposed to
Hetzner only via Cloudflare Tunnel + Access service-token gating.

Hetzner cron triggers webhooks → `claude-runner` runs `claude -p` headless
subprocess as Eliot's authenticated Claude Code → returns JSON to Hetzner.
Quota consumed: Eliot's Max 20x (5h rolling + weekly caps).

**Mitigations** (see ARCHITECTURE_FINALE risk table):
- 4 grouped briefings/day (not 32 individual) — fits Max 20x easily
- Fallback chain on Max throttle: Cerebras → Groq → static template
- Power Plan never sleep + WoL on Win11
- Cloudflare Tunnel auto-reconnect (`cloudflared --autoupdate`)

### Couche 2 (24/7 LLM automation) — Cerebras + Groq free

Macro / Sentiment / Positioning / News-NLP agents run on Hetzner using
Pydantic AI with Cerebras OpenAI-compatible endpoint as primary, Groq as
fallback. Both 0€.

### Couche 3 (ML, no LLM) — pure Python on Hetzner

LightGBM + hmmlearn + dtaidistance + river + arch + numpyro + vollib +
FOMC-RoBERTa + FinBERT-tone (HuggingFace, CPU). Already specced in
`packages/ml/pyproject.toml`.

### Anthropic risk acceptance (re-confirmed)

Per `docs/ARCHITECTURE_FINALE.md` warning section: Anthropic banned OpenClaw
and 3rd-party Max agents in April 2026; ToS Max 20x states OAuth is
"intended exclusively for ordinary individual use of Claude Code". Pattern
of `claude -p` automation 4×/day from cron is grey area — silent ban risk
of the $200/mo account.

**Eliot accepts this risk** in exchange for fixed-cost predictability.
Mitigation: fallback chain Cerebras/Groq guarantees service continuity
(degraded) if ban occurs.

## Consequences

- `infra/secrets/anthropic.env.example` is kept in repo as **historical
  documentation only** (in case future Eliot wants paid API). The actual
  production path uses Max 20x → claude-runner local.
- Phase 0 W3 step 18-23 (claude-runner + tunnel + cron) becomes **the
  critical path** — that's where Voie D delivers value.
- Phase 1 budget: **$220/mo total** ($200 Max + €20 Hetzner). Optional add:
  Eliot's domain (~$15/yr Phase 1+) + UPS for Win11 (~€80 one-shot).
- **No Anthropic Workspace `ichor-prod` to provision.** Removed from
  `infra/secrets/README.md` Phase 0 expectations.

## Alternatives rejected

- **API key with budget cap $25-50/mo** — rejected by Eliot: "pas d'API
  avec coûts surprise". Even with cap, the bookkeeping + risk of going
  over (cap is best-effort) is unwanted.
- **Wait for Anthropic to launch a usage-based but flat-rate prod tier** —
  no such product announced; speculative.

## References

- [`docs/ARCHITECTURE_FINALE.md`](../ARCHITECTURE_FINALE.md) — full Voie D spec
- [`docs/AUDIT_V3.md`](../AUDIT_V3.md) §4 — Anthropic pricing + Max 20x verdict
- This conversation 2026-05-02 16:xx UTC, Eliot's third autonomy delegation message
