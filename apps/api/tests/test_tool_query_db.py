"""Unit tests for the query_db tool handler (Capability 5 STEP-1).

Pure-validator tests; no DB connection required. Validates the
sqlglot-AST whitelist enforcement against:
  - well-formed allowlist queries (must pass)
  - DML/DDL injection attempts (must reject)
  - schema-qualified table sneaks (information_schema, pg_catalog)
  - multi-statement payloads
  - subquery + CTE table extraction
  - UNION / INTERSECT / EXCEPT branches
  - allowlist drift guards (NOT in allowlist → reject)
"""

from __future__ import annotations

import pytest
from ichor_api.services.tool_query_db import (
    ALLOWED_TABLES,
    DEFAULT_MAX_ROWS,
    HARD_MAX_ROWS,
    _clamp_max_rows,
    validate_query,
)

# ── Positive: queries that must pass validation ──────────────────


def test_simple_select_allowlist_passes() -> None:
    res = validate_query("SELECT * FROM session_card_audit LIMIT 10")
    assert res.ok, res.reason
    assert "session_card_audit" in res.tables_referenced


def test_select_with_where_passes() -> None:
    res = validate_query(
        "SELECT id, asset, conviction FROM session_card_audit "
        "WHERE conviction > 0.7 ORDER BY ran_at DESC LIMIT 100"
    )
    assert res.ok, res.reason


def test_join_two_allowlisted_tables_passes() -> None:
    res = validate_query(
        "SELECT s.asset, c.title FROM session_card_audit s "
        "JOIN cb_speeches c ON c.published_at < s.ran_at "
        "LIMIT 50"
    )
    assert res.ok, res.reason
    assert "session_card_audit" in res.tables_referenced
    assert "cb_speeches" in res.tables_referenced


def test_cte_with_allowlisted_table_passes() -> None:
    res = validate_query(
        "WITH recent AS (SELECT * FROM fred_observations WHERE observation_date > '2026-01-01') "
        "SELECT series_id, COUNT(*) FROM recent GROUP BY series_id"
    )
    assert res.ok, res.reason
    assert "fred_observations" in res.tables_referenced


def test_union_allowlisted_branches_passes() -> None:
    res = validate_query("SELECT id FROM alerts UNION SELECT id FROM gpr_observations")
    assert res.ok, res.reason


def test_subquery_allowlisted_passes() -> None:
    res = validate_query(
        "SELECT asset FROM session_card_audit WHERE asset IN "
        "(SELECT DISTINCT asset FROM alerts WHERE severity = 'high')"
    )
    assert res.ok, res.reason
    assert "session_card_audit" in res.tables_referenced
    assert "alerts" in res.tables_referenced


# ── Negative: injection / DDL / DML must reject ─────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO session_card_audit (id) VALUES (1)",
        "UPDATE session_card_audit SET asset = 'X'",
        "DELETE FROM session_card_audit WHERE id = '1'",
        "DROP TABLE session_card_audit",
        "ALTER TABLE session_card_audit ADD COLUMN x int",
        "CREATE TABLE evil (id int)",
        "GRANT SELECT ON session_card_audit TO public",
        "TRUNCATE session_card_audit",
    ],
)
def test_dml_ddl_rejected(sql: str) -> None:
    res = validate_query(sql)
    assert not res.ok, f"Expected rejection, got pass for: {sql}"


def test_multi_statement_rejected() -> None:
    res = validate_query("SELECT * FROM session_card_audit; DROP TABLE alerts;")
    assert not res.ok
    assert "multi-statement" in res.reason


def test_information_schema_rejected() -> None:
    res = validate_query("SELECT table_name FROM information_schema.tables")
    assert not res.ok
    assert "forbidden" in res.reason.lower()


def test_pg_catalog_rejected() -> None:
    res = validate_query("SELECT relname FROM pg_catalog.pg_class")
    assert not res.ok
    assert "forbidden" in res.reason.lower()


def test_non_allowlisted_table_rejected() -> None:
    """trader_notes is explicitly excluded per ADR-050."""
    res = validate_query("SELECT * FROM trader_notes")
    assert not res.ok
    assert "trader_notes" in res.reason.lower() or "forbidden" in res.reason.lower()


def test_api_keys_table_rejected() -> None:
    """Even fictional secret tables get caught by the allowlist."""
    res = validate_query("SELECT key, secret FROM api_keys")
    assert not res.ok


def test_subquery_with_forbidden_table_rejected() -> None:
    """Forbidden table inside a subquery must still be caught."""
    res = validate_query(
        "SELECT * FROM session_card_audit WHERE id IN (SELECT id FROM secrets_store)"
    )
    assert not res.ok
    assert "secrets_store" in res.reason or "forbidden" in res.reason.lower()


def test_cte_with_forbidden_table_rejected() -> None:
    """CTE referencing a forbidden table is caught."""
    res = validate_query("WITH x AS (SELECT * FROM api_keys) SELECT * FROM x")
    assert not res.ok


def test_empty_string_rejected() -> None:
    assert not validate_query("").ok
    assert not validate_query("   ").ok


def test_garbage_input_rejected() -> None:
    res = validate_query("not a sql query at all")
    assert not res.ok


def test_explain_rejected() -> None:
    """EXPLAIN can reveal query plans + indexes; not in scope."""
    res = validate_query("EXPLAIN SELECT * FROM session_card_audit")
    assert not res.ok


def test_set_role_rejected() -> None:
    """SET commands can elevate privileges — must be blocked."""
    res = validate_query("SET ROLE postgres; SELECT 1")
    assert not res.ok


# ── Allowlist invariant guards ─────────────────────────────────────


def test_allowed_tables_is_canonical_six() -> None:
    """ADR-050 declared 6 tables. Drift guard."""
    expected = {
        "session_card_audit",
        "fred_observations",
        "gdelt_events",
        "gpr_observations",
        "cb_speeches",
        "alerts",
    }
    assert ALLOWED_TABLES == frozenset(expected)


# ── max_rows clamping ──────────────────────────────────────────────


def test_clamp_max_rows_default() -> None:
    assert _clamp_max_rows(None) == DEFAULT_MAX_ROWS
    assert _clamp_max_rows(0) == DEFAULT_MAX_ROWS
    assert _clamp_max_rows(-1) == DEFAULT_MAX_ROWS


def test_clamp_max_rows_inside() -> None:
    assert _clamp_max_rows(50) == 50
    assert _clamp_max_rows(500) == 500


def test_clamp_max_rows_over_hard_cap() -> None:
    assert _clamp_max_rows(2000) == HARD_MAX_ROWS
    assert _clamp_max_rows(1_000_000) == HARD_MAX_ROWS
