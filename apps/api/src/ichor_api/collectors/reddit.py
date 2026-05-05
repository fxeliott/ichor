"""Reddit public-JSON collector — pulls hot posts from finance subreddits.

Reddit exposes a public JSON endpoint at any listing URL by appending
`.json` (e.g. `https://www.reddit.com/r/wallstreetbets/hot.json?limit=50`).
This is a documented, stable, no-auth read path that has been supported
since 2010+. Reddit's API ToS allows this for non-commercial polling at
modest rates with a descriptive User-Agent header.

We poll a configurable list of subreddits (default : `wallstreetbets`,
`forex`, `Gold`, `economics`) and surface the top-N hot posts as a
sentiment signal feeder. The persistence path mirrors `mastodon` :
parsed posts stream into `news_items` with `source_kind = "social"` and
`source = "reddit:{subreddit}"`, dedup-stable via `guid_hash` from the
post's stable `name` field (e.g. "t3_abc123").

ToS-friendly :
  - Read-only, no posting, no auth.
  - User-Agent identifies us as `ichor:macro-pulse:1.0`.
  - Rate-limited at the cron level (30-min cadence default).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx

# Default User-Agent — Reddit explicitly asks for an identifiable string
# in the form `<platform>:<appname>:<version> (by /u/<username>)`. Empty
# user-agent triggers a 429 in many cases.
DEFAULT_USER_AGENT = "ichor-collector:macro-pulse:1.0"

# Default subreddits relevant to the Phase-1 universe (FX + macro + gold).
DEFAULT_SUBREDDITS: tuple[str, ...] = (
    "wallstreetbets",
    "forex",
    "Gold",
    "economics",
    "macroeconomics",
)

PostKind = Literal["link", "self"]


@dataclass(frozen=True)
class RedditPost:
    """One normalized post from a Reddit listing."""

    subreddit: str
    """Lowercase subreddit name (e.g. "wallstreetbets")."""
    name: str
    """Stable Reddit fullname like "t3_abc123" — used for dedup."""
    title: str
    selftext: str
    """Body text for self-posts ; empty for link posts."""
    url: str
    """Permalink to the post on reddit.com (always populated)."""
    author: str
    """Author handle without /u/ prefix."""
    score: int
    """Net score (upvotes minus downvotes)."""
    num_comments: int
    created_at: datetime
    """UTC datetime parsed from `created_utc` epoch."""
    kind: PostKind


_HTML_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|#39);")
_ENTITY_MAP = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "#39": "'"}


def _decode_entities(s: str) -> str:
    """Reddit JSON sometimes returns `&amp;` etc. Cheap decoder."""
    return _HTML_ENTITY_RE.sub(lambda m: _ENTITY_MAP[m.group(1)], s)


def listing_url(subreddit: str, *, sort: str = "hot", limit: int = 50) -> str:
    """Build the public listing URL.

    Strips a leading `r/` from the subreddit and clamps `limit` to
    Reddit's documented max (100). Default sort is `hot` ; callers can
    pass `top` / `new` / `rising`."""
    s = subreddit.strip().removeprefix("r/").lstrip("/")
    n = max(1, min(100, limit))
    return f"https://www.reddit.com/r/{s}/{sort}.json?limit={n}"


def parse_listing(body: str | dict, *, subreddit: str) -> list[RedditPost]:
    """Parse a Reddit JSON listing into typed posts.

    Accepts either the raw JSON string or a pre-parsed dict (for tests).
    Silently drops malformed children (Reddit occasionally injects
    `t1` comment objects in listings — we filter to `t3` link/self).
    """
    if isinstance(body, str):
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return []
    else:
        data = body
    if not isinstance(data, dict):
        return []
    children = (
        data.get("data", {}).get("children", []) if isinstance(data.get("data"), dict) else []
    )
    if not isinstance(children, list):
        return []

    out: list[RedditPost] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        if child.get("kind") != "t3":
            continue  # not a link/self post
        d = child.get("data")
        if not isinstance(d, dict):
            continue
        name = str(d.get("name") or "").strip()
        title = _decode_entities(str(d.get("title") or "")).strip()
        if not name or not title:
            continue
        selftext = _decode_entities(str(d.get("selftext") or ""))
        permalink = str(d.get("permalink") or "")
        url_link = str(d.get("url") or "")
        # Prefer the canonical reddit.com permalink for traceability.
        post_url = (
            f"https://www.reddit.com{permalink}"
            if permalink.startswith("/")
            else url_link or f"https://www.reddit.com/{name}"
        )
        try:
            created_epoch = float(d.get("created_utc") or 0.0)
        except (TypeError, ValueError):
            created_epoch = 0.0
        if created_epoch <= 0:
            continue
        created_at = datetime.fromtimestamp(created_epoch, tz=UTC)
        try:
            score = int(d.get("score") or 0)
            num_comments = int(d.get("num_comments") or 0)
        except (TypeError, ValueError):
            continue
        kind: PostKind = "self" if d.get("is_self") else "link"
        out.append(
            RedditPost(
                subreddit=subreddit.lower(),
                name=name,
                title=title[:512],
                selftext=selftext[:2000],
                url=post_url[:1024],
                author=str(d.get("author") or "[deleted]"),
                score=score,
                num_comments=num_comments,
                created_at=created_at,
                kind=kind,
            )
        )
    out.sort(key=lambda p: p.score, reverse=True)
    return out


async def fetch_subreddit(
    subreddit: str,
    *,
    sort: str = "hot",
    limit: int = 50,
    user_agent: str = DEFAULT_USER_AGENT,
    client: httpx.AsyncClient | None = None,
    timeout_s: float = 20.0,
) -> list[RedditPost]:
    """Async fetch + parse a single subreddit listing.

    Reddit returns 429 when the User-Agent is empty or recognized as a
    default httpx string ; we always send DEFAULT_USER_AGENT.
    """
    url = listing_url(subreddit, sort=sort, limit=limit)
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if client is None:
        async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as c:
            resp = await c.get(url)
    else:
        resp = await client.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    return parse_listing(resp.text, subreddit=subreddit)


def post_to_news_item_payload(p: RedditPost) -> dict[str, object]:
    """Map a parsed Reddit post → `news_items` row payload.

    Mirrors `mastodon.status_to_news_item_payload` so the same persist
    path / dedup logic applies. `guid_hash = sha256(name)[:32]` keeps
    re-fetches idempotent (Reddit's `name` is permanent across edits).
    """
    summary = p.selftext[:1024] if p.selftext else None
    guid = hashlib.sha256(p.name.encode("utf-8")).hexdigest()[:32]
    now = datetime.now(UTC)
    return {
        "source": f"reddit:{p.subreddit}",
        "source_kind": "social",
        "title": p.title[:512],
        "summary": summary,
        "url": p.url,
        "published_at": p.created_at,
        "fetched_at": now,
        "created_at": now,
        "guid_hash": guid,
        "raw_categories": [p.kind, p.author],
    }


async def persist_to_news_items(
    session,  # type: ignore[no-untyped-def]  # AsyncSession
    posts: list[RedditPost],
) -> int:
    """In-memory dedup + insert into `news_items` (mirrors Mastodon path).

    Returns the number of NEW rows inserted. Caller owns the transaction
    (no commit here)."""
    if not posts:
        return 0
    from sqlalchemy import select

    from ..models import NewsItem

    payloads = [post_to_news_item_payload(p) for p in posts]
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
