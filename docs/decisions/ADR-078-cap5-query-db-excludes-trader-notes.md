# ADR-078: Capability 5 `query_db` allowlist excludes `trader_notes`

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes**: none
- **Related**: ADR-009 (Voie D — no Anthropic SDK consumption), ADR-017
  (Living Macro Entity boundary — never trade signals), ADR-029 (EU AI
  Act §50 + AMF DOC-2008-23 disclosure surface), ADR-050 (Capability 5
  registry scaffold), ADR-071 (Capability 5 deferral, 6-step sequence),
  ADR-077 (Capability 5 STEP-3 — MCP server wire to `/v1/tools/*`)

## Context

Migration `0029_trader_notes.py:5-6` defines `trader_notes` as
**Eliot's private journal**, with the explicit doctrinal note :

> "Explicitly OUT of ADR-017 boundary surface — it's Eliot's notebook,
> never fed back to ML/Brier/Pass-1..5."

The table holds free-form annotations (`body TEXT`, `asset` optional
tag, `ts` author timestamp). It is rendered only by the `/journal`
route in `apps/web2`, never read by the 4-pass orchestrator, never by
Couche-2 agents, never by the Brier optimizer, never by the
counterfactual loop.

ADR-077 (just merged on `main`, commit `2f3fe1e`) wires Capability 5
STEP-3 : the Win11 MCP server forwards `query_db` invocations to
`apps/api /v1/tools/query_db`, where `services/tool_query_db.py`
enforces a 6-table sqlglot AST whitelist :

```
ALLOWED_TABLES = frozenset({
    "session_card_audit",
    "fred_observations",
    "gdelt_events",
    "gpr_observations",
    "cb_speeches",
    "alerts",
})
```

`trader_notes` is **not** in this set. ADR-077 §"Tools registered"
described the 6 tables as the canonical surface but did not codify
*why* `trader_notes` (and `audit_log`, `tool_call_audit`,
`feature_flags`) are excluded. This ADR closes that gap and makes
the exclusion an invariant — any future widening must go through a
new ADR that explicitly supersedes this one.

## Decision

`trader_notes` is **permanently excluded** from the Capability 5
`query_db` allowlist. The 4-pass orchestrator and the Couche-2
agents must never read it through any tool surface. The
`apps/web2 /journal` route remains the only consumer.

The same exclusion applies, by the same reasoning class, to :
`audit_log`, `tool_call_audit`, `feature_flags`. Together they form
the **forbidden set** that a CI guard test enforces against
`ALLOWED_TABLES`.

## Why `trader_notes` must stay out

### 1. Privacy — operator notes, not analytical input

The journal entries capture Eliot's discretionary thinking : doubts,
tilt notes, post-trade self-criticism, off-system context. These
have never been validated as analytical signal and are not intended
to be. Surfacing them to Claude through `query_db` would be a
unilateral repurposing of personal text.

### 2. ADR-017 boundary — notebook is not surface

ADR-017 fixes the Living Macro Entity output surface : probability
distributions, bias direction, calibrated cards. The notebook sits
**below** the boundary by deliberate construction (cf migration
0029 docstring). Letting Pass-1..5 read it pulls operator commentary
**onto** the surface. That is exactly the contamination ADR-017
forbids.

### 3. Anti-feedback-loop (ML hygiene)

Pass-3 (stress) and Pass-5 (counterfactual) plus the Brier optimizer
write back into `session_card_audit` and bias-trainer datasets. If
`query_db` exposed `trader_notes`, Pass-1..5 reasoning could
incorporate Eliot's prior verdicts and create a hidden self-reference
loop. Brier calibration would no longer measure independent forecast
quality — it would measure "how well does Claude echo Eliot's own
notes". This is the textbook leakage failure mode.

### 4. AMF DOC-2008-23 — personalisation criterion 3

DOC-2008-23 vf4_3 (fév 2024) lists 5 cumulative criteria for
investment advice. Criterion 3 — **"présentée comme adaptée à la
situation particulière du client"** — is currently NOT met because
Ichor produces generic non-personalised macro analysis (cf ADR-029).

`trader_notes` is **the formal record of Eliot's particular
situation** : holdings, tilt, conviction, recent regret. Feeding
this corpus into the bias-card pipeline would produce output
mathematically conditioned on Eliot's personal state. That flips
criterion 3 from "non personnalisé" to "personnalisé", and combined
with the existing 4 conditions could push the system across the
advice boundary.

The legal default position is therefore **exclusion-by-construction**,
not "we'll filter at prompt time". Filtering can fail silently;
exclusion at the SQL allowlist cannot.

### 5. Voie D adjacency (ADR-009)

