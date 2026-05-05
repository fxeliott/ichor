"""Mastodon ATOM collector — pulls statuses from public Mastodon accounts.

Each Mastodon instance exposes a public Atom 1.0 feed per user at
  https://{instance}/users/{username}.atom
and per hashtag at
  https://{instance}/tags/{tag}.atom

Both endpoints are public, rate-limited but not API-keyed, and return a
deterministic Atom feed schema. We use them to surface decentralized
finance commentary without needing OAuth.

ToS-friendly: read-only, no auth, no posting. Respect each instance's
rate-limits via the standard `httpx` retry policy. We poll once every
30 minutes by default.

Atom schema (parsed via defusedxml):
  <feed xmlns="http://www.w3.org/2005/Atom"
        xmlns:activity="http://activitystrea.ms/spec/1.0/"
        xmlns:thr="http://purl.org/syndication/thread/1.0">
    <entry>
      <id>tag:instance,YYYY-MM-DD:objectId=...</id>
      <published>2026-05-04T07:18:00Z</published>
      <updated>2026-05-04T07:18:00Z</updated>
      <title>Status content as plain title</title>
      <content type="html">...HTML body...</content>
      <link rel="alternate" href="https://instance/web/@user/123"/>
      <author>
        <name>display name</name>
      </author>
    </entry>
  </feed>

PERSISTENCE — parser-only. Statuses stream into the existing
`news_items` table via the same persistence helper as RSS, with
`source_kind = "social"`. Persistence wiring lands in the next sprint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx
from defusedxml.ElementTree import fromstring as defused_fromstring

# Atom feed XML namespace.
_NS = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class MastodonStatus:
    """One status from a Mastodon ATOM feed, normalized to UTC."""

    instance: str
    """Hostname of the Mastodon instance, e.g. `mastodon.social`."""
    status_id: str
    """Stable Atom <id>, used as dedup key."""
    author: str
    """Display name from <author><name>; may be empty."""
    title: str
    """Short title (first sentence-ish; HTML-stripped)."""
    content_text: str
    """Plain-text body with HTML tags stripped."""
    url: str | None
    """Permalink to the status on the instance web UI."""
    published_at: datetime
    feed_kind: Literal["user", "tag"]


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    no_tags = _HTML_TAG_RE.sub(" ", s)
    return _WS_RE.sub(" ", no_tags).strip()


def _parse_atom_datetime(s: str | None) -> datetime | None:
    """RFC 3339 with optional fractional seconds and `Z` suffix."""
    if not s:
        return None
    s = s.strip()
    # `fromisoformat` handles `Z` natively in Python 3.11+.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _first_alternate_link(entry) -> str | None:  # type: ignore[no-untyped-def]
    """Return href of the first <link rel="alternate"> in the entry."""
    for link in entry.findall(f"{_NS}link"):
        rel = link.attrib.get("rel", "alternate")
        href = link.attrib.get("href")
        if rel == "alternate" and href:
            return href
    # Fallback: any link with href.
    any_link = entry.find(f"{_NS}link")
    return any_link.attrib.get("href") if any_link is not None else None


def parse_mastodon_atom(
    xml_body: str,
    *,
    instance: str,
    feed_kind: Literal["user", "tag"] = "user",
) -> list[MastodonStatus]:
    """Parse one Mastodon ATOM feed body into normalized statuses."""
    root = defused_fromstring(xml_body)
    out: list[MastodonStatus] = []
    for entry in root.findall(f"{_NS}entry"):
        atom_id = (entry.findtext(f"{_NS}id") or "").strip()
        if not atom_id:
            continue
        published = _parse_atom_datetime(entry.findtext(f"{_NS}published"))
        if published is None:
            continue
        title_raw = entry.findtext(f"{_NS}title") or ""
        content_raw = entry.findtext(f"{_NS}content") or ""
        title = _strip_html(title_raw)
        content_text = _strip_html(content_raw)
        if not content_text and not title:
            continue
        author_el = entry.find(f"{_NS}author")
        author = ""
        if author_el is not None:
            author = (author_el.findtext(f"{_NS}name") or "").strip()
        out.append(
            MastodonStatus(
                instance=instance,
                status_id=atom_id,
                author=author,
                title=title or content_text[:120],
                content_text=content_text,
                url=_first_alternate_link(entry),
                published_at=published,
                feed_kind=feed_kind,
            )
        )
    out.sort(key=lambda s: s.published_at, reverse=True)
    return out


def user_feed_url(instance: str, username: str) -> str:
    """Build the per-user ATOM URL for a given Mastodon instance.

    Strips a leading `@` from the username and a trailing slash from
    the instance. Both arguments are user-supplied, so quote them
    via httpx URL building before fetching to avoid path injection."""
    return f"https://{instance.rstrip('/')}/users/{username.lstrip('@')}.atom"


def tag_feed_url(instance: str, tag: str) -> str:
    """Build the per-hashtag ATOM URL. Tag must be normalized (no `#`)."""
    return f"https://{instance.rstrip('/')}/tags/{tag.lstrip('#')}.atom"


async def fetch_mastodon_atom(
    url: str,
    *,
    instance: str,
    feed_kind: Literal["user", "tag"] = "user",
    client: httpx.AsyncClient | None = None,
    timeout_s: float = 20.0,
) -> list[MastodonStatus]:
    """Async fetch + parse one Mastodon ATOM feed.

    Caller-owned client supports test mocking + connection pooling. If
    not provided, a one-shot client is created with `timeout_s`.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            resp = await c.get(url)
    else:
        resp = await client.get(url, timeout=timeout_s)
    resp.raise_for_status()
    return parse_mastodon_atom(resp.text, instance=instance, feed_kind=feed_kind)


