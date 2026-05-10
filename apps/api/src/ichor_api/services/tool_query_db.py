"""query_db tool handler — Capability 5 STEP-1 (W83+, ADR-071).

Read-only SQL access for the 4-pass orchestrator. Implements the
sqlglot-AST whitelist enforcement that ADR-071 § STEP-1 mandated to
replace the description-text-only allowlist of ADR-050.

Three concentric defenses :
  1. **Statement gate** : only `SELECT` (and `WITH ... SELECT`) accepted.
     Anything else (INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/GRANT/EXEC,
     plus pg-specific COPY/SET/SHOW/EXPLAIN/VACUUM) is rejected.
  2. **Table allowlist** : every table referenced in the AST (top-level,
     subqueries, CTEs, JOINs, UNIONs) must be in `ALLOWED_TABLES`.
     Schema-qualified names (`pg_catalog.pg_class`, `information_schema.*`)
     are rejected.
  3. **Multi-statement gate** : sqlglot.parse(sql) returns a list of
     statements; we reject anything with len > 1, blocking SQL-injection
     payloads of the form `SELECT 1; DROP TABLE api_keys`.

The whitelist comes from ADR-050 §QUERY_DB description and is the
**canonical 6-table set**. Future extensions go through a new ADR
(don't silently widen the surface).

The handler is **read-only**: it executes the validated SQL via
`session.execute(text(sql))` on the standard async engine, but the
ichor DB user is provisioned with limited grants
(see `apps/api/migrations/`...). The whitelist is the primary
defense; least-privilege at the DB role layer is the backstop.

This service is not yet wired into the orchestrator. It's
unit-tested standalone and waits for ADR-071 STEP-3+ to be plugged
into the Ichor MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Canonical whitelist per ADR-050 § QUERY_DB description.
# Locked at this set unless a new ADR ratifies an extension.
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "session_card_audit",
        "fred_observations",
        "gdelt_events",
        "gpr_observations",
        "cb_speeches",
        "alerts",
    }
)

# Hard cap on rows returned by any single query, regardless of the
# `max_rows` request parameter. Defends against unbounded payloads
# even if the orchestrator forgets to set the limit.
HARD_MAX_ROWS = 1000

# Default when `max_rows` not specified.
DEFAULT_MAX_ROWS = 100

# Statement classes accepted by the parser.
# sqlglot's expression class names — Select for SELECT, plus `With` (CTE
# wrapper that ultimately yields a Select).
_ALLOWED_STATEMENT_TYPES: tuple[type, ...] = (
    sqlglot.exp.Select,
    sqlglot.exp.Union,
    sqlglot.exp.Intersect,
    sqlglot.exp.Except,
)

# W99 hardening (post code review) — Postgres functions / mechanisms that
# can lock, sleep, IO, or escape the SELECT-only sandbox even when the
# top-level statement is technically a `Select`. Each name is matched
# case-insensitively against `sqlglot.exp.Anonymous.this` (= function
# name token) during AST walk. Adding to this list is a security-positive
# change ; removing requires an ADR.
_FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {
        # Time-based DoS (block the connection for N seconds, exhausts pool)
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        # Advisory locks (could deadlock other Ichor cron jobs)
        "pg_advisory_lock",
        "pg_advisory_lock_shared",
        "pg_advisory_xact_lock",
        "pg_advisory_xact_lock_shared",
        "pg_try_advisory_lock",
        "pg_try_advisory_lock_shared",
        "pg_try_advisory_xact_lock",
        "pg_try_advisory_xact_lock_shared",
        # Large object IO (filesystem read/write inside the DB)
        "lo_import",
        "lo_export",
        "lo_open",
        "lo_create",
        "lo_unlink",
        # Network egress / cross-DB (data exfiltration)
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "dblink_send_query",
        "postgres_fdw_handler",
        # Server-side process escape (if extensions are loaded)
        "copy_from_program",
        "copy_to_program",
        # Reflection / privilege probing
        "current_setting",
        "set_config",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
    }
)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of `validate_query`."""

    ok: bool
    reason: str
    """Empty when ok=True. Structured error message when ok=False."""

    tables_referenced: frozenset[str] = frozenset()
    """All tables that the AST walked through (verified against allowlist)."""


class ToolQueryDbError(Exception):
    """Raised for runtime failures during SQL execution. Validation
    failures don't raise — they return a `ValidationResult(ok=False)`."""


