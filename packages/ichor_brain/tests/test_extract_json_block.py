"""extract_json_block brace-balanced recovery (S02 socle round 6).

The greedy first-`{`-to-last-`}` regex over-captures when prose carries stray
braces, turning a recoverable response into a misleading PassError. The
brace-balanced, string-aware scan recovers the real object.
"""

from __future__ import annotations

import pytest
from ichor_brain.passes.base import PassError, extract_json_block


def test_bare_object() -> None:
    assert extract_json_block('{"a": 1}') == {"a": 1}


def test_fenced_object() -> None:
    assert extract_json_block('```json\n{"a": 1, "b": "x"}\n```') == {"a": 1, "b": "x"}


def test_prose_around_object() -> None:
    assert extract_json_block('Analysis: {"a": 1} done.') == {"a": 1}


def test_trailing_brace_in_prose_after_object() -> None:
    # The greedy {.*} would capture up to the LAST '}' (in '}}') → invalid JSON ;
    # the balanced scan stops at the object's own closing brace.
    txt = 'Here: {"quadrant": "risk_on", "n": 2} — note: use }} sparingly.'
    assert extract_json_block(txt) == {"quadrant": "risk_on", "n": 2}


def test_stray_brace_pair_before_object() -> None:
    # A non-JSON {curly} BEFORE the real object — the per-'{' balanced scan
    # yields {curly braces} (fails json.loads) then the real object (parses).
    txt = 'use {curly braces} carefully. {"a": 1, "b": 2}'
    assert extract_json_block(txt) == {"a": 1, "b": 2}


def test_braces_inside_string_value() -> None:
    # A '}' / '{' inside a string value must NOT change the brace depth.
    txt = '{"note": "use } and { in text", "ok": true}'
    assert extract_json_block(txt) == {"note": "use } and { in text", "ok": True}


def test_escaped_quote_inside_string() -> None:
    txt = '{"q": "she said \\"hi}\\" loudly", "n": 3}'
    assert extract_json_block(txt) == {"q": 'she said "hi}" loudly', "n": 3}


def test_nested_object() -> None:
    assert extract_json_block('x {"a": {"b": 1}, "c": 2} y') == {"a": {"b": 1}, "c": 2}


def test_no_json_raises() -> None:
    with pytest.raises(PassError):
        extract_json_block("no json here at all")
