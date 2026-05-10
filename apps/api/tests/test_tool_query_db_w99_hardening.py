"""W99 — regression tests for the post-code-review hardening of
`tool_query_db.validate_query`. Each test pins a CRITICAL issue
identified by the code-reviewer subagent.

Issues addressed :
  1. `pg_sleep()` / function-call DoS bypassed the table-only whitelist.
  2. `SELECT ... FOR UPDATE / FOR SHARE` lifted row-level locks
     incompatible with the read-only contract.
  3. CTE alias-shadowing on a forbidden table (defense in depth).
"""

from __future__ import annotations

import pytest
from ichor_api.services.tool_query_db import (
    _FORBIDDEN_FUNCTIONS,
    ALLOWED_TABLES,
    validate_query,
)

# ────────────────────────── Issue #1 — function DoS ──────────────────────────


@pytest.mark.parametrize(
    "fn",
    [
        "pg_sleep",
        "pg_advisory_lock",
        "pg_try_advisory_lock",
        "lo_import",
        "lo_export",
        "dblink",
        "copy_from_program",
        "pg_read_file",
    ],
)
def test_forbidden_function_call_rejected(fn: str) -> None:
    """W99 — every entry in `_FORBIDDEN_FUNCTIONS` must be rejected
    even when the table referenced is on the allowlist."""
    table = next(iter(ALLOWED_TABLES))
    sql = f"SELECT {fn}(1) FROM {table} LIMIT 1"
    res = validate_query(sql)
    assert res.ok is False
    assert "forbidden function" in res.reason
    assert fn in res.reason


def test_pg_sleep_in_subquery_rejected() -> None:
    """Subquery embedding of pg_sleep must also be caught by the AST walk."""
    sql = "SELECT id FROM alerts WHERE id IN (  SELECT pg_sleep(60) FROM fred_observations LIMIT 1)"
    res = validate_query(sql)
    assert res.ok is False
    assert "pg_sleep" in res.reason


def test_pg_advisory_lock_inside_cte_rejected() -> None:
    """CTE-wrapped advisory lock must be caught."""
    sql = "WITH locked AS (SELECT pg_advisory_lock(1) FROM alerts) SELECT * FROM locked"
    res = validate_query(sql)
    assert res.ok is False
    # Either the function check fires first, or the CTE alias
    # shadowing falls through to a different rejection — both OK.
    assert "pg_advisory_lock" in res.reason or "forbidden table" in res.reason


def test_forbidden_functions_list_is_non_empty() -> None:
    """Sanity guard : the constant must contain at least the canonical
    DoS / lock / IO entries. Catches accidental wholesale deletion."""
    canonical = {
        "pg_sleep",
        "pg_advisory_lock",
        "lo_import",
        "lo_export",
        "dblink",
        "copy_from_program",
    }
    assert canonical <= _FORBIDDEN_FUNCTIONS


# ────────────────────────── Issue #2 — row-level locks ──────────────────────────


@pytest.mark.parametrize(
    "lock_clause",
    [
        "FOR UPDATE",
        "FOR SHARE",
        "FOR NO KEY UPDATE",
        "FOR KEY SHARE",
        "FOR UPDATE OF alerts",
        "FOR UPDATE NOWAIT",
        "FOR UPDATE SKIP LOCKED",
    ],
)
def test_row_lock_clause_rejected(lock_clause: str) -> None:
    """W99 — every variant of `FOR UPDATE / FOR SHARE / ...` must be
    rejected. They lift row-level locks incompatible with read-only."""
    sql = f"SELECT id FROM alerts {lock_clause}"
    res = validate_query(sql)
    assert res.ok is False
    assert "lock" in res.reason.lower()


def test_lock_in_subquery_rejected() -> None:
    """Subquery FOR UPDATE also rejected."""
    sql = "SELECT * FROM (  SELECT id FROM alerts FOR UPDATE) AS sub LIMIT 1"
    res = validate_query(sql)
    assert res.ok is False
    assert "lock" in res.reason.lower()


def test_no_lock_clause_passes() -> None:
    """Sanity — the cleanest possible SELECT must still pass (no false
    positives from the new lock check)."""
    sql = "SELECT id FROM alerts LIMIT 5"
    res = validate_query(sql)
    assert res.ok is True


# ────────────────────────── Issue #3 — CTE alias shadowing ──────────────────────────


def test_cte_alias_shadowing_forbidden_table_caught() -> None:
    """W99 — `WITH alerts AS (SELECT * FROM trader_notes) SELECT * FROM
    alerts` should still be rejected because the WALK reaches the inner
    `trader_notes` Table node BEFORE the alias is registered. The 2nd
    pass that excludes CTE aliases doesn't apply to the inner walk."""
    sql = "WITH alerts AS (SELECT * FROM trader_notes) SELECT * FROM alerts"
    res = validate_query(sql)
    assert res.ok is False
    # Reject because trader_notes is forbidden ; the alias `alerts`
    # shadowing the real `alerts` table doesn't help the attacker.
    assert "trader_notes" in res.reason or "forbidden table" in res.reason


def test_cte_alias_legitimate_passes() -> None:
    """Counter-test — a legitimate CTE that wraps an allowed table
    must pass without being blocked by the new defenses."""
    sql = "WITH recent AS (SELECT * FROM fred_observations LIMIT 100) SELECT * FROM recent"
    res = validate_query(sql)
    assert res.ok is True


# ────────────────────────── No regression on benign queries ──────────────────────────


def test_basic_select_still_works() -> None:
    """W99 hardening must not break the canonical pattern."""
    sql = "SELECT * FROM alerts ORDER BY ts DESC LIMIT 10"
    res = validate_query(sql)
    assert res.ok is True


def test_join_across_allowed_tables_still_works() -> None:
    """Multi-table joins on the allowlist must still pass."""
    sql = "SELECT a.id, f.value FROM alerts a JOIN fred_observations f ON a.id = f.id LIMIT 5"
    res = validate_query(sql)
    assert res.ok is True


def test_aggregate_function_still_works() -> None:
    """COUNT/MAX/MIN must not be in the forbidden set (they're builtin
    aggregates, not anonymous calls). Sanity guard."""
    sql = "SELECT COUNT(*), MAX(ts) FROM alerts"
    res = validate_query(sql)
    assert res.ok is True
