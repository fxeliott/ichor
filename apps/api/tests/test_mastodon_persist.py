"""Tests for mastodon.persist_to_news_items + status_to_news_item_payload.

Pure-function payload mapping is fully tested ; the persist function
is covered with a stub AsyncSession so we don't need a live DB.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.collectors.mastodon import (
    MastodonStatus,
    persist_to_news_items,
    status_to_news_item_payload,
)


def _status(
    *,
    status_id: str = "tag:mastodon.social,2026-05-04:objectId=42:objectType=Status",
    instance: str = "mastodon.social",
    author: str = "alice",
    title: str = "Macro take",
    content: str = "Inflation is sticky and the Fed is behind the curve.",
    url: str | None = "https://mastodon.social/web/@alice/42",
    feed_kind: str = "user",
) -> MastodonStatus:
    return MastodonStatus(
        instance=instance,
        status_id=status_id,
        author=author,
        title=title,
        content_text=content,
        url=url,
        published_at=datetime(2026, 5, 4, 7, 18, tzinfo=UTC),
        feed_kind=feed_kind,  # type: ignore[arg-type]
    )


# ─────────────────────── status_to_news_item_payload ──────────────────


def test_payload_basic_fields() -> None:
    s = _status()
    p = status_to_news_item_payload(s)
    assert p["source"] == "mastodon:mastodon.social"
    assert p["source_kind"] == "social"
    assert p["title"] == "Macro take"
    assert p["url"] == "https://mastodon.social/web/@alice/42"
    assert p["published_at"] == datetime(2026, 5, 4, 7, 18, tzinfo=UTC)
    # guid_hash is sha256 prefix, deterministic for same status_id
    assert isinstance(p["guid_hash"], str) and len(p["guid_hash"]) == 32
    # raw_categories includes feed_kind + author
    assert p["raw_categories"] == ["user", "alice"]


def test_payload_falls_back_url_when_none() -> None:
    s = _status(url=None)
    p = status_to_news_item_payload(s)
    assert isinstance(p["url"], str) and p["url"].startswith("atom-id:")


def test_payload_truncates_title_to_512() -> None:
    s = _status(title="x" * 600, content="ignored")
    p = status_to_news_item_payload(s)
    title = p["title"]
    assert isinstance(title, str)
    assert len(title) == 512


def test_payload_falls_back_title_to_content_truncated() -> None:
    s = _status(title="", content="A" * 200)
    p = status_to_news_item_payload(s)
    title = p["title"]
    assert isinstance(title, str)
    # status_to_news_item_payload uses content[:120] when title is empty
    assert len(title) == 120


def test_payload_summary_capped_at_1024() -> None:
    s = _status(content="z" * 5000)
    p = status_to_news_item_payload(s)
    summary = p["summary"]
    assert isinstance(summary, str)
    assert len(summary) == 1024


def test_payload_guid_hash_stable_for_same_id() -> None:
    s1 = _status(status_id="tag:abc")
    s2 = _status(status_id="tag:abc", title="different title")
    assert (
        status_to_news_item_payload(s1)["guid_hash"] == status_to_news_item_payload(s2)["guid_hash"]
    )


def test_payload_guid_hash_different_for_different_id() -> None:
    s1 = _status(status_id="tag:abc")
    s2 = _status(status_id="tag:xyz")
    assert (
        status_to_news_item_payload(s1)["guid_hash"] != status_to_news_item_payload(s2)["guid_hash"]
    )


def test_payload_handles_no_author() -> None:
    s = _status(author="")
    p = status_to_news_item_payload(s)
    # Empty author still produces a list with just feed_kind
    assert p["raw_categories"] == ["user"]


# ─────────────────────────── persist_to_news_items ─────────────────


class _StubResult:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, str]]:
        return self._rows


class _StubSession:
    """AsyncSession stub recording added rows + serving 'existing' tuples."""

    def __init__(self, existing: list[tuple[str, str]] | None = None) -> None:
        self._existing = existing or []
        self.added: list[object] = []
        self.flushed = 0

    async def execute(self, stmt: object) -> _StubResult:
        return _StubResult(self._existing)

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed += 1


@pytest.mark.asyncio
async def test_persist_skips_existing_pairs() -> None:
    s = _StubSession(existing=[("mastodon:mastodon.social", "deadbeef")])
    statuses = [
        _status(status_id="duplicate"),
        _status(status_id="brand-new"),
    ]
    # Force one of the payload guid_hashes to match the "existing" stub
    payload_existing = status_to_news_item_payload(statuses[0])
    s._existing = [(payload_existing["source"], payload_existing["guid_hash"])]  # type: ignore[list-item]

    inserted = await persist_to_news_items(s, statuses)
    # 2 candidates, 1 dupe → 1 inserted
    assert inserted == 1
    assert len(s.added) == 1
    assert s.flushed == 1


@pytest.mark.asyncio
async def test_persist_empty_list_short_circuits() -> None:
    s = _StubSession()
    inserted = await persist_to_news_items(s, [])
    assert inserted == 0
    assert s.added == []
    assert s.flushed == 0


@pytest.mark.asyncio
async def test_persist_inserts_all_when_no_existing() -> None:
    s = _StubSession(existing=[])
    statuses = [_status(status_id=f"id-{i}", title=f"toot {i}") for i in range(5)]
    inserted = await persist_to_news_items(s, statuses)
    assert inserted == 5
    assert len(s.added) == 5
