"""GDELT collector resilience (S03 residual audit 2026-06-19).

The collector was down ≥2 days persisting 0 rows: GDELT 429s + the 5/15/45 s
backoff blew the 600 s systemd timeout across 14 queries, and the
fetch-all-then-persist-once path lost the WHOLE batch on the SIGTERM. These
pin the two code fixes: a capped, Retry-After-aware sleep, and per-query
streaming with intra-query dedup so a killed run keeps completed queries.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.collectors import gdelt
from ichor_api.collectors.gdelt import (
    _MAX_RETRY_SLEEP_S,
    GdeltArticle,
    GdeltQuery,
    _retry_sleep,
    poll_each,
)


def _art(url: str, label: str = "fed") -> GdeltArticle:
    return GdeltArticle(
        fetched_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        query_label=label,
        url=url,
        title="t",
        seendate=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        domain="d",
        language="en",
        sourcecountry="US",
        tone=0.0,
    )


# ───────────────────────────── _retry_sleep ─────────────────────────────


def test_retry_sleep_honors_server_retry_after() -> None:
    assert _retry_sleep("10", 3.0) == 10.0


def test_retry_sleep_caps_at_max() -> None:
    assert _retry_sleep("600", 3.0) == _MAX_RETRY_SLEEP_S  # server says 10min → capped
    assert _retry_sleep(None, 45.0) == _MAX_RETRY_SLEEP_S  # local backoff 45s → capped


def test_retry_sleep_falls_back_on_unparseable_or_absent() -> None:
    assert _retry_sleep("soon", 7.0) == 7.0  # garbage header → backoff
    assert _retry_sleep(None, 9.0) == 9.0  # no header → backoff
    assert _retry_sleep("", 5.0) == 5.0  # empty header → backoff


# ───────────────────── poll_each streaming + dedup ──────────────────────


@pytest.mark.asyncio
async def test_poll_each_streams_per_query_and_dedups_intra_query(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    q_fed = GdeltQuery(label="fed", query="Fed", timespan="1h", max_records=25)
    q_ecb = GdeltQuery(label="ecb", query="ECB", timespan="1h", max_records=25)
    canned = {
        # duplicate url within the fed query → collapsed to one
        "fed": [_art("http://a"), _art("http://a"), _art("http://b")],
        # same url 'a' under a DIFFERENT query → kept (cross-query dedup is the
        # DB's ON CONFLICT (url, query_label, seendate) job, preserving per-asset density)
        "ecb": [_art("http://a", label="ecb")],
    }

    async def _fake_fetch(q, *, client, **kw):  # type: ignore[no-untyped-def]
        return canned[q.label]

    monkeypatch.setattr(gdelt, "fetch_query", _fake_fetch)

    yielded: list[tuple[str, list[str]]] = []
    async for label, arts in poll_each([q_fed, q_ecb], politeness_delay_s=0):
        yielded.append((label, [a.url for a in arts]))

    # streamed one tuple per query, in order
    assert [lbl for lbl, _ in yielded] == ["fed", "ecb"]
    # intra-query url dedup applied to fed
    assert yielded[0] == ("fed", ["http://a", "http://b"])
    # cross-query same url is NOT dropped here (kept for the DB to dedup per label)
    assert yielded[1] == ("ecb", ["http://a"])


@pytest.mark.asyncio
async def test_poll_each_skips_empty_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    q = GdeltQuery(label="fed", query="Fed", timespan="1h", max_records=25)

    async def _fake_fetch(qq, *, client, **kw):  # type: ignore[no-untyped-def]
        return [_art(""), _art("http://x")]  # empty-url row dropped

    monkeypatch.setattr(gdelt, "fetch_query", _fake_fetch)
    out = [arts async for _, arts in poll_each([q], politeness_delay_s=0)]
    assert [a.url for a in out[0]] == ["http://x"]


def test_fetch_query_default_max_retries_is_bounded() -> None:
    import inspect

    sig = inspect.signature(gdelt.fetch_query)
    assert sig.parameters["max_retries"].default == 2  # was 3; bounds wall-clock
