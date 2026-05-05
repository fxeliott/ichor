"""Pure-function tests for the Mastodon ATOM feed parser."""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.collectors.mastodon import (
    MastodonStatus,
    _parse_atom_datetime,
    _strip_html,
    parse_mastodon_atom,
    tag_feed_url,
    user_feed_url,
)

# ─────────────────────────── helpers ───────────────────────────────


def test_strip_html_empty() -> None:
    assert _strip_html("") == ""
    assert _strip_html(None) == ""


def test_strip_html_basic() -> None:
    assert _strip_html("<p>hello <em>world</em></p>") == "hello world"


def test_strip_html_collapses_whitespace() -> None:
    assert _strip_html("<p>a\n\n  b\t\tc</p>") == "a b c"


def test_strip_html_handles_inline_links() -> None:
    s = '<p>Check <a href="https://x">this</a> out</p>'
    assert _strip_html(s) == "Check this out"


def test_parse_atom_datetime_z_suffix() -> None:
    d = _parse_atom_datetime("2026-05-04T07:18:00Z")
    assert d == datetime(2026, 5, 4, 7, 18, tzinfo=UTC)


def test_parse_atom_datetime_offset() -> None:
    d = _parse_atom_datetime("2026-05-04T09:18:00+02:00")
    assert d is not None
    # Different absolute representation, same instant.
    assert d.utcoffset() is not None


def test_parse_atom_datetime_invalid() -> None:
    assert _parse_atom_datetime("") is None
    assert _parse_atom_datetime(None) is None
    assert _parse_atom_datetime("not-a-date") is None


def test_user_feed_url_strips_leading_at() -> None:
    assert user_feed_url("mastodon.social", "@alice") == "https://mastodon.social/users/alice.atom"


def test_user_feed_url_strips_trailing_slash() -> None:
    assert user_feed_url("mastodon.social/", "alice") == "https://mastodon.social/users/alice.atom"


def test_tag_feed_url_strips_leading_hash() -> None:
    assert (
        tag_feed_url("mastodon.social", "#economics")
        == "https://mastodon.social/tags/economics.atom"
    )


# ─────────────────────────── parse_mastodon_atom ───────────────────


_SAMPLE_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>https://mastodon.social/users/alice.atom</id>
  <title>alice</title>
  <entry>
    <id>tag:mastodon.social,2026-05-04:objectId=42:objectType=Status</id>
    <published>2026-05-04T07:18:00Z</published>
    <updated>2026-05-04T07:18:00Z</updated>
    <title>Hello there macro folks</title>
    <content type="html">&lt;p&gt;Hello there &lt;em&gt;macro&lt;/em&gt; folks. Inflation is &lt;strong&gt;sticky&lt;/strong&gt;.&lt;/p&gt;</content>
    <link rel="alternate" type="text/html" href="https://mastodon.social/web/@alice/42"/>
    <author>
      <name>alice</name>
    </author>
  </entry>
  <entry>
    <id>tag:mastodon.social,2026-05-03:objectId=41:objectType=Status</id>
    <published>2026-05-03T18:42:00Z</published>
    <updated>2026-05-03T18:42:00Z</updated>
    <title>Older toot</title>
    <content type="html">&lt;p&gt;Older toot body&lt;/p&gt;</content>
    <link rel="alternate" type="text/html" href="https://mastodon.social/web/@alice/41"/>
    <author>
      <name>alice</name>
    </author>
  </entry>
  <entry>
    <id></id>
    <published>2026-05-03T18:42:00Z</published>
    <title>Empty id row</title>
    <content type="html">should be dropped</content>
  </entry>
  <entry>
    <id>tag:mastodon.social,2026-05-03:objectId=43:objectType=Status</id>
    <published></published>
    <title>Bad date row</title>
    <content type="html">should be dropped</content>
  </entry>
</feed>
"""


def test_parse_mastodon_atom_extracts_two_valid_entries() -> None:
    statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social")
    assert len(statuses) == 2
    assert all(isinstance(s, MastodonStatus) for s in statuses)


def test_parse_mastodon_atom_strips_html_content() -> None:
    statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social")
    newest = statuses[0]
    assert "Hello there macro folks" in newest.content_text
    assert "Inflation is sticky" in newest.content_text
    assert "<p>" not in newest.content_text
    assert "<em>" not in newest.content_text


def test_parse_mastodon_atom_picks_alternate_link() -> None:
    statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social")
    assert statuses[0].url == "https://mastodon.social/web/@alice/42"


def test_parse_mastodon_atom_sorts_newest_first() -> None:
    statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social")
    times = [s.published_at for s in statuses]
    assert times == sorted(times, reverse=True)


def test_parse_mastodon_atom_drops_empty_id_and_bad_date() -> None:
    statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social")
    titles = {s.title for s in statuses}
    assert "Empty id row" not in titles
    assert "Bad date row" not in titles


def test_parse_mastodon_atom_carries_instance_and_feed_kind() -> None:
    user_statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social", feed_kind="user")
    assert all(s.instance == "mastodon.social" for s in user_statuses)
    assert all(s.feed_kind == "user" for s in user_statuses)
    tag_statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social", feed_kind="tag")
    assert all(s.feed_kind == "tag" for s in tag_statuses)


def test_parse_mastodon_atom_returns_immutable_dataclass() -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    statuses = parse_mastodon_atom(_SAMPLE_ATOM, instance="mastodon.social")
    with pytest.raises(FrozenInstanceError):
        statuses[0].title = "modified"  # type: ignore[misc]


def test_parse_mastodon_atom_handles_empty_feed() -> None:
    body = '<?xml version="1.0" ?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    assert parse_mastodon_atom(body, instance="mastodon.social") == []


def test_parse_mastodon_atom_falls_back_title_to_content_truncated() -> None:
    """If <title> is empty, use first 120 chars of content_text."""
    body = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:mastodon.social,2026-05-04:objectId=99:objectType=Status</id>
    <published>2026-05-04T07:18:00Z</published>
    <title></title>
    <content type="html">&lt;p&gt;A long body that exceeds 120 characters easily because of how verbose social media commentary on macroeconomic events tends to be.&lt;/p&gt;</content>
    <author><name>bob</name></author>
  </entry>
</feed>
"""
    statuses = parse_mastodon_atom(body, instance="mastodon.social")
    assert len(statuses) == 1
    assert len(statuses[0].title) <= 120
    assert statuses[0].title.startswith("A long body that exceeds")
