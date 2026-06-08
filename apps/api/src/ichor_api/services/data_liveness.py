"""Generic data-source liveness — S04 « no silent stale/absent ».

Why this module exists
----------------------
The runtime liveness audit (``data_pool._fred_liveness`` / ``DegradedInput``,
``data_pool.py:281-398``) covers ONLY the ~6 FRED critical anchors. Every
non-FRED table the brain reads — NyFed MCT, Cleveland nowcast, NFIB, COT, TFF,
GPR, … — gates on emptiness alone (``if not rows: rows[0]``) with NO age check,
so a months-stale row renders as the current headline value with zero trace
(the systemic « zone d'ombre » the S04 depth audit named the TGA-bug class).

This module is the **pure, dependency-free generalization** that closes it:
the caller passes the ``latest_date`` it already fetched, and this classifies
``fresh | stale | absent`` against a max-age, mirroring the EXACT FRED semantics
(``age = today - latest_date``; ``fresh ⟺ age <= max_age``) so the two compose
into a single degraded-inputs manifest.

Design contract (deliberately pure — mirrors ``conviction_fusion``)
-------------------------------------------------------------------
No I/O, no SQLAlchemy, no datetime.now() call inside (``now`` is injected, so
the function is deterministic + unit-testable). Increment-1 core; the wiring
into each ``_section_*`` (append to the shared degraded list + render a STALE
band instead of a silent ``rows[0]``) is the deploy-gated increment-2 step.

Byte-consistency invariant
--------------------------
``classify_liveness(k, d, now=n, max_age_days=m).status`` equals
``_fred_liveness``'s status for the same ``(observation_date, max_age)`` —
``fresh`` iff ``(n - d).days <= m`` (``data_pool.py:396-398``). Pinned by
``test_data_liveness.test_mirrors_fred_liveness_boundary``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

LivenessStatus = Literal["fresh", "stale", "absent"]


@dataclass(frozen=True, slots=True)
class SourceLiveness:
    """Liveness verdict for one persisted source over its freshness window.

    ``source_key`` is a provenance label (e.g. ``"NYFED:MCT"``, ``"CFTC:COT"``,
    ``"GPR"``) — the non-FRED analogue of ``FredLiveness.series_id``, so a
    generalized integrity header can count degraded anchors regardless of
    provenance. ``status == "fresh"`` ⟺ not degraded.
    """

    source_key: str
    status: LivenessStatus
    latest_date: date | None
    age_days: int | None
    max_age_days: int
    impacted: str = ""

    @property
    def is_degraded(self) -> bool:
        """True for ``stale`` or ``absent`` — the input silently degrades its
        dependent section/driver and must surface (ADR-099 §D-2
        « never silently absent »)."""
        return self.status != "fresh"


def _as_date(value: date | datetime) -> date:
    """Normalize to a plain ``date``. The FRED audit compares
    ``observation_date`` (a pure ``date``); a ``datetime`` caller (e.g. a
    table whose latest column is a timestamp) is reduced to its date so the
    age arithmetic stays in whole days, identical to the FRED path."""
    return value.date() if isinstance(value, datetime) else value


def classify_liveness(
    source_key: str,
    latest_date: date | datetime | None,
    *,
    now: date | datetime,
    max_age_days: int,
    impacted: str = "",
) -> SourceLiveness:
    """Classify a source ``fresh | stale | absent`` — generic mirror of
    ``data_pool._fred_liveness`` (``data_pool.py:371-398``).

    * ``latest_date is None`` → ``absent`` (collector never delivered).
    * else ``age = (now - latest_date).days``; ``fresh`` iff
      ``age <= max_age_days``, else ``stale``.

    A future-dated ``latest`` (negative age, e.g. a forward-stamped weekly
    release) classifies ``fresh`` — same as the FRED path's ``age <= max_age``.
    ``now`` is injected (no ``datetime.now()`` here) so callers stay
    deterministic and the function is pure.
    """
    if max_age_days < 0:
        raise ValueError(f"max_age_days must be >= 0, got {max_age_days}")
    if latest_date is None:
        return SourceLiveness(source_key, "absent", None, None, max_age_days, impacted)
    latest = _as_date(latest_date)
    today = _as_date(now)
    age = (today - latest).days
    status: LivenessStatus = "fresh" if age <= max_age_days else "stale"
    return SourceLiveness(source_key, status, latest, age, max_age_days, impacted)
