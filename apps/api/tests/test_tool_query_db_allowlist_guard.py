"""ADR-078 CI guard — `query_db` allowlist must exclude the forbidden set.

The forbidden set is defined in
`docs/decisions/ADR-078-cap5-query-db-excludes-trader-notes.md` :

    {trader_notes, audit_log, tool_call_audit, feature_flags}

Each table is excluded for an explicit reason :
  - trader_notes     : privacy + ADR-017 boundary + ML hygiene + AMF
                       DOC-2008-23 criterion 3 (personnalisation).
  - audit_log        : immutable MiFID trail (ADR-029, migration 0028).
  - tool_call_audit  : immutable Cap5 audit (ADR-077, migration 0038).
                       Self-referential — query_db reading the audit
                       of query_db invites recursion attacks.
  - feature_flags    : kill-switch surface — orchestrator must remain
                       blind to its own gates.

Widening `ALLOWED_TABLES` to include any of these tables is a
contractual regression that must go through a successor ADR
explicitly superseding ADR-078 (see "Future-revisit clause" in the
ADR for the four cumulative conditions).

This test fails the build if the invariant breaks.
"""

from __future__ import annotations

from ichor_api.services.tool_query_db import ALLOWED_TABLES

# Single source of truth for the forbidden set. Update this list ONLY
# when a successor ADR explicitly authorises one of these tables (and
# meets the four cumulative conditions in ADR-078 §"Future-revisit").
FORBIDDEN_SET: frozenset[str] = frozenset(
    {
        "trader_notes",
        "audit_log",
        "tool_call_audit",
        "feature_flags",
        # ADR-088 (W115c, round-28) Invariant 3 : Vovk pocket weights
        # are read ONLY through `services/pocket_skill_reader.py` which
        # applies hysteresis + small-sample shielding + feature-flag
        # gate. Couche-2 agents MUST NOT bypass via raw SQL.
        "brier_aggregator_weights",
        # ADR-087 Loop 1 : audit log is immutable (ADR-029-class). No
        # Cap5 read path — query_db consumers must not see audit rows.
        "auto_improvement_log",
        # ADR-087 Loop 4 : addenda are render-only via the injector. The
        # raw table holds candidate prompts the LLM hasn't seen yet.
        "pass3_addenda",
        # ADR-091 W117b sub-wave .b (round-32) : GEPA candidate prompts
        # are un-vetted LLM outputs pre-adoption. Couche-2 agents MUST
        # remain blind to the candidate pool ; only adopted prompts
        # are loaded by the orchestrator at startup via a code path
        # that does NOT touch Cap5 query_db.
        "gepa_candidate_prompts",
    }
)


def test_forbidden_set_disjoint_from_allowlist() -> None:
    """ADR-078 invariant : `ALLOWED_TABLES & FORBIDDEN_SET == ∅`."""
    overlap = ALLOWED_TABLES & FORBIDDEN_SET
    assert overlap == frozenset(), (
        f"ADR-078 violated : query_db ALLOWED_TABLES leaks forbidden tables {sorted(overlap)}. "
        f"Adding one of these tables requires a successor ADR per ADR-078 §Future-revisit."
    )


def test_forbidden_set_each_member_blocked() -> None:
    """Belt-and-suspenders : check each forbidden table individually
    so the failure message names the offending table."""
    for tbl in sorted(FORBIDDEN_SET):
        assert tbl not in ALLOWED_TABLES, (
            f"ADR-078 violated : forbidden table {tbl!r} leaked into query_db ALLOWED_TABLES. "
            f"This table is excluded by construction (see ADR-078 §Forbidden set)."
        )


def test_canonical_allowlist_size_unchanged() -> None:
    """Size guard — ADR-077 + ADR-078 fix the surface at exactly 6
    tables. Adding a 7th MUST go through an ADR (regression detector
    for accidental widening via copy-paste from another module).
    """
    assert len(ALLOWED_TABLES) == 6, (
        f"ALLOWED_TABLES has {len(ALLOWED_TABLES)} entries (expected 6 per "
        f"ADR-077 / ADR-078). Adding a 7th table requires a successor ADR."
    )


def test_canonical_allowlist_contents() -> None:
    """Spell out the canonical 6 — protects against silent rename."""
    expected = frozenset(
        {
            "session_card_audit",
            "fred_observations",
            "gdelt_events",
            "gpr_observations",
            "cb_speeches",
            "alerts",
        }
    )
    assert ALLOWED_TABLES == expected, (
        f"ALLOWED_TABLES drift : got {sorted(ALLOWED_TABLES)}, expected {sorted(expected)}. "
        f"Renaming or replacing a canonical table requires an ADR + migration plan."
    )
