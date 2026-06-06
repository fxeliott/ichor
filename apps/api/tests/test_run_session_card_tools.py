"""Tests for the Cap-5 ToolConfig wiring in run_session_card (G1 / S03).

`_build_tool_config` decides which tools the live tool-enabled brain passes
(regime / asset / scenarios) may call. The S03 'real-time interconnection'
deliverable adds Claude Code's native WebSearch tool when the
`brain_web_research_enabled` flag is ON, so Opus does live web research during
generation (Voie D, zero API spend). Pins the on/off contract + that the base
db/calc tools and the pass scope are preserved either way.
"""

from __future__ import annotations

from ichor_api.cli.run_session_card import _build_tool_config


def test_tool_config_base_tools_always_present() -> None:
    for flag in (True, False):
        cfg = _build_tool_config(web_research_on=flag)
        assert "mcp__ichor__query_db" in cfg.allowed_tools
        assert "mcp__ichor__calc" in cfg.allowed_tools
        # Tool scope unchanged: regime + asset + scenarios only.
        assert set(cfg.enabled_for_passes) == {"regime", "asset", "scenarios"}


def test_tool_config_adds_websearch_when_enabled() -> None:
    cfg = _build_tool_config(web_research_on=True)
    assert "WebSearch" in cfg.allowed_tools
    # Web search needs a couple extra agentic turns.
    assert cfg.max_turns == 10


def test_tool_config_no_websearch_when_disabled() -> None:
    cfg = _build_tool_config(web_research_on=False)
    assert "WebSearch" not in cfg.allowed_tools
    assert cfg.max_turns == 8
