# ADR-081: Doctrinal invariant CI guards

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes**: none
- **Related**: ADR-009 (Voie D), ADR-017 (Living Macro Entity boundary —
  no BUY/SELL signals), ADR-021 (Couche-2 via Claude not fallback),
  ADR-023 (Couche-2 Haiku low not Sonnet), ADR-028 (Wave 5 CI strategy
  incremental), ADR-029 (EU AI Act §50 + AMF DOC-2008-23 + audit_log
  immutable), ADR-031 (SessionType single source via get_args),
  ADR-077 (Cap5 STEP-3 MCP wire — tool_call_audit trigger), ADR-078
  (Cap5 query_db excludes trader_notes — already CI-guarded W87),
  ADR-079 (EU AI Act §50.2 watermark middleware), ADR-080 (disclosure
  surface contract)

## Context

Ichor accumulates a stack of doctrinal invariants — boundary contracts,
compliance requirements, architectural constraints — that today live as
prose in ADRs, sentences in CLAUDE.md, and human muscle memory. Examples :

- ADR-017 : "No BUY/SELL signals anywhere. Grep `BUY|SELL` returns
  only docstrings of boundary, persona, or `/learn` pages." — but no
  CI gate enforces it.
- ADR-009 Voie D : "Production routes via the local Win11 claude-runner
  subprocess (Max 20x flat). Never add `anthropic` python SDK." — no
  CI gate.
- ADR-023 : "Couche-2 lives on Claude Haiku low. Sonnet medium hits the
  Cloudflare Free 100 s edge timeout." — no CI gate ; the wiring is in
  `packages/agents/src/ichor_agents/claude_runner.py` but a refactor
  could quietly switch the default back to Sonnet.

The codebase is now 80+ services, 47 CLI runners, 35 routers, 5
Couche-2 agents, 44 collectors. With the open-ended "add a new alert"
pattern (ADRs 033-052 added 17 alerts in 2 days), drift risk grows
exponentially. Code review alone cannot scale.

W83 added one CI guard test (sqlglot allowlist for `query_db`). W87
added another (ADR-078 forbidden_set). W90 generalises this discipline
to **the most consequential invariants**.

## Decision

Ratify a single test module **`apps/api/tests/test_invariants_ichor.py`**
that mechanises the high-impact doctrinal invariants. Each invariant
gets one test (or two : forbidden + positive). Adding a new invariant
to the surface = extending this file + extending the table below in
this ADR.

### Tracked invariants (W90 initial set)

| # | ADR             | Test name                                                | What it catches |
| - | --------------- | -------------------------------------------------------- | --------------- |
| 1 | ADR-017         | `test_no_buy_sell_in_python_code_tokens`                 | `BUY` / `SELL` appearing as Python identifiers, attributes, dict keys (not in strings/comments). Catches `BIAS = "BUY"` constant, `signals.append(BUY)` import, etc. |
| 2 | ADR-009         | `test_no_anthropic_sdk_imports`                          | `import anthropic` or `from anthropic import …` in production code (Voie D Max 20x mandates subprocess only). |
| 3 | ADR-023         | `test_couche2_agents_do_not_default_to_sonnet`           | `"sonnet"` literals in `packages/agents/src/ichor_agents/agents/*.py` outside historical-context comments. |
| 4 | ADR-023         | `test_couche2_agents_reference_haiku`                    | Positive guard — at least one Couche-2 agent file references `"haiku"`, catches accidental wholesale deletion. |
| 5 | ADR-029         | `test_audit_log_immutable_trigger_present`               | Migration 0028 still defines `BEFORE UPDATE OR DELETE` + `RAISE EXCEPTION` + sanctioned-purge GUC. |
| 6 | ADR-077 / PRE-2 | `test_tool_call_audit_immutable_trigger_present`         | Migration 0038 mirrors the audit_log pattern (Capability 5 audit chain). |
| 7 | ADR-079 / 080   | `test_ai_watermark_default_prefixes_match_settings`      | `AIWatermarkMiddleware.DEFAULT_WATERMARKED_PREFIXES` agrees with `Settings.ai_watermarked_route_prefixes`. Single-source-of-truth alignment ; catches drift where one is updated without the other. |

### Tracked invariants — already CI-guarded elsewhere (cross-reference)

| ADR     | Test name (existing)                                            | File |
| ------- | --------------------------------------------------------------- | ---- |
| ADR-077 (sqlglot whitelist) | `test_tool_query_db_select_only` etc (29 tests)                  | `apps/api/tests/test_tool_query_db.py` |
| ADR-078 (forbidden set)     | `test_forbidden_set_disjoint_from_allowlist` etc (4 tests)       | `apps/api/tests/test_tool_query_db_allowlist_guard.py` |
| ADR-079 (watermark headers) | `test_watermark_present_on_llm_route` etc (10 tests)             | `apps/api/tests/test_ai_watermark_middleware.py` |
| ADR-080 (well-known)        | `test_inventory_*` (7 tests)                                     | `apps/api/tests/test_well_known_ai_content.py` |
| ADR-031 (SessionType)       | `test_session_type_literal_matches_valid_session_types`          | `packages/ichor_brain/tests/test_types.py` (predates ADR-031) |
| ADR-076 (MOCK_* fallback)   | none — informal pattern, not yet codified                        | (W92 candidate) |

