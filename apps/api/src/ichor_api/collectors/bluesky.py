"""Bluesky AT Protocol collector — replaces Twitter/X (free tier killed Feb 2026).

Per SPEC_V2_SOURCES.md §3 + ADR-021 docs. Uses the public AppView at
`public.api.bsky.app` for unauthenticated reads (profile/feed scraping).
Search now requires an App Password (free, 2026); we read it from
`BLUESKY_APP_PASSWORD` env if present, otherwise stick to the public
endpoints.

Whitelist: same as the Twitter/X CB-officials list — Fed, ECB, BoE, BoJ,
SNB, PBoC + key macroeconomists/strategists.

Cf https://github.com/MarshalX/atproto + https://docs.bsky.app/docs/advanced-guides/atproto
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

PUBLIC_APPVIEW = "https://public.api.bsky.app"

# CB officials + macro voices on Bluesky (handles to discover/verify).
WATCHLIST_HANDLES: tuple[str, ...] = (
    "federalreserve.bsky.social",
    "ecb.europa.eu",  # ATProto handles can be DNS-based
    "bankofengland.bsky.social",
    "fmcconnell.bsky.social",  # macroeconomist example
)


@dataclass(frozen=True)
class BlueskyPost:
    """One post from Bluesky."""

    uri: str  # at://did:plc:.../app.bsky.feed.post/...
    cid: str
    author_handle: str
    author_did: str
    text: str
    created_at: datetime
    reply_count: int
    repost_count: int
    like_count: int
    quote_count: int
    fetched_at: datetime
    raw: dict[str, Any]


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(UTC)


def parse_post(post: dict[str, Any]) -> BlueskyPost | None:
    """Convert a Bluesky AppView post node into a BlueskyPost."""
    record = post.get("record") or {}
    text = record.get("text")
    if not text:
        return None
    author = post.get("author") or {}
    return BlueskyPost(
        uri=str(post.get("uri") or ""),
        cid=str(post.get("cid") or ""),
        author_handle=str(author.get("handle") or "unknown"),
        author_did=str(author.get("did") or ""),
        text=str(text),
        created_at=_parse_iso(str(record.get("createdAt") or "")),
        reply_count=int(post.get("replyCount") or 0),
        repost_count=int(post.get("repostCount") or 0),
        like_count=int(post.get("likeCount") or 0),
        quote_count=int(post.get("quoteCount") or 0),
        fetched_at=datetime.now(UTC),
        raw=post,
    )


async def fetch_author_feed(
    handle: str,
    *,
    limit: int = 30,
    timeout_s: float = 15.0,
) -> list[BlueskyPost]:
    """Public unauthenticated fetch of an author's feed.

    Uses `app.bsky.feed.getAuthorFeed`. No API key required.
    """
    url = f"{PUBLIC_APPVIEW}/xrpc/app.bsky.feed.getAuthorFeed"
    params = {"actor": handle, "limit": min(max(1, limit), 100), "filter": "posts_no_replies"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError:
        return []
    feed = body.get("feed") or []
    out: list[BlueskyPost] = []
    for item in feed:
        post = item.get("post") or {}
        parsed = parse_post(post)
        if parsed is not None:
            out.append(parsed)
    return out


async def search_posts_authenticated(
    query: str,
    *,
    bsky_identifier: str,
    bsky_app_password: str,
    limit: int = 25,
    timeout_s: float = 20.0,
) -> list[BlueskyPost]:
    """Search posts (requires app password since Feb 2026).

    Two-step: createSession to get accessJwt, then searchPosts.
    Returns [] on any auth/API error.
    """
    if not bsky_identifier or not bsky_app_password:
        return []

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            session = await client.post(
                "https://bsky.social/xrpc/com.atproto.server.createSession",
                json={"identifier": bsky_identifier, "password": bsky_app_password},
            )
            session.raise_for_status()
            jwt = session.json().get("accessJwt")
        except httpx.HTTPError:
            return []
        if not jwt:
            return []

        try:
            r = await client.get(
                f"{PUBLIC_APPVIEW}/xrpc/app.bsky.feed.searchPosts",
                params={"q": query, "limit": min(max(1, limit), 100)},
                headers={"Authorization": f"Bearer {jwt}"},
            )
            r.raise_for_status()
            body = r.json()
        except httpx.HTTPError:
            return []

    posts = body.get("posts") or []
    return [p for p in (parse_post(post) for post in posts) if p is not None]


async def poll_watchlist(
    handles: tuple[str, ...] = WATCHLIST_HANDLES,
    *,
    per_handle_limit: int = 20,
) -> list[BlueskyPost]:
    """Poll all watchlist authors. No auth needed for getAuthorFeed."""
    out: list[BlueskyPost] = []
    for h in handles:
        posts = await fetch_author_feed(h, limit=per_handle_limit)
        out.extend(posts)
    return out