def _extract_tables(expr: sqlglot.exp.Expression) -> frozenset[str]:
    """Walk the AST and return every plain (un-aliased) table name.

    Catches:
      - top-level `FROM`
      - JOIN tables
      - subqueries
      - CTEs (the WITH ... AS (SELECT ...) inner query)
      - UNION / INTERSECT / EXCEPT branches

    CTE alias names are tracked and excluded from the returned set so
    a query like `WITH recent AS (SELECT * FROM fred_observations) SELECT
    * FROM recent` doesn't trip the allowlist check on the alias
    `recent` (only the underlying real table `fred_observations` matters).
    """
    # First pass: collect CTE alias names so we can skip them in the
    # second pass.
    cte_aliases: set[str] = set()
    for node in expr.walk():
        if isinstance(node, sqlglot.exp.CTE):
            alias_obj = node.args.get("alias")
            if alias_obj is not None:
                # alias_obj is a TableAlias; .name gives the alias string
                alias_name = getattr(alias_obj, "name", None) or str(alias_obj)
                if alias_name:
                    cte_aliases.add(alias_name.lower())

    # Second pass: collect concrete tables, skipping CTE aliases and
    # capturing schema-qualified names verbatim (so they get rejected
    # by the allowlist check).
    tables: set[str] = set()
    for node in expr.walk():
        if isinstance(node, sqlglot.exp.Table):
            # Reject schema-qualified names: only bare table names allowed.
            # node.args["db"] is the schema/catalog (e.g. "pg_catalog").
            db = node.args.get("db")
            if db is not None:
                tables.add(f"{db.name}.{node.name}".lower())
                continue
            name = node.name.lower()
            if name in cte_aliases:
                # Internal CTE reference — the alias is verified by the
                # presence of the underlying real table elsewhere in the
                # walk, which is already in the allowlist check.
                continue
            tables.add(name)
    return frozenset(tables)


def _walk_for_forbidden_functions(expr: sqlglot.exp.Expression) -> str | None:
    """W99 — return the first forbidden function name encountered in the
    AST, or None if clean. Matches `sqlglot.exp.Anonymous` (unknown /
    user-defined functions including `pg_sleep`) AND `sqlglot.exp.Func`
    subclasses with matching `name`. Case-insensitive.
    """
    for node in expr.walk():
        # Anonymous = user-defined or unrecognized-by-sqlglot function call.
        # `node.name` is the function identifier as written.
        if isinstance(node, sqlglot.exp.Anonymous):
            fname = (node.name or "").lower()
            if fname in _FORBIDDEN_FUNCTIONS:
                return fname
        # Some Postgres builtins resolve to a typed sqlglot.exp.Func
        # subclass (rare for the ones we forbid, but defense in depth).
        elif isinstance(node, sqlglot.exp.Func):
            fname = getattr(node, "_class_name", "") or type(node).__name__
            fname = fname.lower()
            if fname in _FORBIDDEN_FUNCTIONS:
                return fname
    return None


def _has_lock_clause(stmt: sqlglot.exp.Expression) -> bool:
    """W99 — `SELECT ... FOR UPDATE / FOR SHARE / FOR NO KEY UPDATE / FOR
    KEY SHARE` lifts row-level locks that block other transactions. Even
    when wrapped in a CTE, sqlglot exposes these via the `locks` arg on
    the inner `Select`. Walk the whole AST so locks inside subqueries
    are also caught.
    """
    for node in stmt.walk():
        if isinstance(node, sqlglot.exp.Select):
            locks = node.args.get("locks")
            if locks:
                return True
    return False