### Tracked invariants — NOT yet codified (W92+ candidates)

- **ADR-026 / ADR-027** WCAG 2.2 AA — currently checked by axe-core
  Playwright run, not a unit test. Acceptable (axe is the right tool).
- **ADR-076** Frontend `MOCK_*` graceful fallback pattern — could be
  codified as a TS-level lint rule that requires `MOCK_*` constants
  to be guarded by `isLive(...)` ternaries. Out of scope.
- **Cap conviction 95 %** — ADR-017 caps `conviction_pct` at 95.
  Today enforced by Pydantic `Field(ge=0.0, le=95.0)` in
  `packages/ichor_brain/types.py`. No CI guard against accidental
  loosening. Could add a test that imports the field and asserts
  the upper bound. W92 candidate.
- **`/v1/tools/*` exclusion from watermark** — ADR-079 + ADR-080 intentionally
  exclude tool routes (data-only return shape). No test enforces this.
  W92 candidate.
- **Cron register canonical clauses** (ADR-030) — already shell-lint-guarded
  by `.github/workflows/ci.yml` shellcheck job. Acceptable.

### Test design philosophy

1. **One module, many tests** — `test_invariants_ichor.py` is the
   canonical home. Avoid sprawl.
2. **Tokenise, don't grep** — Python `tokenize` distinguishes code
   tokens from STRING and COMMENT tokens. `BUY` in a docstring is the
   description of the boundary itself ; `BUY` as an identifier is a
   regression. The test must NOT flag the description of the
   invariant in the codebase.
3. **Skip rather than fail when prerequisites missing** — if a venv
   is missing a package (e.g. `ichor_agents`), `pytest.skip()` with
   the missing-prereq reason. Don't fail the build for environmental
   reasons.
4. **Allowed-exception lists are explicit, not implicit** — when
   the BUY/SELL test will eventually accept a specific file (e.g.
   a future archived persona), that file goes in a named whitelist
   visible in code review.
5. **Tests are fast** — under 5 seconds total for the whole module.
   They run on every CI invocation + every developer pre-commit
   (when pre-commit is wired in W91+).

### Failure mode handling

When a test fails, the message must explain :
- Which invariant is violated (ADR number).
- Where the violation is (file path + line number).
- What the developer should do (e.g. "use `claude -p` subprocess
  only", "move the `BUY` literal to a docstring").

The `assert` messages in the W90 implementation follow this
template.

## Consequences

### Positive

- The most consequential invariants of the project (BUY/SELL
  boundary, Voie D, audit immutability, watermark alignment) are now
  mechanically enforced. Drift becomes a CI failure, not a silent
  production bug.
- Developer onboarding cost drops : reading the test file is faster
  than reading the underlying ADRs.
- Cross-ADR consistency check (ADR-079 / ADR-080 single-source-of-
  truth) catches a class of bug that human review struggles with
  (two files separately updated by different waves).

### Accepted

- Some invariants are inherently hard to mechanise (e.g. "the
  prompt persona MUST be in French" — could check character class,
  but locale-sensitive). Those stay as ADR prose for now.
- The test file is **trusted code** — a malicious / careless
  developer could weaken a test (e.g. expand the allowed-marker
  list to swallow real violations). Mitigation : changes to
  `test_invariants_ichor.py` MUST be reviewed against the
  corresponding ADR. ADR-081 itself documents the canonical set
  so reviewers have a reference.
- Tokenisation has edge cases : Python f-strings, `__future__`
  imports, `# type: ignore` markers etc. Implementation chose
  conservative behaviour (skip suspect tokens, fail explicitly
  on tokenize errors). Rare false negatives are acceptable since
  the invariants are double-checked at code review time.

### Required follow-ups

- **W91 candidate** — wire `apps/api/tests/test_invariants_ichor.py`
  into the pre-commit configuration so violations are caught
  locally before push.
- **W92 candidate** — extend the tracked set with the items in
  the "NOT yet codified" table above (ADR-076 fallback, conviction
  95 cap, `/v1/tools/*` watermark exclusion).
- **Long-term** — when a new ADR ratifies a new invariant, the ADR
  body must mention "CI-guarded by `test_<name>` in
  `test_invariants_ichor.py`" or "INFORMAL — CI guard pending W?".
  Reviewer's checklist.

## Implementation references

- `apps/api/tests/test_invariants_ichor.py` — 7 tests, ~250 lines.
- `apps/api/migrations/versions/0028_audit_log_immutable_trigger.py`
  — referenced by `test_audit_log_immutable_trigger_present`.
- `apps/api/migrations/versions/0038_tool_call_audit.py` —
  referenced by `test_tool_call_audit_immutable_trigger_present`.
- `apps/api/src/ichor_api/middleware/ai_watermark.py` — referenced
  by `test_ai_watermark_default_prefixes_match_settings`.
- `apps/api/src/ichor_api/services/tool_query_db.py` — already
  CI-guarded by `test_tool_query_db_allowlist_guard.py` (W87,
  ADR-078).

## References

- ADR-009, ADR-017, ADR-021, ADR-023, ADR-028, ADR-029, ADR-031,
  ADR-076, ADR-077, ADR-078, ADR-079, ADR-080.
