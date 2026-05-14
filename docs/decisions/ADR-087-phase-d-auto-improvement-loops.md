# ADR-087: Phase D auto-improvement loops (4-loop architecture + W116c LLM addendum + W117a DSPy foundation)

**Status**: Accepted — codifies what shipped W113-W118 + W116c + W117a (rounds 15-26, PRs #90→#101).
This ADR is **retroactive** : the implementation landed before this contract was written.
Round-27 authored the ADR to close the doctrinal hygiene gap (rule 3 — "ADR avant code")
and to make the four invariants explicit and enforceable for future loops.

**Date**: 2026-05-13

**Supersedes**: none

**Extends**: [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary), [ADR-029](ADR-029-eu-ai-act-50-and-amf-disclosure.md) (audit immutability), [ADR-081](ADR-081-doctrinal-invariant-ci-guards.md) (CI guards), [ADR-085](ADR-085-pass-6-scenario-decompose-taxonomy.md) (Pass-6 7-bucket reconciler — Vovk consumer)

**Related**: ADR-088 (W115c confluence_engine pocket-read, PROPOSED), future W117b GEPA wiring (deferred).

## Context

Phase 2 Ichor emits probability-calibrated session-cards (Pass-1→Pass-4 + Pass-5 counterfactual + Pass-6 scenarios) but, until this ADR, **did not learn from realized outcomes**. The 4-pass orchestrator was stateless across sessions : every fresh card started from the current data-pool, the prior priors were never reconsumed, and the model's calibration could not improve unless Eliot manually inspected post-mortem data.

Round-13 audit (8 dimensions) scored **Couche 9 Auto-Improvement = 2/10**. The Brier reconciler (W105g) and scenario calibration EWMA (W105b) existed, but :

- No immutable audit log of "the loop ran X times, produced Y deltas, here's the trace" (cf ADR-029).
- No concept-drift detector to flag when realized-outcome distribution diverges from prior distribution.
- No expert-aggregator to combine multiple predictors (4-pass output, climatology, equal-weight) under a provable regret bound.
- No proper scoring rule that penalises overconfident wrong calls vs underconfident wrong calls asymmetrically.
- No prompt-mutation/optimization framework that could ever wire to the LLM passes without violating Voie D.

Phase D fills these gaps with four canonical loops + two LLM-touching extensions, all under doctrinal invariants this ADR makes contractual.

## Decision

### Loop 1 — `auto_improvement_log` audit table (W113, migration 0042)

Every Phase D loop **MUST** write one row per fire to `auto_improvement_log` :

```sql
CREATE TABLE auto_improvement_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fired_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    loop_kind    VARCHAR(32) NOT NULL CHECK (loop_kind IN (...)),
    asset        VARCHAR(16),
    regime       VARCHAR(32),
    session_type VARCHAR(16),
    payload      JSONB NOT NULL,
    notes        TEXT
);
```

The table is **immutable** (UPDATE/DELETE rejected by trigger, ADR-029-class). The canonical `loop_kind` enum (pinned by migration `0042_auto_improvement_log.py` CHECK constraint AND service `_VALID_LOOP_KINDS` frozenset) is exactly 4 values :

| `loop_kind`        | Producer                                                                                                                | Cadence                     |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| `brier_aggregator` | `cli/run_brier_aggregator.py` (W115b)                                                                                   | nightly 03:30               |
| `adwin_drift`      | `services/drift_detector.py` (W114)                                                                                     | nightly 02:00               |
| `post_mortem`      | `cli/run_post_mortem_pbs.py` (W116b) AND `cli/run_addendum_generator.py` (W116c — addenda are post-mortem-class writes) | Sunday 18:00 + Sunday 19:00 |
| `meta_prompt`      | reserved for future W117b GEPA optimizer fires                                                                          | on-demand                   |

**Note (round-28 correction)** : an earlier draft of this ADR listed six `loop_kind` values (`concept_drift`, `addendum`, `addenda_eviction`, `dspy_compile` in addition to the canonical four). Those did NOT match the migration or service code ; the table above is the verified source-of-truth. If a future round needs to add a `loop_kind` value (e.g., `gepa_mutation` for W117b), it MUST ship in a migration that ALTERs the CHECK constraint AND updates `_VALID_LOOP_KINDS` in lockstep, with a CI guard test pinning the equality between the two sets.

Helper `services/auto_improvement_log.py:record(loop_kind, asset, regime, session_type, payload, notes)` is the canonical write API.

### Loop 2 — ADWIN concept-drift detector (W114, `services/drift_detector.py`)

Replays realized outcomes through River 0.21+ `ADWIN` (delta=0.001 stream / 0.002 batch). On detected change-point, writes `loop_kind='adwin_drift'` row with `payload={"change_point_at": ..., "magnitude": ..., "asset": ..., "regime": ...}`. Tiered dispatcher : regime / asset / pair-specific instances.

**Cron** : `ichor-drift-detector.timer` nightly 02:00 Paris on Hetzner.

**Optional extras** : `river>=0.21` in `[phase-d]` pyproject.toml extra.

### Loop 3 — Vovk-Zhdanov Aggregating Algorithm (W115, `services/vovk_aggregator.py` + migration 0043)

Implements the η=1 Brier-game AA from Vovk-Zhdanov JMLR 2009, Proposition 2 + Theorem 1. For N experts emitting probabilities `p_i ∈ [0, 1]` on a binary outcome `y ∈ {0, 1}` :

- Loss : `L_i = (p_i - y)²`.
- Weight update : `w_{t+1}(i) ∝ w_t(i) · exp(−η · L_i)` renormalized.
- η=1 substitution (n=2 binary) reduces to **weighted mean** `γ = Σ w_i · p_i`.
- Regret bound : `Regret_T ≤ ln(N) / η = ln(N)`, **constant in T**.

State persisted in `brier_aggregator_weights` table : one row per `(asset, regime, session_type)` pocket with JSONB `weights`, `cumulative_losses`, `expert_kinds`. The three canonical experts are :

1. `prod_predictor` — Ichor 4-pass output P(target_up=1).
2. `climatology` — empirical P(close > open) over last 365 days, fallback 0.5 if n < 8.
3. `equal_weight` — uniform 0.5.

**Cron** : `ichor-brier-aggregator.timer` Sunday 03:30 Paris on Hetzner.

**Empirical proof (2026-05-13)** : autonomous fire 03:32:39 CEST. 16 `auto_improvement_log` rows. NAS100/usd_complacency prod weight 0.358 → 0.464 (gaining skill, n=12). EUR_USD/usd_complacency prod weight 0.300 (anti-skill, n=13 statistically significant — investigation pending ADR-090).

### Loop 4 — Ahmadian Penalized Brier Score (W116, `services/penalized_brier.py`)

Implements the superior-ordering proper scoring rule from Ahmadian et al. arXiv:2407.17697, λ=2.0 :

`PBS(p, y) = Brier(p, y) + λ · (p - climatology_baseline)²`

The penalty rewards predictions that deviate from baseline only when warranted by realized outcomes. Empirically `pbs_correct < pbs_wrong` (verified LIVE on Hetzner Python).

Post-mortem run produces `pass3_addenda` rows (migration 0044) — short LLM-generated narrative refinements gated by Pass-3 stress test. Top-K=3 per pocket, LRU eviction on tie (`services/pass3_addendum_injector.py`).

**Cron** : `ichor-post-mortem-pbs.timer` Sunday 18:00 Paris on Hetzner.

### LLM extension 1 — W116c addendum generator (`services/addendum_generator.py`)

The PBS post-mortem (loop 4) emits a "skill_delta_at_this_session" signal, but the human-readable refinement (what should Pass-3 stress narratively check NEXT time ?) requires an LLM. This is the first NEW LLM-calling cron in Phase D.

**Doctrinal invariants** (rule 16 ban-risk minimisation MANDATORY) :

1. **Routes only via canonical Voie D entry** `ichor_agents.claude_runner.call_agent_task_async`. NEVER direct httpx to `api.anthropic.com` / `console.anthropic.com`.
2. **ADR-017 regex defense-in-depth** : `_BANNED_TOKENS = re.compile(r"\b(BUY|SELL|LONG\s+NOW|SHORT\s+NOW|TP\d*|SL\d*|STOP[- ]LOSS|TAKE[- ]PROFIT|TARGET\s+\d+\.\d+|ENTRY\s+\d+\.\d+|LEVERAGE|MARGIN)\b", re.IGNORECASE)` + `_validate_no_signals(text)` filter BEFORE persistence. If any banned token surfaces, raise `ValueError` and DO NOT write to `pass3_addenda`.
3. **Feature-flag fail-closed** : `w116c_llm_addendum_enabled` row absence in `feature_flags` = "do nothing" exit 0 (NEVER fail-open). Canonical name per `services/addendum_generator.py:21` + `cli/run_addendum_generator.py:44` ; earlier ADR-087 drafts cited `phase_d_w117a_pass3_addenda_enabled` which was a conflation with the W117a DSPy foundation and does NOT exist in code. The W117a foundation is `[phase-d-w117]` extras-gated at module import, not a `feature_flags` row.
4. **Cron spacing ≥ 5 min** from other **LLM-calling** jobs : Sunday 18:00 (W116b PBS — CPU-pure compute) + Sunday 19:00+ (W116c addendum LLM call). The 60+ min spacing between any two LLM-calling fires (currently only W116c + future W117b GEPA + future W115c if it ever calls LLM) is the ban-risk-relevant invariant. **CPU-pure jobs (Aggregator W115b 03:30 + Optimizer V1 SGD 03:30) are EXEMPT from this spacing** : their concurrent fire is operationally OK because they don't touch the claude-runner subprocess. Round-28 ADR clarification — pre-round-28 this exemption was implicit and trader-review flagged the apparent contradiction.
5. **Rate limit** : 24 outputs/24h empirically safe on Max 20x plan (round-26 verified). W116c fires weekly = 1 LLM call/week, well within margin.

**Cron** : `ichor-addendum-generator.timer` Sunday 19:00 Paris on Hetzner. ARMED 2026-05-13 19:03 CEST next fire 2026-05-17.

### LLM extension 2 — W117a DSPy foundation (`services/dspy_claude_runner_lm.py`)

DSPy 3.2 ships with `dspy.BaseLM` extensibility (replacing the deprecated `LM.basic_request`). Ichor's wrapper inherits `dspy.BaseLM` and routes `forward()` through `call_agent_task_async`, making **every** future DSPy-using module Voie D-bound by construction.

**Doctrinal invariants** :

1. **Sentinel namespace** : `_ALLOWED_MODEL_TAGS = frozenset({"ichor-claude-runner-haiku", "ichor-claude-runner-sonnet", "ichor-claude-runner-opus"})`. Constructor REJECTS any `model_tag` not in this set. This blocks the obvious litellm-bait `dspy.LM(model="claude-3-5-haiku-latest")` which would route through litellm → paid Anthropic API. Rejection raises `ValueError("model_tag must be one of: ichor-claude-runner-*")`.
2. **Try-import + stub class** : module stays importable on systems without DSPy installed. Stub class raises `RuntimeError("DSPy 3.2 not installed — install with pip install -e 'apps/api[phase-d-w117]'")` on instantiation. CI gracefully degrades without the extra.
3. **413 → `dspy.ContextWindowExceededError`** mapping so DSPy retry/truncation engages. Other HTTP errors propagate as `RuntimeError`.
4. **Asyncio nested-loop detection** : `forward()` (sync, per DSPy 3.2 BaseLM contract) inspects `asyncio.get_running_loop()` and raises `RuntimeError` if called from inside an event loop. Prevents opaque "This event loop is already running" stack traces from deep inside `asyncio.run()`.

**Future consumer** : W117b GEPA optimizer (deferred next session ; requires ADR-088+ for prompt-mutation contract, ADR-017 regex fitness penalty, and rate-limit discipline).

## CI / pre-commit invariants

Tests added in `apps/api/tests/test_invariants_ichor.py` :

- `test_no_anthropic_sdk_import` — scans `apps/api/src` + `packages/` for `^import anthropic` or `^from anthropic`. PASS = zero matches.
- `test_no_dspy_lm_with_claude_model_tag` — scans for `dspy\.LM\(.*model.*=.*['"]claude` literal. PASS = zero matches.
- `test_dspy_claude_runner_lm_sentinel_namespace` — asserts `_ALLOWED_MODEL_TAGS` is a frozenset and contains only `ichor-claude-runner-*` entries.
- `test_addendum_generator_has_adr017_regex` — asserts `_BANNED_TOKENS` is defined in `services/addendum_generator.py` and `_validate_no_signals` is called before persistence write.
- `test_auto_improvement_log_immutable_trigger` — runs migration 0042 against a sandbox session and asserts UPDATE/DELETE raise.

All run on pre-commit hook `ichor-invariants` (W91) AND on CI (W90).

## Empirical proof obligations (rule 18 "marche exactement pas juste fonctionne")

Every Phase D loop **MUST** ship with three independent witnesses :

| Witness                                 | Where to find it                                                                                                                       |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| **Migration LIVE**                      | `ssh ichor-hetzner "sudo -u postgres psql ichor -tAc 'SELECT version_num FROM alembic_version;'"`                                      |
| **Cron armed OR fired**                 | `ssh ichor-hetzner "systemctl list-timers --no-pager                                                                                   | grep <unit>.timer"` |
| **DB row count** OR **journalctl exec** | `ssh ichor-hetzner "sudo -u postgres psql ichor -tAc 'SELECT count(*) FROM <table>;'"` OR `journalctl -u <unit>.service --since '...'` |

The W115b autonomous Vovk fire 2026-05-13 03:32:39 CEST is the gold-standard proof : all three witnesses converge (migration 0043 LIVE + `journalctl` exec + 16 audit rows + 24 weight rows + `/v1/phase-d/aggregator-weights` returns evolved pockets).

## Observability — `/v1/phase-d/*` endpoints

A new FastAPI router `apps/api/src/ichor_api/routers/phase_d.py` exposes read-only diagnostics :

| Endpoint                         | Purpose                                                                                      |
| -------------------------------- | -------------------------------------------------------------------------------------------- |
| `/v1/phase-d/audit-log`          | Paged `auto_improvement_log` slice (filter by `loop_kind`, `since_days`, `asset`, `regime`). |
| `/v1/phase-d/aggregator-weights` | Vovk pocket dump (all `(asset, regime, session_type)` × experts).                            |
| `/v1/phase-d/pass3-addenda`      | Score-ordered addenda store.                                                                 |
| `/v1/phase-d/pocket-summary`     | Top-K aggregator + last-N audit + flag states (one-shot health check).                       |

These endpoints are excluded from W88 AI watermark middleware (no LLM-derived response payload). Frontend `/learn` consumer is intentionally gel'd per rule 4 ; Eliot consumes via `curl` from dev box meanwhile.

## Hetzner deploy convention (rule 19 reversible <30s)

Every Phase D single-file deploy uses the canonical scp+SSH chain :

```bash
# 1. Backup BEFORE overwrite
ssh ichor-hetzner "sudo cp /opt/ichor/apps/api/src/ichor_api/services/<file> /opt/ichor/apps/api/src/ichor_api/services/<file>.bak"

# 2. Upload to /tmp (writable for SSH user)
scp <local-file> ichor-hetzner:/tmp/<filename>

# 3. Copy + chown + restart + smoke
ssh ichor-hetzner "sudo cp /tmp/<filename> /opt/ichor/apps/api/src/ichor_api/services/<filename> && \
                   sudo chown root:root /opt/ichor/apps/api/src/ichor_api/services/<filename> && \
                   sudo systemctl restart <unit>.service && \
                   sudo journalctl -u <unit>.service --since '10 seconds ago' --no-pager | tail -30"

# Rollback (≤30s) if smoke fails :
ssh ichor-hetzner "sudo cp /opt/ichor/apps/api/src/ichor_api/services/<file>.bak /opt/ichor/apps/api/src/ichor_api/services/<file> && sudo systemctl restart <unit>.service"
```

## Consequences

### Positive

- **Audit-trail complete** : every Phase D fire is one immutable row, ADR-029-class. Compliance with EU AI Act §50.2 + AMF DOC-2008-23 criterion 4 (méthodologie & calibration).
- **Provable regret bound** on the aggregator : Vovk-Zhdanov 2009 Theorem 1 says `Regret_T ≤ ln(N) = ln(3) ≈ 1.10` constant in T. Better than any no-regret online learner (e.g., Hedge `O(√T ln N)`).
- **Zero Anthropic API spend** : the W117a DSPy wrapper makes future DSPy work (W117b GEPA, future prompt-tuners) automatically Voie D-bound. Foundation invariant.
- **Self-healing skill diagnostics** : EUR_USD anti-skill discovered automatically by Vovk after just n=13 observations. Without this loop, the systematic miscalibration would have been invisible until manual post-mortem (which historically happens ~once/quarter).
- **No frontend coupling** : `/v1/phase-d/*` endpoints exist but consumer is gel'd ; the back-end can evolve independently of the UI surface.

### Negative

- **W116c LLM addendum generator increases Voie D surface area** : one more cron that calls `claude -p` weekly. Even Sunday 19:00 single-shot, it adds load to Win11 NSSM runner. Mitigation : the cron is feature-flag-gated (currently OFF), so adoption is gradual and observable.
- **W115c read-side NOT YET implemented** : Vovk weights are stored but not yet consumed by the 4-pass orchestrator. Phase D loop is open (measure ✓ act ✗). ADR-088 PROPOSED closes this gap.
- **Pre-existing fragility surfaces** : EUR_USD/usd_complacency anti-skill is structural (no data-pool EUR-specific section, no EZ input in Pass-1 régime taxonomy). Discovered by W115 Vovk autonomously ; fix tracked in ADR-090 PROPOSED.
- **Hetzner timer cadence assumption** : Sunday 03:30 + 18:00 + 19:00 spacing relies on no other LLM-calling cron landing on Sunday. New crons MUST respect ≥5 min spacing OR be explicitly batched.

### Neutral

- **DSPy 3.2 dependency** is optional extra (`[phase-d-w117]`). CI without the extra still passes ; production environment installs the extra explicitly. No transitive `anthropic` SDK pull-in (verified via `pip download --no-deps`).

## Future work

- **W117b GEPA optimizer wiring** — uses W117a foundation. Estimated 3 dev-days. Needs new ADR with prompt-mutation contract + ADR-017 regex fitness penalty.
- **W115c confluence_engine pocket-read** — ADR-088 PROPOSED. Estimated 0.5 dev-days.
- **Vovk Bayesian shrinkage** — Dirichlet prior n_pseudo=10 toward uniform. Improves small-sample (n<30) interpretation of weight deltas without changing AA math. Future audit gap, ~1 dev-day.
- **Server-side LLM tools (`web_search`/`web_fetch`)** remain EXCLUDED per ADR-071 — they bill separately from Max plan, violating Voie D.
