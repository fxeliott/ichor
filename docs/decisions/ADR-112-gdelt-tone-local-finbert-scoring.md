# ADR-112 — Local FinBERT scoring of the dead GDELT tone column

- **Status**: Accepted (2026-06-12)
- **Context session**: S04 re-run #2 (re-fire « tu es sûr d'avoir tout traité ? »)

## Context

The 2026-06-11 S04 runtime witness (post PR #229) discovered that
`gdelt_events.tone` was **0.0 on 13,607/13,607 rows over the full 8-day
retention**. Root cause: the GDELT DOC 2.0 **ArtList JSON feed carries no
per-article tone field** (the official docs enumerate none; live probe was
429-rate-limited but the DB evidence is unambiguous) — the collector's
`float(art.get("tone", 0.0))` default has been applied silently since
ingestion. Blast radius: the geopolitics "most-negative" ranking ranked
nothing (mitigated same-day by the PR #230 column-vitality guard → honest
suspension), the `TARIFF_SHOCK` alert could structurally never fire
(`avg_tone <= -1.5` impossible), and the consumed `/v1/geopolitics/heatmap`
served a flat `mean_tone = 0.0`.

## Decision

Score the tone **locally** with the FinBERT-tone pipeline already serving
`run_news_tone_scorer` on the same host (Voie D: zero external API, zero
LLM call, CPU inference, warm HF cache):

- New CLI `run_gdelt_tone_scorer` + 15-min systemd timer
  (`register-cron-gdelt-tone.sh`), first run backfills 48h.
- **English titles only** (`language = 'English'`, ~62% of rows/48h —
  FinBERT-tone is an English financial-text model). Non-English rows stay
  at an honest neutral 0.0, documented on the model.
- **Scale**: `tone = (p_positive − p_negative) × 10` — continuous signed
  score on the GDELT-like −10..+10 scale every consumer was built for
  (`TARIFF_SHOCK` −1.5 ≙ FinBERT −0.15). The softmax difference beats
  label±confidence on ambivalent headlines.
- **No migration**: `tone = 0.0` keeps meaning "not scored / non-English /
  exactly balanced"; the 6h re-scan window (news-scorer pattern) bounds
  retries; exact-zero scores are skipped (re-enter next tick).
- The PR #230 guard **auto-disarms** once real negative tones enter the
  geopolitics candidate pool — no consumer change required.

## Alternatives rejected

- **GDELT ToneChart mode** (per-query tone histogram + top articles):
  doubles the API request budget per cycle on an endpoint that already
  429s at evening peak (PR #228 politeness), and only covers the bin's
  top-10 articles — partial coverage for 2× the quota.
- **GKG 2.0 V2Tone ingestion**: authoritative per-document tone but a new
  15-min-file ingestion pipeline — a full collector project, not a slice.
- **Separate `tone_scored_at` column (migration)**: cleaner bookkeeping,
  but a schema migration buys little — the continuous score makes
  scored-vs-unscored distinguishable in practice (exact 0.0 is a measure-
  zero event for scored rows) and the 6h window bounds re-scans anyway.
  Revisit only if a consumer ever needs a hard scored/unscored flag.

## Consequences

- The S04 geopolitics dimension's negative-event ranking revives with
  REAL per-article tones; per-asset differentiation (PR #229 pool 400)
  operates on ranked data.
- `TARIFF_SHOCK` becomes fireable again; `/v1/geopolitics/heatmap`
  `mean_tone` carries signal on English coverage.
- Non-English coverage (≈38%) contributes presence (counts, headlines)
  but not tone — acceptable; revisit with a multilingual financial model
  only if a real gap is witnessed.
- Semantics of `gdelt_events.tone` are now "locally-scored GDELT-like
  tone", documented on the model column (models/gdelt_event.py).
- Follow-up (separate slice): column-vitality probes in the S03 freshness
  monitor (zero-variance on critical columns → DATA_QUALITY alert) so the
  next dead column is caught by the monitor, not by a consumer witness.