import hashlib  # noqa: E402 — placed below to keep public API on top


def status_to_news_item_payload(s: MastodonStatus) -> dict[str, object]:
    """Map a parsed Mastodon status to the columns of `news_items`.

    Stable `guid_hash` from the Atom <id> ensures dedup across re-fetches
    of the same feed. `source_kind = "social"` segregates these rows
    from RSS-collected news in /v1/news filters.
    """
    from datetime import UTC, datetime

    title = s.title.strip() or s.content_text[:120].strip()
    summary = s.content_text[:1024] if s.content_text else None
    guid = hashlib.sha256(s.status_id.encode("utf-8")).hexdigest()[:32]
    return {
        "source": f"mastodon:{s.instance}",
        "source_kind": "social",
        "title": title[:512],
        "summary": summary,
        "url": s.url or f"atom-id:{s.status_id}",
        "published_at": s.published_at,
        "fetched_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "guid_hash": guid,
        "raw_categories": [s.feed_kind, s.author] if s.author else [s.feed_kind],
    }


async def persist_to_news_items(
    session,  # type: ignore[no-untyped-def]  # AsyncSession
    statuses: list[MastodonStatus],
) -> int:
    """Insert Mastodon statuses into the existing `news_items` table.

    Mirrors the in-memory dedup pattern of `collectors.persistence.
    persist_news_items` for RSS : query existing (source, guid_hash)
    tuples in one round-trip, then insert only the new ones.

    Source is always `mastodon:{instance}` so the rows segregate from
    RSS-collected news in /v1/news filters. The FinBERT-tone worker
    can later annotate `tone_label` / `tone_score` post-hoc.

    Returns the number of NEW rows inserted. Caller owns the
    transaction (no commit here — same convention as the rest of
    `collectors.persistence`).
    """
    if not statuses:
        return 0
    from sqlalchemy import select

    from ..models import NewsItem

    payloads = [status_to_news_item_payload(s) for s in statuses]
    sources = {p["source"] for p in payloads}
    hashes = {p["guid_hash"] for p in payloads}

    existing_rows = (
        await session.execute(
            select(NewsItem.source, NewsItem.guid_hash).where(
                NewsItem.source.in_(sources), NewsItem.guid_hash.in_(hashes)
            )
        )
    ).all()
    existing: set[tuple[str, str]] = {(r[0], r[1]) for r in existing_rows}

    inserted = 0
    for p in payloads:
        key = (p["source"], p["guid_hash"])
        if key in existing:
            continue
        session.add(NewsItem(**p))
        inserted += 1

    await session.flush()
    return inserted
