"""Unit tests for `cli.embed_session_cards` rendering pure-functions (W110c).

The DB-write path is covered by integration tests (pending W110e).
This module pins the deterministic text-rendering surface that feeds
into `embed_text()` — drift here changes embedding semantics for
*every* future card.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from ichor_api.cli.embed_session_cards import (
    _render_card_content,
    _render_jsonb_list,
    _render_scenarios,
)


def _fake_card(**overrides):  # noqa: ANN001, ANN202 — test helper
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "asset": "EUR_USD",
        "session_type": "pre_ny",
        "generated_at": datetime(2025, 11, 8, 12, 0, tzinfo=UTC),
        "regime_quadrant": "goldilocks",
        "bias_direction": "long",
        "conviction_pct": 72.0,
        "magnitude_pips_low": 30.0,
        "magnitude_pips_high": 80.0,
        "mechanisms": [
            {"description": "DXY weakness + EU PMI surprise"},
            {"description": "Real-yield differential narrowing"},
        ],
        "invalidations": ["Break of 1.0820 support"],
        "catalysts": [{"name": "US CPI 13:30 UTC"}],
        "scenarios": [
            {"label": "base", "p": 0.42, "magnitude_pips": [30, 80], "mechanism": "..."},
            {"label": "mild_bull", "p": 0.21, "magnitude_pips": [60, 110], "mechanism": "..."},
            {"label": "mild_bear", "p": 0.18, "magnitude_pips": [-50, -10], "mechanism": "..."},
            {"label": "crash_flush", "p": 0.0, "magnitude_pips": [-200, -100], "mechanism": "..."},
        ],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_render_card_header_includes_asset_session_date_regime() -> None:
    card = _fake_card()
    out = _render_card_content(card)
    assert "asset=EUR_USD" in out
    assert "session=pre_ny" in out
    assert "2025-11-08" in out
    assert "regime=goldilocks" in out


def test_render_card_bias_block_has_direction_conviction_magnitude() -> None:
    card = _fake_card()
    out = _render_card_content(card)
    assert "bias=long" in out
    assert "conviction=72%" in out
    assert "magnitude_pips=[30,80]" in out


def test_render_card_omits_magnitude_when_null() -> None:
    card = _fake_card(magnitude_pips_low=None, magnitude_pips_high=None)
    out = _render_card_content(card)
    assert "magnitude_pips" not in out
    assert "conviction=72%" in out


def test_render_card_regime_unknown_when_null() -> None:
    card = _fake_card(regime_quadrant=None)
    out = _render_card_content(card)
    assert "regime=unknown" in out


def test_render_jsonb_list_accepts_strings_and_dicts_and_truncates() -> None:
    items = [
        "first string",
        {"description": "second from dict"},
        {"name": "third"},
        "fourth (dropped by max_items=3)",
    ]
    out = _render_jsonb_list("Mechanisms", items, max_items=3)
    assert "Mechanisms:" in out
    assert "first string" in out
    assert "second from dict" in out
    assert "third" in out
    assert "fourth" not in out


def test_render_jsonb_list_returns_empty_string_for_invalid() -> None:
    assert _render_jsonb_list("X", None, max_items=3) == ""
    assert _render_jsonb_list("X", [], max_items=3) == ""
    assert _render_jsonb_list("X", "not-a-list", max_items=3) == ""
    assert _render_jsonb_list("X", [{}], max_items=3) == "X:\n  - {}"


def test_render_scenarios_skips_zero_probability_buckets() -> None:
    scenarios = [
        {"label": "base", "p": 0.42, "magnitude_pips": [30, 80]},
        {"label": "crash_flush", "p": 0.0, "magnitude_pips": [-200, -100]},
    ]
    out = _render_scenarios(scenarios)
    assert "base" in out
    assert "p=0.42" in out
    assert "crash_flush" not in out  # p=0 dropped


def test_render_scenarios_empty_or_invalid_returns_empty_string() -> None:
    assert _render_scenarios(None) == ""
    assert _render_scenarios([]) == ""
    assert _render_scenarios("not-a-list") == ""
    # Items missing label / p are silently skipped
    assert _render_scenarios([{"label": "base"}, {"p": 0.5}]) == ""


def test_render_full_card_has_all_sections_and_double_newline_separators() -> None:
    card = _fake_card()
    out = _render_card_content(card)
    # 6 logical groups → 5 separator pairs of `\n\n`
    blocks = out.split("\n\n")
    assert len(blocks) >= 4  # header + bias + at least one of mech/inv/cat + scenarios
    assert any("Mechanisms" in b for b in blocks)
    assert any("Invalidations" in b for b in blocks)
    assert any("Catalysts" in b for b in blocks)
    assert any("Scenarios" in b for b in blocks)
