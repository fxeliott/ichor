"""Tests for NY Fed MCT collector r52 bot-mitigation workaround.

The collector was silently 0-rows since 2026-05-09 because NY Fed enabled
WAF that returns 403 on the prior bot-style User-Agent. r52 fix : present
as realistic browser session (Chrome 131 UA + Accept-Language + Referer).

These tests pin the workaround as INTENTIONAL so future refactors don't
regress to a bot-flagged UA and silently re-break the collector.
"""

from __future__ import annotations

import re

from ichor_api.collectors.nyfed_mct import _HEADERS


def test_user_agent_uses_realistic_chrome_string() -> None:
    """UA must look like a real browser. NY Fed WAF flags `compatible;`
    + bot-URL patterns ; r52 verified 403 with the prior IchorCollector
    UA. Catches future regressions to bot-style UA."""
    ua = _HEADERS.get("User-Agent", "")
    assert "Chrome/" in ua, f"UA must contain Chrome version, got: {ua!r}"
    assert re.search(r"Chrome/\d+\.\d+", ua), f"UA must have Chrome major.minor version: {ua!r}"
    # Negative assertions: do NOT regress to bot-flagged patterns
    assert "compatible;" not in ua.lower(), (
        f"UA must NOT contain 'compatible;' token (bot-flag pattern): {ua!r}"
    )
    assert "ichor" not in ua.lower(), (
        f"UA must NOT contain 'ichor' (bot-URL pattern triggered NY Fed WAF): {ua!r}"
    )


def test_referer_pinned_to_nyfed_research_page() -> None:
    """Referer must point to a real NY Fed research page so the CSV
    fetch looks like a legitimate browser session originating from
    the public chart page."""
    referer = _HEADERS.get("Referer", "")
    assert referer.startswith("https://www.newyorkfed.org/research"), (
        f"Referer must start with NY Fed research URL : got {referer!r}"
    )


def test_accept_language_present() -> None:
    """Accept-Language header signals a human session ; required by
    most modern WAFs to differentiate browser vs scraper."""
    accept_lang = _HEADERS.get("Accept-Language", "")
    assert accept_lang, "Accept-Language must be set (WAF discrimination)"
    assert "en" in accept_lang.lower(), f"Should include English: {accept_lang!r}"


def test_accept_includes_csv_mime() -> None:
    """The endpoint serves text/csv ; Accept must list it explicitly
    so the server doesn't content-negotiate to HTML."""
    accept = _HEADERS.get("Accept", "")
    assert "csv" in accept.lower(), f"Accept must include csv mime: {accept!r}"
