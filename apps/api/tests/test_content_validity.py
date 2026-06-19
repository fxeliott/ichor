"""Pure tests for the content-validity classifier (S03 freshness monitor).

`classify_content` closes the Kalshi silent-death blind spot: rows arriving
(freshness GREEN) but every value NULL/degenerate. Catches the NULL class
(Kalshi yes_price) and the all-same-value class (GDELT tone=0.0 incident).
"""

from __future__ import annotations

from ichor_api.services.collector_freshness import classify_content


def test_insufficient_sample_never_flags() -> None:
    # Below min_sample we cannot tell dead from quiet → never flag.
    assert classify_content(sample_size=5, non_null=0, distinct=0) == "insufficient_sample"
    assert classify_content(sample_size=19, non_null=0, distinct=0) == "insufficient_sample"


def test_kalshi_all_null_is_null_dead() -> None:
    # The exact Kalshi incident: 60 rows persisted, every yes_price NULL.
    assert classify_content(sample_size=60, non_null=0, distinct=0) == "null_dead"


def test_mostly_null_above_threshold_is_null_dead() -> None:
    # null_rate = 1 - 4/100 = 0.96 > 0.95
    assert classify_content(sample_size=100, non_null=4, distinct=4) == "null_dead"


def test_null_rate_exactly_at_threshold_is_ok() -> None:
    # null_rate = 0.95, the check is strict `> max_null_rate` → not dead;
    # distinct > 1 → not degenerate → ok.
    assert classify_content(sample_size=100, non_null=5, distinct=5) == "ok"


def test_gdelt_all_same_value_is_degenerate() -> None:
    # The GDELT tone=0.0-everywhere incident: non-null but a single distinct value.
    assert classify_content(sample_size=33, non_null=33, distinct=1) == "degenerate"


def test_healthy_varied_column_is_ok() -> None:
    assert classify_content(sample_size=60, non_null=60, distinct=40) == "ok"
    # a few legitimate NULLs (below threshold) + variety → still ok
    assert classify_content(sample_size=60, non_null=55, distinct=30) == "ok"


def test_custom_thresholds_respected() -> None:
    # Stricter null tolerance flags a column the default would pass.
    assert (
        classify_content(sample_size=100, non_null=80, distinct=50, max_null_rate=0.1)
        == "null_dead"
    )
    # Lower min_sample lets a small sample be judged.
    assert classify_content(sample_size=8, non_null=0, distinct=0, min_sample=5) == "null_dead"