def validate_query(sql: str) -> ValidationResult:
    """Pure validator. Returns (ok, reason). Never raises.

    Five concentric checks (W99 hardened) :
      1. Multi-statement reject (len(parsed) > 1 → reject).
      2. Top-level statement type must be SELECT-equivalent.
      3. Every referenced table must be in ALLOWED_TABLES.
      4. No forbidden function calls (`pg_sleep`, `pg_advisory_lock`,
         `lo_*`, `dblink`, `copy_from_program`, etc.).
      5. No row-level lock clauses (`FOR UPDATE`, `FOR SHARE`, ...).
    """
    if not isinstance(sql, str) or not sql.strip():
        return ValidationResult(ok=False, reason="empty SQL string")

    try:
        parsed = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(ok=False, reason=f"parse error: {e}")
    except Exception as e:  # noqa: BLE001 — sqlglot may throw various
        return ValidationResult(ok=False, reason=f"parse failure: {type(e).__name__}: {e}")

    # Defense 1 — multi-statement block.
    statements = [s for s in parsed if s is not None]
    if len(statements) == 0:
        return ValidationResult(ok=False, reason="no parseable statement")
    if len(statements) > 1:
        return ValidationResult(
            ok=False,
            reason=f"multi-statement query rejected ({len(statements)} statements)",
        )

    stmt = statements[0]

    # Defense 2 — statement type must be SELECT/UNION/INTERSECT/EXCEPT.
    # CTEs are wrapped: `With(this=Select(...))` or similar.
    body = stmt.args.get("this") if isinstance(stmt, sqlglot.exp.With) else stmt
    if not isinstance(body, _ALLOWED_STATEMENT_TYPES):
        return ValidationResult(
            ok=False,
            reason=(
                f"non-SELECT statement rejected: {type(body).__name__} "
                f"(only SELECT / UNION / INTERSECT / EXCEPT allowed)"
            ),
        )

    # Defense 3 — table allowlist.
    tables = _extract_tables(stmt)
    forbidden = {t for t in tables if t not in ALLOWED_TABLES}
    if forbidden:
        return ValidationResult(
            ok=False,
            reason=(
                f"forbidden table(s) referenced: {sorted(forbidden)}. "
                f"Allowlist: {sorted(ALLOWED_TABLES)}"
            ),
            tables_referenced=tables,
        )

    # Defense 4 (W99) — forbidden function calls (pg_sleep DoS, locks,
    # filesystem IO, network egress, etc.). See `_FORBIDDEN_FUNCTIONS`.
    forbidden_fn = _walk_for_forbidden_functions(stmt)
    if forbidden_fn is not None:
        return ValidationResult(
            ok=False,
            reason=(
                f"forbidden function call: {forbidden_fn!r} (DoS / lock / IO / "
                f"egress risk). See ADR-077 + W99 hardening for the list."
            ),
            tables_referenced=tables,
        )

    # Defense 5 (W99) — row-level lock clauses. `FOR UPDATE / FOR SHARE`
    # blocks other transactions and is incompatible with the read-only
    # tool surface contract.
    if _has_lock_clause(stmt):
        return ValidationResult(
            ok=False,
            reason=(
                "row-level lock clause rejected (FOR UPDATE / FOR SHARE / "
                "FOR NO KEY UPDATE / FOR KEY SHARE). query_db is read-only."
            ),
            tables_referenced=tables,
        )

    return ValidationResult(ok=True, reason="", tables_referenced=tables)


def _clamp_max_rows(max_rows: int | None) -> int:
    """Clamp `max_rows` to [1, HARD_MAX_ROWS]. Default DEFAULT_MAX_ROWS."""
    if max_rows is None:
        return DEFAULT_MAX_ROWS
    if max_rows <= 0:
        return DEFAULT_MAX_ROWS
    return min(max_rows, HARD_MAX_ROWS)


async def execute_query(
    session: AsyncSession, sql: str, max_rows: int | None = None
) -> list[dict[str, Any]]:
    """Validate + execute a read-only SQL query against the whitelist.

    Raises `ToolQueryDbError` on validation failure (caller should
    convert to `tool_call_audit.error` + `tool_output={"error": ...}`).
    Returns a list of dict rows — at most `max_rows` (default 100,
    hard cap 1000).
    """
    validation = validate_query(sql)
    if not validation.ok:
        raise ToolQueryDbError(f"validation rejected query: {validation.reason}")

    capped = _clamp_max_rows(max_rows)

    # We don't append LIMIT here because the validator allowed only
    # SELECT/UNION etc. — the caller's LIMIT is honored. The hard cap
    # is enforced post-fetch by truncating the result set.
    try:
        result = await session.execute(text(sql))
        rows = result.mappings().fetchmany(capped)
        return [dict(r) for r in rows]
    except Exception as e:
        raise ToolQueryDbError(f"execution failure: {type(e).__name__}: {e}") from e


__all__ = [
    "ALLOWED_TABLES",
    "DEFAULT_MAX_ROWS",
    "HARD_MAX_ROWS",
    "ToolQueryDbError",
    "ValidationResult",
    "execute_query",
    "validate_query",
]
