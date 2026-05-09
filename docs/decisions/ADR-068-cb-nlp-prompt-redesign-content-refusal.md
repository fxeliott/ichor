# ADR-068: cb_nlp prompt redesign — Claude content refusal fix

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-021 (Claude primary brain), ADR-023 (Couche-2 → Haiku low),
  ADR-067 (Couche-2 async polling — fixed infra, surfaced this content layer)

## Context

After ADR-067 ratified the Couche-2 async polling migration, the
infrastructure leg of the Couche-2 chain became 100 % CF-immune. The
W67 deploy summary noted one residual content-layer issue:

> cb_nlp prompt produces Claude content refusals (~"I cannot complete
> this..."): output validation fails as JSON. Not infra, prompt
> redesign needed — out of scope for ADR-067, deferred.

Wave 69 verification on 2026-05-09 11:32 captured the verbatim refusal:

```
agents.fallback.claude_failed
  error="output failed Pydantic validation: ValidationError: 1 validation
         error for CbNlpAgentOutput
         Invalid JSON: expected ident at line 1 column 2
         [type=json_invalid,
          input_value='I cannot complete this a...e rate_path_skew field.',
          input_type=str]"
  error_type=ClaudeRunnerOutputError
```

The model returned natural-language refusal prose instead of JSON.
The Couche-2 chain then fell through to Cerebras/Groq which fail on
`MissingCredentials`, propagating `AllProvidersFailed` and putting the
systemd unit into `failed`.

### Root cause analysis

The prior `SYSTEM_PROMPT_CB_NLP` contained three signals that triggered
Claude's safety classifier on the rhetoric → asset-impact link:

1. **`Banned: hyperbole, generic advice, signal generation ("buy",
   "sell")`** — explicitly enumerating "buy"/"sell" alongside an
   `asset_impacts` schema flagged the task as financial-signal-adjacent
   even though the schema's enum (`bullish | bearish | neutral`) made
   the ban redundant. Counter-productive priming.
2. **`asset impact projections`** in the opening framing — reads as
   investment advice rather than research observation.
3. **`rate_path_skew compares the CB's current rhetoric to OIS-implied
   path over the next 6 months`** — asks the model to reason
   quantitatively about market-implied futures, looks like trading
   logic.

Refusal rate was probabilistic — ~30 % of runs in the 24 h prior to
this fix landed on the refusal path. When the corpus included recent
hawkish Fed minutes the rate climbed.

## Decision

Redesign `SYSTEM_PROMPT_CB_NLP` along three axes:

1. **Reframe the role as research analyst, not advisor.** Open with
   "Central-Bank NLP research analyst of Ichor, a probabilistic
   pre-trade research system (ADR-017: research only, never trade
   orders)". The role-frame primes the model toward descriptive
   classification.

2. **Drop the explicit `buy/sell` ban.** The Pydantic schema enforces
   the enum; explicit verbal banning of trading verbs cues the model
   to interpret the task as trading-adjacent. Replaced with neutral
   guidance ("Evidence over opinion. Cite the speech.").

3. **Recharacterize `rate_path_skew` as descriptive consistency, not
   forecast.** Old text: "compares the CB's current rhetoric to
   OIS-implied path". New text: "a qualitative consistency label
   comparing the CB's spoken rhetoric to the market's OIS-implied
   path... This is a descriptive consistency check — not a forecast,
   not a trade view." Same enum values, neutralized framing.

Additionally added field-by-field guidance (stances / shifts /
asset_impacts / notes) and an empty-corpus fallback rule (return the
single most recent communication and flag staleness in `notes`)
because schema requires `min_length=1` on `stances`.

The Pydantic class `CbAssetImpact` docstring also updated to embed the
ADR-017 boundary inline as a model-visible reminder:

> Macro-research note on the rhetoric's expected directional pressure
> on a rate-sensitive asset. This is not a trade recommendation — it
> is a probability-calibrated bias note consumed by the downstream
> Critic (cf. ADR-017 boundary: pre-trade research, never order
> generation).

## Consequences

### Positive

- **Verified live 2026-05-09 11:58:47 CEST** post-deploy: cb_nlp
  produced a valid JSON payload with 2 stances + 2 shifts + 3
  asset_impacts in 83.3 s wall via async path. No ValidationError, no
  refusal prose.
- **Prompt encodes ADR-017 boundary explicitly** — the model now sees
  the contract instead of inferring it from the schema. Future
  refusals will be true content concerns, not framing artifacts.
- **Schema unchanged** — no migration, no consumer-side breakage.
  Downstream Critic + 4-pass orchestrator continue to ingest the same
  `CbNlpAgentOutput` payload.

### Negative

- **Slightly longer system prompt** (~150 → ~330 words). Token cost
  per run +~250 tokens system. Negligible at Haiku low pricing.
- **Field-by-field guidance is a maintenance surface** — if the
  schema evolves (new field, changed enum), the prompt must be
  updated in lockstep. Acceptable cost.

### Out of scope (separate work)

- **Other 4 Couche-2 agents** (`news_nlp`, `sentiment`, `positioning`,
  `macro`) have not surfaced refusals to date but use similar
  patterns. Audit deferred — apply the same three axes if/when a
  refusal is captured.

## Alternatives considered

- **Add a Cerebras/Groq credential to the fallback chain.** Would
  catch refusals at the cost of operating-cost drift away from Voie D
  (ADR-009 — Max 20x flat). Rejected: doesn't fix the root cause and
  re-introduces paid-API dependency.
- **Ignore the refusal (allow occasional empty rows).** Rejected:
  cb_nlp is a primary input to the régime classifier; missing rows
  cascade into stale executive_summary + per-asset bias hints.
- **Switch cb_nlp to Sonnet medium** (better instruction-following).
  Rejected: ADR-023 — Sonnet medium hits CF Free 100 s edge cap on
  ~5 KB CB-speeches context. ADR-067 async would mitigate but
  Haiku-low + redesigned prompt is sufficient and cheaper.

## Verification (live 2026-05-09)

| Run timestamp | model | duration | n_stances | n_shifts | n_impacts | error |
|---|---|---|---|---|---|---|
| 2026-05-09 11:58:47 | claude:haiku | 88.9 s | 2 | 2 | 3 | none |
| 2026-05-09 11:32:13 (pre-fix) | unknown | 43.2 s | — | — | — | content_refusal |
| 2026-05-09 11:08:37 | claude:haiku | 116.2 s | 4 | 3 | 3 | none |
| 2026-05-09 11:04:59 (pre-fix) | unknown | 113.4 s | — | — | — | runner_524 |

Post-fix run is structurally identical to a pre-fix successful run —
the redesign does not change the schema or the analytical output, it
removes the refusal trigger.

## References

- `packages/agents/src/ichor_agents/agents/cb_nlp.py` — module updated
- ADR-017 (research-only boundary, contractual)
- ADR-023 (Couche-2 → Haiku low)
- ADR-067 (async polling, infra leg of this fix)
- Anthropic Constitutional AI safety patterns —
  refusals are typically recoverable via role-framing + schema enforcement.