Voie D forbids Anthropic SDK-billed surface. While `trader_notes`
exclusion is not directly a Voie D concern, the same conservatism
applies : every byte that crosses into the Claude prompt is a byte
we have to defend in audit. Operator notes have no Brier-validated
upside that justifies that audit cost.

## Forbidden set (CI guard target)

The CI test (W87 to ship) walks `ALLOWED_TABLES` and asserts that
none of the following appear :

| Table              | Reason for exclusion                                       |
| ------------------ | ---------------------------------------------------------- |
| `trader_notes`     | This ADR (privacy + ADR-017 + ML hygiene + AMF crit. 3).   |
| `audit_log`        | Immutable MiFID trail (ADR-029, migration 0028 trigger). Not a research surface — chain-of-custody only. Reading it through `query_db` would create observable side channels. |
| `tool_call_audit`  | Same family as `audit_log` (migration 0038 trigger, ADR-077 §"Audit row shape"). Self-referential : `query_db` reading the audit of `query_db` invites recursion attacks. |
| `feature_flags`    | Kill-switch surface (cross-worker invalidation). Letting the orchestrator read its own flag state is a control-plane leak ; the orchestrator must remain blind to its own gates. |

## Consequences

### Positive

- Privacy invariant locked at the SQL layer, not at prompt
  engineering. No silent regression possible.
- ADR-017 boundary stays mechanically enforced — adding a new
  forbidden table only requires a one-line `forbidden_set` update.
- AMF DOC-2008-23 personalisation criterion 3 stays unchecked. The
  legal posture documented in ADR-029 stays defensible.
- ML feedback hygiene preserved : no path from operator commentary
  into Brier-validated bias datasets.

### Accepted

- The 4-pass orchestrator cannot quote operator commentary even when
  it would be useful (e.g. "Eliot flagged AUDUSD retail crowding two
  weeks ago"). Workaround : surface signals via dedicated structured
  collectors (Myfxbook outlooks, ADR-074), not via journal scrape.
- A hypothetical future "context summariser" feature that re-uses
  notes will need a new ADR that explicitly supersedes this one,
  declares the personalisation switch-on, and updates the AMF
  surface text accordingly.

### Required follow-ups

- **CI guard test** — `apps/api/tests/test_tool_query_db_allowlist_guard.py`
  asserts `forbidden_set & ALLOWED_TABLES == set()` for the four
  tables above. Fails the build if anyone widens the allowlist by
  oversight.
- **Frontend disclosure** — append a one-line clause to `LegalFooter`
  (`apps/web2/components/ui/legal-footer.tsx`) :

  > "Le journal opérateur (`/journal`) reste hors du périmètre
  > analytique : ses entrées ne sont jamais lues par les passes 1 à
  > 5 ni par les agents Couche-2 (cf. ADR-078)."

  This makes the privacy invariant visible to any future reader of
  the surface, in line with the EU AI Act §50 transparency posture
  ratified in ADR-029.
- **No code change** to `services/tool_query_db.py` — the file
  already implements the invariant. This ADR codifies what the code
  enforces, so a future reader cannot widen the allowlist without
  facing both the CI test and an ADR supersession.

### Future-revisit clause

A successor ADR may grant `trader_notes` read access if **all** of
the following hold :

1. Eliot signs off explicitly in the successor ADR (not implicit).
2. AMF DOC-2008-23 surface text is updated to acknowledge the
   personalisation flip, or a legal note documents why the flip
   does not occur.
3. A pass-level filter exists upstream of Brier ingestion to
   prevent feedback contamination.
4. The successor ADR declares whether Capability 5 server tools
   (`web_search`, `web_fetch`) are still excluded — those remain
   independently barred by ADR-071 §"client tools only".

Without all four, the exclusion stands.

## References

- `apps/api/src/ichor_api/services/tool_query_db.py` — `ALLOWED_TABLES`
  canonical 6-table whitelist.
- `apps/api/migrations/versions/0029_trader_notes.py:5-6` —
  doctrinal note "OUT of ADR-017 boundary surface".
- `apps/api/migrations/versions/0028_audit_log_immutable_trigger.py` —
  `audit_log` immutable trigger (referenced by forbidden set).
- `apps/api/migrations/versions/0038_tool_call_audit.py` —
  `tool_call_audit` immutable trigger (referenced by forbidden set).
- `apps/web2/components/ui/legal-footer.tsx` — surface disclosure
  target.
- ADR-009 — Voie D constraints.
- ADR-017 — Living Macro Entity boundary contractual.
- ADR-029 — EU AI Act §50 + AMF DOC-2008-23 disclosure footer.
- ADR-050 — Capability 5 registry scaffold.
- ADR-071 — Capability 5 deferral, 6-step sequence ; this ADR
  refines STEP-1's allowlist scope.
- ADR-077 — Capability 5 STEP-3 MCP server wire (commit `2f3fe1e`).
